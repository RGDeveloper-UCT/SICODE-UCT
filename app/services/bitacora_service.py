from flask import has_request_context, request

from app import db
from app.models.bitacora import Bitacora


def registrar_bitacora(
    accion,
    modulo,
    descripcion=None,
    usuario_id=None,
    expediente_id=None,
    entidad=None,
    entidad_id=None,
    datos_anteriores=None,
    datos_posteriores=None,
    motivo=None,
    commit=True,
):
    """Registra auditoría legible y estructurada.

    `commit=False` permite incluir la bitácora en la misma transacción que la
    operación de negocio. Se conserva `commit=True` por compatibilidad con
    llamadas no transaccionales (login, exportaciones y consultas auditadas).
    """
    ip_origen = request.remote_addr if has_request_context() else None
    agente = request.user_agent.string[:255] if has_request_context() and request.user_agent else None

    registro = Bitacora(
        usuario_id=usuario_id,
        expediente_id=expediente_id,
        accion=accion,
        modulo=modulo,
        descripcion=descripcion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        datos_anteriores=datos_anteriores,
        datos_posteriores=datos_posteriores,
        motivo=motivo,
        ip_origen=ip_origen,
        user_agent=agente,
    )

    db.session.add(registro)
    if commit:
        db.session.commit()

    return registro
