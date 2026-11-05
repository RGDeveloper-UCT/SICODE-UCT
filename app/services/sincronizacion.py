"""Invalidación global post-commit mediante Redis Pub/Sub.

No transportamos registros ni datos sensibles: solamente los nombres de los
módulos afectados. Los clientes vuelven a consultar sus endpoints autorizados.
"""
import json
import logging
from uuid import uuid4

from flask import current_app, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session
import redis


CANAL = "sicode:sincronizacion:v1"
_CLAVE = "sicode_modulos_modificados"
_REGISTRADO = False
_LOG = logging.getLogger(__name__)


def _modulos(tabla):
    tabla = (tabla or "").lower()
    if not tabla or "presencia" in tabla:
        return set()
    modulos = {"global", "dashboard", "bitacora"}
    if tabla.startswith("agenda_"):
        modulos.add("agenda")
    if any(x in tabla for x in ("expediente", "portador", "ubicacion", "verificacion")):
        modulos.add("expedientes")
    if any(x in tabla for x in ("documento", "anexo", "analisis", "lote")):
        modulos.update(("anexos", "coordinacion"))
    if any(x in tabla for x in ("coordinacion", "pago", "remision", "monitoreo", "dispositivo")):
        modulos.add("coordinacion")
    if any(x in tabla for x in ("prestamo", "traslado")):
        modulos.add("prestamos")
    if "alerta" in tabla:
        modulos.add("alertas")
    return modulos


def _antes_de_flush(session, _contexto, _instancias):
    if not has_app_context() or not current_app.config.get("SICODE_REALTIME_ENABLED", True):
        return
    afectados = set()
    for objeto in session.new.union(session.deleted):
        afectados.update(_modulos(getattr(objeto, "__tablename__", "")))
    for objeto in session.dirty:
        if session.is_modified(objeto, include_collections=True):
            afectados.update(_modulos(getattr(objeto, "__tablename__", "")))
    if afectados:
        session.info.setdefault(_CLAVE, set()).update(afectados)


def _publicar_despues_de_commit(session):
    modulos = session.info.pop(_CLAVE, None)
    if not modulos or not has_app_context():
        return
    app = current_app._get_current_object()
    if not app.config.get("SICODE_REALTIME_ENABLED", True) or app.config.get("TESTING"):
        return
    mensaje = json.dumps({
        "id": uuid4().hex,
        "modulos": sorted(modulos),
    }, separators=(",", ":"))
    try:
        conexion = redis.Redis.from_url(
            app.config["SICODE_REALTIME_REDIS_URL"],
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        conexion.publish(CANAL, mensaje)
        conexion.close()
    except redis.RedisError:
        # Un fallo de notificación nunca revierte un cambio confirmado.
        _LOG.warning("No fue posible publicar la invalidación en Redis", exc_info=True)


def _despues_de_rollback(session):
    session.info.pop(_CLAVE, None)


def registrar_eventos_sincronizacion():
    """Registra una sola vez los hooks globales de la sesión SQLAlchemy."""
    global _REGISTRADO
    if _REGISTRADO:
        return
    event.listen(Session, "before_flush", _antes_de_flush)
    event.listen(Session, "after_commit", _publicar_despues_de_commit)
    event.listen(Session, "after_rollback", _despues_de_rollback)
    event.listen(Session, "after_soft_rollback", lambda session, _transaccion: _despues_de_rollback(session))
    _REGISTRADO = True
