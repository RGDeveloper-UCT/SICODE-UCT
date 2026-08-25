import os
import shutil
import tempfile
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from werkzeug.utils import secure_filename

from app.services.sicode_ia_background import procesar_lote_sicode_ia


sicode_ia_jobs_bp = Blueprint(
    "sicode_ia_jobs",
    __name__,
    url_prefix="/coordinacion/analisis-documental/ia/trabajos",
)
MAX_ARCHIVOS = 100


def _redis():
    return Redis.from_url(current_app.config.get("SICODE_REDIS_URL", "redis://127.0.0.1:6379/0"))


def _cola():
    return Queue(
        current_app.config.get("SICODE_IA_QUEUE", "sicode_ia"),
        connection=_redis(),
        default_timeout=current_app.config.get("SICODE_IA_JOB_TIMEOUT", 3600),
    )


def _exigir_modificacion():
    if not current_user.puede_modificar:
        abort(403)


def _tamano(archivo):
    pos = archivo.stream.tell()
    archivo.stream.seek(0, 2)
    total = archivo.stream.tell()
    archivo.stream.seek(pos)
    return total


def _job_visible(job):
    usuario_id = int((job.meta or {}).get("usuario_id") or 0)
    return current_user.rol == "administrador" or usuario_id == current_user.id


@sicode_ia_jobs_bp.route("/crear", methods=["POST"])
@login_required
def crear():
    _exigir_modificacion()
    contexto = str(request.form.get("contexto_usuario") or "").strip()[:1000]
    if not contexto:
        flash("Describa qué documentación va a registrar antes de iniciar SICODE.IA.", "danger")
        return redirect(url_for("sicode_ia.inicio"))

    archivos = [a for a in request.files.getlist("archivos_pdf") if a and a.filename]
    if not archivos or len(archivos) > MAX_ARCHIVOS:
        flash(f"Seleccione entre 1 y {MAX_ARCHIVOS} PDF.", "danger")
        return redirect(url_for("sicode_ia.inicio"))
    if any(not a.filename.lower().endswith(".pdf") for a in archivos):
        flash("Todos los archivos deben ser PDF.", "danger")
        return redirect(url_for("sicode_ia.inicio"))

    max_mb = current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40)
    total_bytes = sum(_tamano(a) for a in archivos)
    if total_bytes > max_mb * 1024 * 1024:
        flash(f"La selección pesa {total_bytes/1024/1024:.1f} MB; el límite actual es {max_mb} MB.", "danger")
        return redirect(url_for("sicode_ia.inicio"))

    lote_token = uuid.uuid4().hex
    raiz = current_app.config.get("SICODE_IA_QUEUE_TEMP_DIR") or current_app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR")
    if raiz:
        Path(raiz).mkdir(parents=True, exist_ok=True, mode=0o700)
        carpeta = Path(tempfile.mkdtemp(prefix=f"sicode_ia_queue_{lote_token[:8]}_", dir=raiz))
    else:
        carpeta = Path(tempfile.mkdtemp(prefix=f"sicode_ia_queue_{lote_token[:8]}_"))
    try:
        carpeta.chmod(0o700)
    except OSError:
        pass

    rutas = []
    nombres = []
    try:
        for indice, archivo in enumerate(archivos, start=1):
            nombre = secure_filename(archivo.filename) or f"documento_{indice}.pdf"
            destino = carpeta / f"{indice:03d}_{nombre}"
            archivo.save(destino)
            try:
                destino.chmod(0o600)
            except OSError:
                pass
            rutas.append(str(destino))
            nombres.append(archivo.filename[:240])

        job = _cola().enqueue(
            procesar_lote_sicode_ia,
            rutas,
            nombres,
            contexto,
            lote_token,
            current_user.id,
            job_timeout=current_app.config.get("SICODE_IA_JOB_TIMEOUT", 3600),
            result_ttl=current_app.config.get("SICODE_IA_RESULT_TTL", 86400),
            failure_ttl=current_app.config.get("SICODE_IA_RESULT_TTL", 86400),
            description=f"SICODE.IA {len(archivos)} PDF - usuario {current_user.id}",
        )
        job.meta.update({
            "usuario_id": current_user.id,
            "lote_token": lote_token,
            "fase": "en_cola",
            "porcentaje": 0,
            "detalle": "Trabajo recibido. Esperando worker de SICODE.IA.",
            "archivos_total": len(archivos),
        })
        job.save_meta()
    except Exception:
        shutil.rmtree(carpeta, ignore_errors=True)
        current_app.logger.exception("No fue posible encolar SICODE.IA")
        flash("No fue posible iniciar el análisis en segundo plano. Verifique Redis y el worker SICODE.IA.", "danger")
        return redirect(url_for("sicode_ia.inicio"))

    return redirect(url_for("sicode_ia_jobs.espera", job_id=job.id))


@sicode_ia_jobs_bp.route("/<job_id>")
@login_required
def espera(job_id):
    _exigir_modificacion()
    try:
        job = Job.fetch(job_id, connection=_redis())
    except NoSuchJobError:
        abort(404)
    if not _job_visible(job):
        abort(403)
    return render_template("analisis_documental/sicode_ia_job.html", job_id=job.id)


@sicode_ia_jobs_bp.route("/<job_id>/estado")
@login_required
def estado(job_id):
    _exigir_modificacion()
    try:
        job = Job.fetch(job_id, connection=_redis())
    except NoSuchJobError:
        return jsonify({"estado": "desconocido", "semaforo": "rojo", "detalle": "El trabajo ya no existe en la cola."}), 404
    if not _job_visible(job):
        abort(403)

    estado = job.get_status(refresh=True)
    meta = job.get_meta(refresh=True) or {}
    respuesta = {
        "job_id": job.id,
        "estado": estado,
        "fase": meta.get("fase") or estado,
        "porcentaje": int(meta.get("porcentaje") or (100 if estado == "finished" else 0)),
        "detalle": meta.get("detalle") or "SICODE.IA está trabajando.",
        "archivo_actual": meta.get("archivo_actual"),
        "archivo_indice": meta.get("archivo_indice"),
        "archivos_total": meta.get("archivos_total"),
        "lote_token": meta.get("lote_token"),
    }
    if estado == "finished":
        resultado = job.result or {}
        token = resultado.get("lote_token") or meta.get("lote_token")
        respuesta.update({
            "semaforo": "verde",
            "porcentaje": 100,
            "detalle": "Análisis terminado. Ya puede iniciar la Verificación Humana.",
            "revision_url": url_for("sicode_ia.revision", token=token) if token else None,
        })
    elif estado == "failed":
        respuesta.update({
            "semaforo": "rojo",
            "detalle": "El análisis encontró un error. Revise el servicio sicode-ia-worker.",
            "error": (job.exc_info or "")[-900:],
        })
    else:
        respuesta["semaforo"] = "amarillo"
    return jsonify(respuesta)
