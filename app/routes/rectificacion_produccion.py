from datetime import datetime
from time import time

from flask import Blueprint, abort, jsonify, request, session
from flask_login import current_user, login_required

from app import db
from app.models.expediente import Expediente
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente


rectificacion_produccion_bp = Blueprint(
    "rectificacion_produccion",
    __name__,
    url_prefix="/coordinacion/rectificacion-produccion",
)

MAX_ANEXOS = 200
VIGENCIA_CONFIRMACION_SEGUNDOS = 300
CLAVE_CONFIRMACION_SESION = "rectificacion_produccion_confirmada"


def _estado(expediente):
    return {
        "expediente_id": expediente.id,
        "no_sp": expediente.no_sp,
        "expediente_fisico_registrado": bool(expediente.expediente_fisico_registrado),
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificacion_completa": expediente.rectificacion_completa,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "rectificado_por": expediente.rectificado_por.nombre if expediente.rectificado_por else None,
    }


def _entero(valor):
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _habilitar_siguiente_registro(expediente):
    # Habilita únicamente el siguiente POST de Coordinación para este mismo SP.
    # El guard de aplicación consume esta confirmación una sola vez.
    session[CLAVE_CONFIRMACION_SESION] = {
        "no_sp": expediente.no_sp,
        "usuario_id": current_user.id,
        "valida_hasta": int(time()) + VIGENCIA_CONFIRMACION_SEGUNDOS,
    }


@rectificacion_produccion_bp.get("/estado")
@login_required
def estado():
    no_sp = (request.args.get("no_sp") or "").strip()
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({
            "ok": False,
            "mensaje": "El SP indicado no existe o no está activo en SICODE.",
        }), 404

    return jsonify({"ok": True, **_estado(expediente)})


@rectificacion_produccion_bp.post("/guardar")
@login_required
def guardar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    if datos.get("confirmado") is not True:
        return jsonify({
            "ok": False,
            "mensaje": "Debe confirmar la verificación física o la ausencia del expediente físico.",
        }), 400

    no_sp = str(datos.get("no_sp") or "").strip()
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({
            "ok": False,
            "mensaje": "El SP indicado no existe o no está activo en SICODE.",
        }), 404

    sin_expediente_fisico = datos.get("sin_expediente_fisico") is True
    total_folios = _entero(datos.get("total_folios"))
    total_anexos = _entero(datos.get("total_anexos"))
    origen = str(datos.get("origen") or "Registro de Coordinación").strip()[:120]

    if sin_expediente_fisico:
        if expediente.prestamo_activo:
            return jsonify({
                "ok": False,
                "mensaje": (
                    "No se puede marcar el expediente como no recibido mientras exista "
                    "un préstamo físico activo."
                ),
            }), 409
        if total_anexos is not None and (total_anexos < 0 or total_anexos > MAX_ANEXOS):
            return jsonify({
                "ok": False,
                "mensaje": f"Si registra anexos, indique un total entre 0 y {MAX_ANEXOS}.",
            }), 400
    else:
        if total_folios is None or total_folios < 1:
            return jsonify({
                "ok": False,
                "mensaje": "Indique el total actual de folios con un número mayor que cero.",
            }), 400
        if total_anexos is None or total_anexos < 0 or total_anexos > MAX_ANEXOS:
            return jsonify({
                "ok": False,
                "mensaje": f"Indique un total de anexos entre 0 y {MAX_ANEXOS}.",
            }), 400

    anteriores = {
        "expediente_fisico_registrado": bool(expediente.expediente_fisico_registrado),
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "rectificado_por_id": expediente.rectificado_por_id,
    }

    if sin_expediente_fisico:
        expediente.expediente_fisico_registrado = False
        expediente.folios_rectificados = None
        if total_anexos is not None:
            expediente.anexos_rectificados = total_anexos
        expediente.rectificado_en = None
        expediente.rectificado_por_id = None

        registrar_bitacora(
            accion="MARCAR_SIN_EXPEDIENTE_FISICO_PRODUCCION",
            modulo="Coordinación",
            descripcion=(
                f"Durante {origen} se confirmó que el expediente físico del SP {expediente.no_sp} "
                "todavía no ha sido recibido en Coordinación. No se registró un total ficticio de folios. "
                + (
                    f"Se confirmó un total administrativo de {total_anexos} anexo(s)."
                    if total_anexos is not None
                    else "El total de anexos existente se conservó sin cambios."
                )
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="Expediente",
            entidad_id=expediente.id,
            datos_anteriores=anteriores,
            datos_posteriores={
                "expediente_fisico_registrado": False,
                "folios_rectificados": None,
                "anexos_rectificados": expediente.anexos_rectificados,
                "rectificado_por_id": None,
                "origen": origen,
            },
            motivo="Confirmación de expediente físico aún no recibido durante alimentación de SICODE",
            commit=False,
        )
        db.session.commit()
        _habilitar_siguiente_registro(expediente)

        return jsonify({
            "ok": True,
            "mensaje": (
                f"SP {expediente.no_sp} marcado como sin expediente físico en Coordinación. "
                "Puede continuar con el registro sin inventar un total de folios."
            ),
            **_estado(expediente),
        })

    # Si antes se había marcado como pendiente de recepción, una rectificación
    # física válida confirma que el expediente ya está disponible en Coordinación.
    expediente.expediente_fisico_registrado = True
    expediente.folios_rectificados = total_folios
    expediente.anexos_rectificados = total_anexos
    expediente.rectificado_en = datetime.utcnow()
    expediente.rectificado_por_id = current_user.id

    registrar_bitacora(
        accion="RECTIFICAR_EXPEDIENTE_PRODUCCION",
        modulo="Coordinación",
        descripcion=(
            f"Rectificación obligatoria previa a {origen}. SP {expediente.no_sp}: "
            f"{total_folios} folios y {total_anexos} anexos. "
            "Confirmación realizada para alimentar el registro maestro de SICODE en producción."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
        datos_anteriores=anteriores,
        datos_posteriores={
            "expediente_fisico_registrado": True,
            "folios_rectificados": total_folios,
            "anexos_rectificados": total_anexos,
            "rectificado_por_id": current_user.id,
            "origen": origen,
        },
        motivo="Rectificación operativa obligatoria durante alimentación de SICODE en producción",
        commit=False,
    )
    db.session.commit()
    _habilitar_siguiente_registro(expediente)

    return jsonify({
        "ok": True,
        "mensaje": (
            f"SP {expediente.no_sp} rectificado con {total_folios} folios "
            f"y {total_anexos} anexos."
        ),
        **_estado(expediente),
    })
