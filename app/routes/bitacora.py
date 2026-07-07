from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from app.models.bitacora import Bitacora
from app.models.usuario import Usuario
from app.models.expediente import Expediente

bitacora_bp = Blueprint("bitacora", __name__)

@bitacora_bp.route("/bitacora")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_accion = request.args.get("accion", "").strip()
    filtro_modulo = request.args.get("modulo", "").strip()
    filtro_usuario = request.args.get("usuario", "").strip()

    consulta = (
        Bitacora.query
        .outerjoin(Usuario, Bitacora.usuario_id == Usuario.id)
        .outerjoin(Expediente, Bitacora.expediente_id == Expediente.id)
    )

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Bitacora.descripcion.ilike(filtro),
                Bitacora.accion.ilike(filtro),
                Bitacora.modulo.ilike(filtro),
                Usuario.usuario.ilike(filtro),
                Usuario.nombre.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
            )
        )

    if filtro_accion:
        consulta = consulta.filter(Bitacora.accion == filtro_accion)

    if filtro_modulo:
        consulta = consulta.filter(Bitacora.modulo == filtro_modulo)

    if filtro_usuario:
        consulta = consulta.filter(Usuario.usuario == filtro_usuario)

    eventos = consulta.order_by(Bitacora.creado_en.desc()).limit(100).all()

    acciones = [
        accion[0]
        for accion in Bitacora.query.with_entities(Bitacora.accion)
        .distinct()
        .order_by(Bitacora.accion.asc())
        .all()
    ]

    modulos = [
        modulo[0]
        for modulo in Bitacora.query.with_entities(Bitacora.modulo)
        .distinct()
        .order_by(Bitacora.modulo.asc())
        .all()
    ]

    usuarios = Usuario.query.order_by(Usuario.nombre.asc()).all()

    return render_template(
        "bitacora/listado.html",
        eventos=eventos,
        busqueda=busqueda,
        filtro_accion=filtro_accion,
        filtro_modulo=filtro_modulo,
        filtro_usuario=filtro_usuario,
        acciones=acciones,
        modulos=modulos,
        usuarios=usuarios,
    )
