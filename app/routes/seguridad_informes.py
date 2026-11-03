"""Recepción de boletines técnicos PDF/DOCX con múltiples CVE y sin duplicación."""
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app import db
from app.models.seguridad_operativa import InformeSeguridadTI, VulnerabilidadTI
from app.models.usuario import Usuario
from app.services.agenda_service import notificar
from app.services.bitacora_service import registrar_bitacora
from app.services.sincronizacion_vulnerabilidades import CVE_PATTERN
from app.routes.seguridad_operativa import seguridad_operativa_bp, _archivo_carpeta, _escritura, _fecha, _texto, _auditoria

MAX_ARCHIVO = 8 * 1024 * 1024
TECNOLOGIAS = {"CHROME", "JAVA_PYTHON", "PHP", "MULTIPLE", "OTRO"}
CVE_SEPARADOR = re.compile(r"[\s,;]+")


def _validar_archivo(nombre, datos):
    extension = Path(nombre).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise ValueError("El informe debe ser PDF o DOCX.")
    if not datos or len(datos) > MAX_ARCHIVO:
        raise ValueError("El archivo está vacío o supera el límite de 8 MB.")
    if extension == ".pdf":
        if not datos.startswith(b"%PDF-") or b"%%EOF" not in datos[-2048:]:
            raise ValueError("El archivo PDF no presenta una estructura válida.")
    else:
        try:
            with ZipFile(BytesIO(datos)) as z:
                nombres = set(z.namelist())
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(nombres):
                    raise ValueError("El archivo no corresponde a un DOCX válido.")
                if any(x.lower().endswith(("vbaproject.bin", ".exe", ".js", ".vbs")) for x in nombres):
                    raise ValueError("El DOCX contiene contenido no autorizado.")
        except (BadZipFile, OSError) as error:
            raise ValueError("El DOCX está dañado.") from error
    return extension


def _parsear_cves(texto):
    valores = [item.upper() for item in CVE_SEPARADOR.split((texto or "").strip()) if item]
    if len(valores) > 100:
        raise ValueError("Máximo 100 CVE por informe.")
    if any(not CVE_PATTERN.fullmatch(item) for item in valores):
        raise ValueError("Separe identificadores CVE con comas, espacios o saltos de línea.")
    return list(dict.fromkeys(valores))


@seguridad_operativa_bp.get("/informes")
@login_required
def informes_seguridad():
    page = max(1, request.args.get("page", 1, type=int))
    registros = InformeSeguridadTI.query.order_by(InformeSeguridadTI.id.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template("seguridad_operativa/informes.html", registros=registros)


@seguridad_operativa_bp.route("/informes/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_informe():
    _escritura()
    if request.method == "POST":
        destino = None
        try:
            titulo = _texto("titulo", 220, True)
            emisor = _texto("emisor", 160, True)
            tecnologia = _texto("tecnologia", 40, True)
            resumen = _texto("resumen", 4000)
            prioridad = _texto("prioridad", 12) or "media"
            if prioridad not in {"alta", "media"} or tecnologia not in TECNOLOGIAS:
                raise ValueError("Prioridad o tecnología inválida.")
            fecha = _fecha(request.form.get("fecha_informe"))
            recibido = _fecha(request.form.get("fecha_recibido"))
            cves = _parsear_cves(request.form.get("cves", ""))
            documento = request.files.get("archivo")
            if documento is None or not documento.filename:
                raise ValueError("Adjunte el informe recibido.")
            nombre = secure_filename(documento.filename)[:180] or "informe"
            contenido = documento.stream.read(MAX_ARCHIVO + 1)
            extension = _validar_archivo(nombre, contenido)
            digest = sha256(contenido).hexdigest()
            if InformeSeguridadTI.query.filter_by(sha256=digest).first():
                raise ValueError("Este archivo ya fue incorporado; no se duplicará.")
            informe = InformeSeguridadTI(
                titulo=titulo, emisor=emisor, tecnologia=tecnologia,
                fecha_informe=fecha, fecha_recibido=recibido, resumen=resumen,
                archivo_nombre=uuid4().hex + extension, nombre_original=nombre,
                sha256=digest, creado_por_id=current_user.id,
            )
            db.session.add(informe)
            db.session.flush()
            for cve in cves:
                v = VulnerabilidadTI.query.filter_by(cve=cve).first()
                if v is None:
                    v = VulnerabilidadTI(
                        cve=cve, fuente="CERT", fuentes=["CERT"], titulo=cve,
                        severidad="DESCONOCIDA",
                        descripcion="Mencionada en el informe recibido: " + titulo,
                        recomendacion="Verificar la exposición y consultar las recomendaciones del emisor.",
                        fecha_recibido=recibido,
                    )
                    db.session.add(v)
                    db.session.flush()
                elif "CERT" not in (v.fuentes or []):
                    v.fuentes = sorted(set((v.fuentes or []) + ["CERT"]))
                informe.vulnerabilidades.append(v)
            carpeta = _archivo_carpeta()
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / informe.archivo_nombre
            destino.write_bytes(contenido)
            activos = [u.id for u in Usuario.query.filter_by(activo=True).all() if u.puede_modificar]
            notificar(activos, None,
                     "Informe de seguridad recibido: " + titulo[:120],
                     f"Se registró un informe de {emisor}. Contiene {len(cves)} CVE identificados; revisar aplicabilidad.",
                     prioridad=prioridad, obligatoria=False, clave=f"seguridad-ti:informe:{informe.id}")
            _auditoria("REGISTRAR_INFORME_SEGURIDAD", "InformeSeguridadTI", informe.id,
                       titulo, {"cves": cves, "sha256": digest, "tecnologia": tecnologia})
            db.session.commit()
            flash(f"Informe registrado con {len(cves)} CVE vinculados.", "success")
            return redirect(url_for("seguridad_operativa.informes_seguridad"))
        except (ValueError, TypeError, IntegrityError, OSError) as error:
            db.session.rollback()
            if destino is not None:
                destino.unlink(missing_ok=True)
            flash(str(error), "warning")
    return render_template("seguridad_operativa/nuevo_informe.html", tecnologias=sorted(TECNOLOGIAS))


@seguridad_operativa_bp.get("/informes/<int:id_>/archivo")
@login_required
def descargar_informe(id_):
    informe = db.get_or_404(InformeSeguridadTI, id_)
    extension = Path(informe.archivo_nombre).suffix.lower()
    if not re.fullmatch(r"[0-9a-f]{32}\.(?:pdf|docx)", informe.archivo_nombre):
        abort(404)
    tipos = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    ruta = _archivo_carpeta() / informe.archivo_nombre
    if extension not in tipos or not ruta.is_file():
        abort(404)
    return send_file(ruta, mimetype=tipos[extension], as_attachment=True,
                     download_name=informe.nombre_original)
