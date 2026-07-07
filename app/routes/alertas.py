from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.models.alerta import Alerta
from app.models.expediente import Expediente
from app.models.documento_expediente import DocumentoExpediente
from app.services.bitacora_service import registrar_bitacora

alertas_bp = Blueprint("alertas", __name__)

@alertas_bp.route("/alertas")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()
    filtro_gravedad = request.args.get("gravedad", "").strip()
    filtro_tipo = request.args.get("tipo", "").strip()

    consulta = (
        Alerta.query
        .join(Expediente, Alerta.expediente_id == Expediente.id)
        .outerjoin(DocumentoExpediente, Alerta.documento_id == DocumentoExpediente.id)
    )

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Alerta.titulo.ilike(filtro),
                Alerta.descripcion.ilike(filtro),
                Alerta.tipo_alerta.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                DocumentoExpediente.nombre_documento.ilike(filtro),
            )
        )

    if filtro_estado:
        consulta = consulta.filter(Alerta.estado == filtro_estado)

    if filtro_gravedad:
        consulta = consulta.filter(Alerta.gravedad == filtro_gravedad)

    if filtro_tipo:
        consulta = consulta.filter(Alerta.tipo_alerta == filtro_tipo)

    alertas = consulta.order_by(Alerta.creado_en.desc()).limit(150).all()

    estados = ["Abierta", "En revisión", "Corregida", "Cerrada"]
    gravedades = ["Alta", "Media", "Baja"]

    tipos = [
        tipo[0]
        for tipo in Alerta.query.with_entities(Alerta.tipo_alerta)
        .distinct()
        .order_by(Alerta.tipo_alerta.asc())
        .all()
    ]

    return render_template(
        "alertas/listado.html",
        alertas=alertas,
        busqueda=busqueda,
        filtro_estado=filtro_estado,
        filtro_gravedad=filtro_gravedad,
        filtro_tipo=filtro_tipo,
        estados=estados,
        gravedades=gravedades,
        tipos=tipos,
    )

@alertas_bp.route("/alertas/<int:alerta_id>/estado/<nuevo_estado>", methods=["POST"])
@login_required
def cambiar_estado(alerta_id, nuevo_estado):
    alerta = Alerta.query.get_or_404(alerta_id)

    estados_permitidos = ["Abierta", "En revisión", "Corregida", "Cerrada"]

    if nuevo_estado not in estados_permitidos:
        flash("Estado de alerta no permitido.", "danger")
        return redirect(url_for("alertas.listado"))

    estado_anterior = alerta.estado
    alerta.estado = nuevo_estado

    if nuevo_estado == "Cerrada":
        alerta.cerrado_en = datetime.utcnow()
        alerta.cerrada_por_id = current_user.id
    else:
        alerta.cerrado_en = None
        alerta.cerrada_por_id = None

    db.session.commit()

    registrar_bitacora(
        accion="CAMBIAR_ESTADO_ALERTA",
        modulo="Alertas",
        descripcion=f"Se cambió la alerta '{alerta.titulo}' de '{estado_anterior}' a '{nuevo_estado}'.",
        usuario_id=current_user.id,
        expediente_id=alerta.expediente_id,
    )

    flash("Estado de alerta actualizado correctamente.", "success")
    return redirect(url_for("alertas.listado"))
