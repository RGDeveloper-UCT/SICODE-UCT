from datetime import datetime

from flask import abort, jsonify, request, session, url_for
from flask_login import current_user

from app import db
from app.routes.coordinacion import coordinacion_bp
from app.routes.coordinacion_monitoreo_masivo import (
    MAX_ANEXOS_MONITOREO,
    SESION_LOTE,
    _entero,
    _estado_masivo,
    _texto,
    _validar_lote_id,
)
from app.routes.monitoreo_anexos import _estado_anexos
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente


SCRIPT_MASIVO_FISICO = "js/coordinacion_monitoreo_masivo_fisico.js"


def _respuesta_error(mensaje, codigo=400):
    return jsonify({"ok": False, "mensaje": mensaje}), codigo


def _guardar_marca_lote(lote, expediente, total_folios, total_anexos, sin_expediente_fisico):
    rectificados = dict(lote.get("rectificados") or {})
    rectificados[str(expediente.id)] = {
        "folios": total_folios,
        "anexos": total_anexos,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "sin_expediente_fisico": bool(sin_expediente_fisico),
    }
    actualizado = {"id": lote["id"], "rectificados": rectificados}
    session[SESION_LOTE] = actualizado
    session.modified = True
    return actualizado


@coordinacion_bp.before_request
def rectificacion_fisica_monitoreo_masivo():
    """Amplía la rectificación masiva para admitir un SP aún sin expediente físico.

    La ruta histórica exigía siempre folios > 0. Interceptamos únicamente el
    endpoint de rectificación masiva para mantener una sola cadena de validación:
    con expediente se rectifican folios/anexos; sin expediente se conserva la
    secuencia de anexos, pero no se inventa un total de folios.
    """
    if request.endpoint != "coordinacion.rectificar_monitoreo_masivo" or request.method != "POST":
        return None
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    lote = _validar_lote_id(datos.get("lote_id"))
    if lote is None:
        return _respuesta_error("El lote ya no está activo.", 409)
    if datos.get("confirmado") is not True:
        return _respuesta_error(
            "Debe confirmar la verificación física/File Server o la ausencia del expediente físico."
        )

    no_sp = _texto(datos.get("no_sp"), 60)
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return _respuesta_error("El SP indicado no existe o no está activo.", 404)

    sin_expediente_fisico = datos.get("sin_expediente_fisico") is True
    total_anexos = _entero(datos.get("total_anexos"))
    total_folios = None if sin_expediente_fisico else _entero(datos.get("total_folios"))

    if sin_expediente_fisico and expediente.prestamo_activo:
        return _respuesta_error(
            "No se puede marcar el expediente como no recibido mientras exista un préstamo físico activo.",
            409,
        )

    if not sin_expediente_fisico and (total_folios is None or total_folios < 1):
        return _respuesta_error(
            "El total de folios debe ser mayor que cero o debe marcar que aún no se cuenta con el expediente físico."
        )

    # En el masivo el total de anexos sí es obligatorio porque determina el
    # correlativo de los reportes que serán incorporados como nuevos anexos.
    if total_anexos is None or total_anexos < 0 or total_anexos > MAX_ANEXOS_MONITOREO:
        return _respuesta_error(
            f"El total de anexos debe estar entre 0 y {MAX_ANEXOS_MONITOREO}."
        )

    estado_anexos = _estado_anexos(expediente)
    if total_anexos < estado_anexos["minimo_conocido"]:
        return _respuesta_error(
            f"SICODE ya tiene evidencia de al menos {estado_anexos['minimo_conocido']} anexo(s) "
            "para este SP. Verifique el control disponible y corrija el total."
        )

    anteriores = {
        "expediente_fisico_registrado": bool(expediente.expediente_fisico_registrado),
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "rectificado_por_id": expediente.rectificado_por_id,
    }

    expediente.expediente_fisico_registrado = not sin_expediente_fisico
    expediente.folios_rectificados = total_folios
    expediente.anexos_rectificados = total_anexos
    # Esta fecha representa la confirmación del estado dentro del lote. Aunque
    # no exista expediente físico, permite garantizar que el mismo usuario no
    # continúe con un lote cuyos datos hayan cambiado durante la captura.
    expediente.rectificado_en = datetime.utcnow()
    expediente.rectificado_por_id = current_user.id

    if sin_expediente_fisico:
        accion = "MARCAR_SIN_EXPEDIENTE_FISICO_MONITOREO_MASIVO"
        descripcion = (
            f"Durante el registro masivo de monitoreo se confirmó que el expediente físico del SP "
            f"{expediente.no_sp} todavía no ha sido recibido en Coordinación. No se registró un "
            f"total ficticio de folios; se confirmó un total administrativo de {total_anexos} anexo(s) "
            "para conservar el correlativo documental del lote."
        )
        motivo = "Confirmación de expediente físico aún no recibido en registro masivo de monitoreo"
    else:
        accion = "RECTIFICAR_EXPEDIENTE_MONITOREO_MASIVO"
        descripcion = (
            f"Rectificación para lote masivo de monitoreo. SP {expediente.no_sp}: "
            f"{total_folios} folios y {total_anexos} anexos antes de incorporar los reportes del lote."
        )
        motivo = "Rectificación obligatoria previa a registro masivo de monitoreo"

    registrar_bitacora(
        accion=accion,
        modulo="Coordinación",
        descripcion=descripcion,
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
        datos_anteriores=anteriores,
        datos_posteriores={
            "expediente_fisico_registrado": bool(expediente.expediente_fisico_registrado),
            "folios_rectificados": expediente.folios_rectificados,
            "anexos_rectificados": expediente.anexos_rectificados,
            "rectificado_por_id": current_user.id,
            "sin_expediente_fisico": sin_expediente_fisico,
            "origen": "Registro masivo de reportes de monitoreo",
        },
        motivo=motivo,
        commit=False,
    )
    db.session.commit()

    lote = _guardar_marca_lote(
        lote,
        expediente,
        total_folios,
        total_anexos,
        sin_expediente_fisico,
    )

    if sin_expediente_fisico:
        mensaje = (
            f"SP {expediente.no_sp} confirmado sin expediente físico: folios sin dato y "
            f"{total_anexos} anexos para el correlativo del lote."
        )
    else:
        mensaje = (
            f"SP {expediente.no_sp} rectificado: {total_folios} folios y {total_anexos} anexos."
        )

    return jsonify({
        "ok": True,
        "mensaje": mensaje,
        "expediente_fisico_registrado": bool(expediente.expediente_fisico_registrado),
        "sin_expediente_fisico": sin_expediente_fisico,
        **_estado_masivo(expediente, lote),
    })


@coordinacion_bp.after_request
def cargar_control_fisico_en_monitoreo_masivo(response):
    """Carga el complemento visual sólo en el panel masivo, sin duplicar plantilla."""
    if request.endpoint != "coordinacion.monitoreo_masivo" or request.method != "GET":
        return response
    if response.status_code != 200 or response.mimetype != "text/html":
        return response

    contenido = response.get_data(as_text=True)
    if SCRIPT_MASIVO_FISICO in contenido:
        return response

    etiqueta = f'<script src="{url_for("static", filename=SCRIPT_MASIVO_FISICO)}" defer></script>'
    if "</body>" in contenido:
        contenido = contenido.replace("</body>", f"{etiqueta}\n</body>", 1)
    else:
        contenido += etiqueta
    response.set_data(contenido)
    return response
