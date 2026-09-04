from datetime import datetime

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, MovimientoDispositivo, PagoCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.ubicacion import UbicacionFisica
from app.services.anexos_integridad_service import bloquear_y_validar_anexo_nuevo


_REGISTRADO = False
_CAMPOS_UBICACION = ("archivador", "sicoin", "estante", "caja", "modulo", "posicion", "observaciones")


def _usuario_actual_id():
    if has_request_context() and current_user.is_authenticated:
        return current_user.id
    return None


def _expediente(session, expediente_id, relacion=None):
    if relacion is not None:
        return relacion
    return session.get(Expediente, expediente_id) if expediente_id is not None else None


def _auditar_cambio_ubicacion(session, ubicacion):
    estado = inspect(ubicacion)
    anteriores = {}
    posteriores = {}

    for campo in _CAMPOS_UBICACION:
        historia = estado.attrs[campo].history
        if not historia.has_changes():
            continue
        anteriores[campo] = historia.deleted[0] if historia.deleted else None
        posteriores[campo] = historia.added[0] if historia.added else getattr(ubicacion, campo)

    if not posteriores:
        return

    session.add(Bitacora(
        usuario_id=_usuario_actual_id(),
        expediente_id=ubicacion.expediente_id,
        accion="CAMBIAR_UBICACION",
        modulo="Expedientes",
        descripcion="Se actualizó la ubicación física del expediente.",
        entidad="UbicacionFisica",
        entidad_id=str(ubicacion.id) if ubicacion.id else None,
        datos_anteriores=anteriores,
        datos_posteriores=posteriores,
        ip_origen=request.remote_addr if has_request_context() else None,
        user_agent=(request.user_agent.string[:255] if has_request_context() and request.user_agent else None),
        creado_en=datetime.utcnow(),
    ))


def _validar_prestamo_nuevo(session, prestamo):
    expediente = _expediente(session, prestamo.expediente_id, prestamo.expediente)
    if expediente is None:
        return
    if not expediente.expediente_fisico_registrado:
        raise ValueError("No se puede prestar un SP que todavía no tiene expediente físico registrado.")
    if not expediente.activo:
        raise ValueError("No se puede prestar un expediente inactivo.")


def _validar_documento_nuevo(session, documento):
    expediente = _expediente(session, documento.expediente_id, documento.expediente)
    if expediente and not expediente.expediente_fisico_registrado:
        raise ValueError("No se puede foliar un SP que todavía no tiene expediente físico registrado.")


def _resolver_alerta_vencimiento(session, prestamo):
    estado = inspect(prestamo).attrs.estado.history
    if not estado.has_changes() or prestamo.estado != "Devuelto":
        return

    alertas = session.execute(
        select(Alerta).where(
            Alerta.expediente_id == prestamo.expediente_id,
            Alerta.tipo_alerta == "PRESTAMO_VENCIDO",
            Alerta.estado.in_(["Abierta", "En revisión"]),
        )
    ).scalars().all()

    for alerta in alertas:
        alerta.estado = "Corregida"
        alerta.cerrado_en = None
        alerta.cerrada_por_id = None


def _sincronizar_folios_recepcion(detalle):
    registro = detalle.registro
    if registro is not None and detalle.folios and not registro.folios_recepcion:
        registro.folios_recepcion = detalle.folios


def _antes_de_flush(session, _flush_context, _instances):
    for objeto in list(session.new):
        if isinstance(objeto, PrestamoExpediente):
            _validar_prestamo_nuevo(session, objeto)
        elif isinstance(objeto, DocumentoExpediente):
            _validar_documento_nuevo(session, objeto)
        elif isinstance(objeto, AnexoCoordinacion):
            bloquear_y_validar_anexo_nuevo(session, objeto)
            _sincronizar_folios_recepcion(objeto)
        elif isinstance(objeto, (PagoCoordinacion, MovimientoDispositivo)):
            _sincronizar_folios_recepcion(objeto)

    for objeto in list(session.dirty):
        if isinstance(objeto, PrestamoExpediente):
            _resolver_alerta_vencimiento(session, objeto)
        elif isinstance(objeto, UbicacionFisica):
            _auditar_cambio_ubicacion(session, objeto)
        elif isinstance(objeto, (PagoCoordinacion, MovimientoDispositivo, AnexoCoordinacion)):
            _sincronizar_folios_recepcion(objeto)


def registrar_eventos_integridad():
    global _REGISTRADO
    if _REGISTRADO:
        return
    event.listen(Session, "before_flush", _antes_de_flush)
    _REGISTRADO = True
