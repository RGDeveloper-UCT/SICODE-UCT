from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.forms.expediente_form import ExpedienteForm
from app.models.expediente import Expediente
from app.models.ubicacion import UbicacionFisica
from app.services.bitacora_service import registrar_bitacora

expedientes_bp = Blueprint("expedientes", __name__)

@expedientes_bp.route("/expedientes")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()

    consulta = Expediente.query

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
            )
        )

    expedientes = consulta.order_by(Expediente.creado_en.desc()).all()

    return render_template(
        "expedientes/listado.html",
        expedientes=expedientes,
        busqueda=busqueda,
    )

@expedientes_bp.route("/expedientes/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    form = ExpedienteForm()

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = Expediente.query.filter_by(codigo_interno=codigo_interno).first()
        existe_sp = Expediente.query.filter_by(no_sp=no_sp).first()

        if existe_codigo:
            flash("Ya existe un expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        if existe_sp:
            flash("Ya existe un expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        expediente = Expediente(
            codigo_interno=codigo_interno,
            no_sp=no_sp,
            nombre_referencia=form.nombre_referencia.data.strip() if form.nombre_referencia.data else None,
            estado_administrativo=form.estado_administrativo.data,
            estado_fisico_documental=form.estado_fisico_documental.data,
            observaciones=form.observaciones.data,
            activo=True,
        )

        db.session.add(expediente)
        db.session.flush()

        ubicacion = UbicacionFisica(
            expediente_id=expediente.id,
            archivador=form.archivador.data,
            sicoin=form.sicoin.data,
            estante=form.estante.data,
            caja=form.caja.data,
            modulo=form.modulo.data,
            posicion=form.posicion.data,
            observaciones=form.observaciones.data,
        )

        db.session.add(ubicacion)
        db.session.commit()

        registrar_bitacora(
            accion="CREAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se creó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Expediente creado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

@expedientes_bp.route("/expedientes/<int:expediente_id>")
@login_required
def detalle(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    return render_template(
        "expedientes/detalle.html",
        expediente=expediente,
        ubicacion=ubicacion,
    )
