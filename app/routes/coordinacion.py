from flask import Blueprint, render_template, abort
from flask_login import login_required

coordinacion_bp = Blueprint("coordinacion", __name__, url_prefix="/coordinacion")

TIPOS_REGISTRO = {
    "pago": {
        "titulo": "Pago",
        "descripcion": "Registrar pagos recibidos y asociarlos al SP correspondiente.",
    },
    "instalacion": {
        "titulo": "Instalación",
        "descripcion": "Registrar recepción y control administrativo de nuevas instalaciones.",
    },
    "desinstalacion": {
        "titulo": "Desinstalación",
        "descripcion": "Registrar desinstalaciones recibidas y su control administrativo.",
    },
    "anexo": {
        "titulo": "Anexo",
        "descripcion": "Registrar anexos recibidos y relacionarlos con el expediente.",
    },
    "monitoreo": {
        "titulo": "Reporte de monitoreo",
        "descripcion": "Registrar reportes remitidos por el Centro de Control y Monitoreo.",
    },
    "documento-emitido": {
        "titulo": "Documento emitido",
        "descripcion": "Registrar documentos generados y firmados por la Coordinación.",
    },
    "actividad": {
        "titulo": "Actividad",
        "descripcion": "Registrar actividades realizadas por el personal de la Coordinación.",
    },
    "remision": {
        "titulo": "Remisión de expediente",
        "descripcion": "Registrar expedientes remitidos a Archivo/Bodega MINGOB u otro destino.",
    },
}


@coordinacion_bp.route("")
@coordinacion_bp.route("/")
@login_required
def inicio():
    return render_template(
        "coordinacion/inicio.html",
        tipos_registro=TIPOS_REGISTRO,
    )


@coordinacion_bp.route("/registrar/<tipo>")
@login_required
def registrar(tipo):
    configuracion = TIPOS_REGISTRO.get(tipo)
    if not configuracion:
        abort(404)

    return render_template(
        "coordinacion/registro_pendiente.html",
        tipo=tipo,
        configuracion=configuracion,
    )
