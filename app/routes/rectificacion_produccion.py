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
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificacion_completa": expediente.rectificacion_completa,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "rectificado_por": expediente.rectificado_por.nombre if expediente.rectificado_por else None,
    }


def _entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


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
            "mensaje": "Debe confirmar que verificó físicamente los totales del expediente.",
        }), 400

    no_sp = str(datos.get("no_sp") or "").strip()
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({
            "ok": False,
            "mensaje": "El SP indicado no existe o no está activo en SICODE.",
        }), 404

    total_folios = _entero(datos.get("total_folios"))
    total_anexos = _entero(datos.get("total_anexos"))

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
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
        "rectificado_por_id": expediente.rectificado_por_id,
    }

    expediente.folios_rectificados = total_folios
    expediente.anexos_rectificados = total_anexos
    expediente.rectificado_en = datetime.utcnow()
    expediente.rectificado_por_id = current_user.id

    origen = str(datos.get("origen") or "Registro de Coordinación").strip()[:120]
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
            "folios_rectificados": total_folios,
            "anexos_rectificados": total_anexos,
            "rectificado_por_id": current_user.id,
            "origen": origen,
        },
        motivo="Rectificación operativa obligatoria durante alimentación de SICODE en producción",
        commit=False,
    )
    db.session.commit()

    # Habilita únicamente el siguiente POST de Coordinación para este mismo SP.
    # El guard de aplicación consume esta confirmación una sola vez.
    session[CLAVE_CONFIRMACION_SESION] = {
        "no_sp": expediente.no_sp,
        "usuario_id": current_user.id,
        "valida_hasta": int(time()) + VIGENCIA_CONFIRMACION_SEGUNDOS,
    }

    return jsonify({
        "ok": True,
        "mensaje": (
            f"SP {expediente.no_sp} rectificado con {total_folios} folios "
            f"y {total_anexos} anexos."
        ),
        **_estado(expediente),
    })
