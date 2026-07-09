from datetime import datetime
import re

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.forms.prestamo_form import PrestamoForm, DevolucionForm
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.services.bitacora_service import registrar_bitacora

prestamos_bp = Blueprint("prestamos", __name__)

def generar_numero_control(expediente):
    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PRE-{no_sp_limpio}-{marca_tiempo}"

@prestamos_bp.route("/prestamos")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()

    consulta = PrestamoExpediente.query.join(Expediente)

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                PrestamoExpediente.numero_control.ilike(filtro),
                PrestamoExpediente.solicitante.ilike(filtro),
                PrestamoExpediente.persona_entrega.ilike(filtro),
                PrestamoExpediente.persona_recibe.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
            )
        )

    if filtro_estado:
        consulta = consulta.filter(PrestamoExpediente.estado == filtro_estado)

    prestamos = consulta.order_by(PrestamoExpediente.fecha_prestamo.desc()).limit(150).all()

    estados = ["En préstamo", "Devuelto"]

    return render_template(
        "prestamos/listado.html",
        prestamos=prestamos,
        busqueda=busqueda,
        filtro_estado=filtro_estado,
        estados=estados,
    )

@prestamos_bp.route("/expedientes/<int:expediente_id>/prestamos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("No se puede prestar un expediente inactivo.", "danger")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    prestamo_abierto = (
        PrestamoExpediente.query
        .filter_by(expediente_id=expediente.id, estado="En préstamo")
        .first()
    )

    if prestamo_abierto:
        flash("Este expediente ya tiene un préstamo activo.", "warning")
        return redirect(url_for("prestamos.listado"))

    form = PrestamoForm()

    if form.validate_on_submit():
        prestamo = PrestamoExpediente(
            expediente_id=expediente.id,
            numero_control=generar_numero_control(expediente),
            solicitante=form.solicitante.data.strip(),
            persona_entrega=form.persona_entrega.data.strip(),
            persona_recibe=form.persona_recibe.data.strip(),
            fecha_estimada_devolucion=form.fecha_estimada_devolucion.data,
            estado="En préstamo",
            observaciones=form.observaciones.data,
            activo=True,
        )

        expediente.estado_administrativo = "En préstamo"

        db.session.add(prestamo)
        db.session.commit()

        registrar_bitacora(
            accion="REGISTRAR_PRESTAMO",
            modulo="Préstamos",
            descripcion=(
                f"Se registró préstamo del expediente No. de SP {expediente.no_sp}. "
                f"Número de control: {prestamo.numero_control}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Préstamo registrado correctamente.", "success")
        return redirect(url_for("prestamos.listado"))

    return render_template(
        "prestamos/formulario.html",
        form=form,
        expediente=expediente,
    )

@prestamos_bp.route("/prestamos/<int:prestamo_id>/devolver", methods=["GET", "POST"])
@login_required
def devolver(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    expediente = prestamo.expediente

    if prestamo.estado == "Devuelto":
        flash("Este préstamo ya fue devuelto.", "warning")
        return redirect(url_for("prestamos.listado"))

    form = DevolucionForm()

    if form.validate_on_submit():
        prestamo.estado = "Devuelto"
        prestamo.fecha_real_devolucion = datetime.utcnow()
        prestamo.persona_devuelve = form.persona_devuelve.data.strip()
        prestamo.persona_recibe_devolucion = form.persona_recibe_devolucion.data.strip()
        prestamo.observaciones_devolucion = form.observaciones_devolucion.data

        expediente.estado_administrativo = "Devuelto"

        db.session.commit()

        registrar_bitacora(
            accion="REGISTRAR_DEVOLUCION",
            modulo="Préstamos",
            descripcion=(
                f"Se registró devolución del expediente No. de SP {expediente.no_sp}. "
                f"Número de control: {prestamo.numero_control}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Devolución registrada correctamente.", "success")
        return redirect(url_for("prestamos.listado"))

    return render_template(
        "prestamos/devolver.html",
        form=form,
        prestamo=prestamo,
        expediente=expediente,
    )
