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

@expedientes_bp.route("/expedientes/<int:expediente_id>/editar", methods=["GET", "POST"])
@login_required
def editar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    form = ExpedienteForm()
    form.submit.label.text = "Actualizar expediente"

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = (
            Expediente.query
            .filter(Expediente.codigo_interno == codigo_interno, Expediente.id != expediente.id)
            .first()
        )

        existe_sp = (
            Expediente.query
            .filter(Expediente.no_sp == no_sp, Expediente.id != expediente.id)
            .first()
        )

        if existe_codigo:
            flash("Ya existe otro expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        if existe_sp:
            flash("Ya existe otro expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        expediente.codigo_interno = codigo_interno
        expediente.no_sp = no_sp
        expediente.nombre_referencia = form.nombre_referencia.data.strip() if form.nombre_referencia.data else None
        expediente.estado_administrativo = form.estado_administrativo.data
        expediente.estado_fisico_documental = form.estado_fisico_documental.data
        expediente.observaciones = form.observaciones.data

        if not ubicacion:
            ubicacion = UbicacionFisica(expediente_id=expediente.id)
            db.session.add(ubicacion)

        ubicacion.archivador = form.archivador.data
        ubicacion.sicoin = form.sicoin.data
        ubicacion.estante = form.estante.data
        ubicacion.caja = form.caja.data
        ubicacion.modulo = form.modulo.data
        ubicacion.posicion = form.posicion.data
        ubicacion.observaciones = form.observaciones.data

        db.session.commit()

        registrar_bitacora(
            accion="EDITAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se actualizó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Expediente actualizado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    if request.method == "GET":
        form.codigo_interno.data = expediente.codigo_interno
        form.no_sp.data = expediente.no_sp
        form.nombre_referencia.data = expediente.nombre_referencia
        form.estado_administrativo.data = expediente.estado_administrativo
        form.estado_fisico_documental.data = expediente.estado_fisico_documental
        form.observaciones.data = expediente.observaciones

        if ubicacion:
            form.archivador.data = ubicacion.archivador
            form.sicoin.data = ubicacion.sicoin
            form.estante.data = ubicacion.estante
            form.caja.data = ubicacion.caja
            form.modulo.data = ubicacion.modulo
            form.posicion.data = ubicacion.posicion

    return render_template("expedientes/formulario.html", form=form, modo="Editar")

@expedientes_bp.route("/expedientes/<int:expediente_id>/desactivar", methods=["POST"])
@login_required
def desactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("El expediente ya se encuentra desactivado.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = False
    db.session.commit()

    registrar_bitacora(
        accion="DESACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se desactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente desactivado correctamente. El registro se conserva para trazabilidad.", "info")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

@expedientes_bp.route("/expedientes/<int:expediente_id>/reactivar", methods=["POST"])
@login_required
def reactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if expediente.activo:
        flash("El expediente ya se encuentra activo.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = True
    db.session.commit()

    registrar_bitacora(
        accion="REACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se reactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente reactivado correctamente.", "success")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))
