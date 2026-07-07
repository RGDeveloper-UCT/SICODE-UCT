from flask import request
from app import db
from app.models.bitacora import Bitacora

def registrar_bitacora(accion, modulo, descripcion=None, usuario_id=None, expediente_id=None):
    ip_origen = request.remote_addr if request else None

    registro = Bitacora(
        usuario_id=usuario_id,
        expediente_id=expediente_id,
        accion=accion,
        modulo=modulo,
        descripcion=descripcion,
        ip_origen=ip_origen,
    )

    db.session.add(registro)
    db.session.commit()

    return registro
