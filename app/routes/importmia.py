"""ImportM.IA: carga, revisión y conciliación segura del Excel maestro v3."""
import hashlib
import json

from flask import Blueprint, abort, flash, render_template, request, current_app
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.services.importmia_service import conciliar, ImportMIAInvalido

importmia_bp = Blueprint("importmia", __name__, url_prefix="/importmia")


def _firmador():
    return URLSafeTimedSerializer(current_app.secret_key, salt="importmia-v3")

def _huella(resultado):
    """Vincula la vista previa a los resultados que existían al validar."""
    datos = resultado["decisiones"]
    return hashlib.sha256(json.dumps(datos, ensure_ascii=False, default=str).encode()).hexdigest()

@importmia_bp.route("/", methods=["GET", "POST"])
@login_required
def inicio():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    resultado = None
    token = None
    if request.method == "POST":
        if request.form.get("accion") != "previsualizar":
            abort(400)
        archivo = request.files.get("archivo")
        if not archivo or not (archivo.filename or "").lower().endswith(".xlsx"):
            flash("Seleccione el contrato Excel .xlsx de ImportM.IA v3.", "warning")
        else:
            try:
                datos = archivo.stream.read(8 * 1024 * 1024 + 1)
                resultado = conciliar(datos)
                token = _firmador().dumps({
                    "usuario": current_user.id,
                    "sha256": hashlib.sha256(datos).hexdigest(),
                    "huella": _huella(resultado),
                })
            except ImportMIAInvalido as exc:
                flash(str(exc), "danger")
    return render_template("importmia/inicio.html", resultado=resultado, token=token)


@importmia_bp.post("/confirmar-indice")
@login_required
def confirmar_indice():
    """Solo confirma NUEVO del índice mediante el conciliador ya existente.

    Pagos, análisis, anexos administrativos y otras hojas no se escriben.
    Requiere subir de nuevo el mismo archivo, reevalúa concurrencia y conflictos.
    """
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    try:
        firmado = _firmador().loads(request.form.get("token", ""), max_age=1800)
    except (BadSignature, SignatureExpired):
        flash("La vista previa expiró o cambió. Vuelva a comparar el archivo.", "warning")
        return __redirigir()

    archivo = request.files.get("archivo")
    datos = archivo.stream.read(8 * 1024 * 1024 + 1) if archivo else b""
    if len(datos) > 8 * 1024 * 1024:
        flash("El Excel excede el tamaño permitido.", "danger")
        return __redirigir()
    if (firmado.get("usuario") != current_user.id or
            hashlib.sha256(datos).hexdigest() != firmado.get("sha256")):
        flash("Debe confirmar con el mismo Excel y el mismo usuario.", "danger")
        return __redirigir()

    from collections import Counter
    from app import db
    from app.models.expediente import Expediente
    from app.models.documento_expediente import DocumentoExpediente
    from app.models.coordinacion import AnexoCoordinacion
    from app.services.bitacora_service import registrar_bitacora
    from app.services.importacion_indice_fileserver_service import normalizar

    try:
        resultado = conciliar(datos)
        # Mismo bloqueo y revalidación que el importador actual de File Server.
        sp = sorted({r["sp"] for r in resultado["filas"]})
        Expediente.query.with_entities(Expediente.id).filter(
            Expediente.no_sp.in_(sp)
        ).order_by(Expediente.id).with_for_update(of=Expediente).all()
        resultado = conciliar(datos)
        if _huella(resultado) != firmado.get("huella"):
            raise ImportMIAInvalido("SICODE cambió desde la vista previa; vuelva a comparar.")

        decisiones = resultado["decisiones"]
        numeros = Counter((r["expediente_id"], r["numero_anexo"])
                          for r in decisiones if r["seccion"] == "ANEXO")
        nuevos = [r for r in decisiones if r["estado"] == "NUEVO"]
        ids = []
        for r in nuevos:
            doc = DocumentoExpediente(
                expediente_id=r["expediente_id"],
                nombre_documento=r["nombre_documento"],
                tipo_documento=r["tipo_documento"],
                folio_inicio=r["folio_inicial"],
                folio_fin=r["folio_final"],
                total_folios=r["folio_final"] - r["folio_inicial"] + 1,
                estado_revision="Pendiente de revisión",
                es_anexo=r["seccion"] == "ANEXO",
                indice_numero_anexo=r["numero_anexo"],
                indice_titulo_anexo=r["titulo_anexo"] or None,
                indice_orden=r["orden"],
                observaciones=r["observaciones"] or None,
                activo=True,
            )
            db.session.add(doc)
            db.session.flush()
            ids.append(doc.id)
            if r["seccion"] == "ANEXO" and r.get("anexo_coordinacion_id"):
                anexo = db.session.get(AnexoCoordinacion, r["anexo_coordinacion_id"])
                fuerte = anexo and (
                    (r["titulo_anexo"] and anexo.titulo and
                     normalizar(r["titulo_anexo"]) == normalizar(anexo.titulo))
                    or (r["rc"] and anexo.registro.rc and
                        normalizar(r["rc"]) == normalizar(anexo.registro.rc))
                )
                if (fuerte and anexo.documento_expediente_id is None
                        and numeros[(r["expediente_id"], r["numero_anexo"])] == 1):
                    anexo.documento_expediente_id = doc.id

        registrar_bitacora(
            accion="IMPORTMIA_CONFIRMAR_INDICE", modulo="ImportM.IA",
            descripcion=f"ImportM.IA v3: {len(nuevos)} documentos nuevos indexados; otras hojas sin escritura.",
            usuario_id=current_user.id, entidad="DocumentoExpediente",
            datos_posteriores={"sha256_excel": firmado["sha256"], "documentos": ids[:200],
                              "solo_indice": True, "preserva_rectificaciones": True},
            commit=False,
        )
        db.session.commit()
        flash(f"Índice: {len(nuevos)} documentos nuevos registrados. Las hojas operativas siguen pendientes.", "success")
    except (ImportMIAInvalido, ValueError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Fallo ImportM.IA confirmar índice")
        flash("No fue posible confirmar el índice. No se aplicaron cambios.", "danger")
    return __redirigir()


def __redirigir():
    from flask import redirect, url_for
    return redirect(url_for("importmia.inicio"))
