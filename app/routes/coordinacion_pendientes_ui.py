from flask import request, url_for

from app.routes.coordinacion import coordinacion_bp


SCRIPT_PENDIENTES = "js/coordinacion_pendientes.js"
ENDPOINTS_UI = {
    "coordinacion.inicio",
    "coordinacion.pendientes",
    "coordinacion.verificar_pendiente",
}


@coordinacion_bp.after_request
def cargar_enlace_bandeja_pendientes(response):
    if request.endpoint not in ENDPOINTS_UI or request.method != "GET":
        return response
    if response.status_code != 200 or response.mimetype != "text/html":
        return response

    contenido = response.get_data(as_text=True)
    if SCRIPT_PENDIENTES in contenido:
        return response

    etiqueta = f'<script src="{url_for("static", filename=SCRIPT_PENDIENTES)}" defer></script>'
    if "</body>" in contenido:
        contenido = contenido.replace("</body>", f"{etiqueta}\n</body>", 1)
    else:
        contenido += etiqueta
    response.set_data(contenido)
    return response
