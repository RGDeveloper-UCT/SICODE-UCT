from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.expediente_form import RegistrarExpedienteFisicoForm
from app.models.expediente import Expediente
from app.models.ubicacion import UbicacionFisica
from app.services.alertas_service import crear_alerta_si_no_existe
from app.services.bitacora_service import registrar_bitacora


expediente_fisico_bp = Blueprint("expediente_fisico", __name__, url_prefix="/expedientes")


@expediente_fisico_bp.route("/pendientes-fisicos")
@login_required
def pendientes():
    registros = (
        Expediente.query
        .filter_by(expediente_fisico_registrado=False)
        .order_by(Expediente.no_sp.asc())
        .all()
    )
    return render_template("expedientes/pendientes_fisicos.html", registros=registros)


@expediente_fisico_bp.route("/<int:expediente_id>/registrar-fisico", methods=["GET", "POST"])
@login_required
def registrar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if expediente.expediente_fisico_registrado:
        flash("Este SP ya tiene expediente físico registrado.", "info")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    form = RegistrarExpedienteFisicoForm()

    if form.validate_on_submit():
        anteriores = {
            "expediente_fisico_registrado": False,
            "estado_administrativo": expediente.estado_administrativo,
            "estado_fisico_documental": expediente.estado_fisico_documental,
        }

        expediente.expediente_fisico_registrado = True
        expediente.estado_administrativo = form.estado_administrativo.data
        expediente.estado_fisico_documental = form.estado_fisico_documental.data
        if form.observaciones.data:
            expediente.observaciones = form.observaciones.data

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

        registrar_bitacora(
            accion="REGISTRAR_EXPEDIENTE_FISICO",
            modulo="Expedientes",
            descripcion=f"Se registró la existencia física del expediente del SP {expediente.no_sp}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="Expediente",
            entidad_id=expediente.id,
            datos_anteriores=anteriores,
            datos_posteriores={
                "expediente_fisico_registrado": True,
                "estado_administrativo": expediente.estado_administrativo,
                "estado_fisico_documental": expediente.estado_fisico_documental,
            },
            commit=False,
        )
        db.session.commit()

        if expediente.estado_fisico_documental in {"Con observaciones", "Incompleto", "No localizado"}:
            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                tipo_alerta="REVISION_EXPEDIENTE",
                titulo=f"Expediente requiere revisión: {expediente.no_sp}",
                descripcion=f"El expediente físico fue registrado con estado: {expediente.estado_fisico_documental}.",
                gravedad="Alta" if expediente.estado_fisico_documental == "No localizado" else "Media",
                usuario_id=current_user.id,
            )

        flash("Expediente físico registrado sin duplicar el SP.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    return render_template("expedientes/registrar_fisico.html", expediente=expediente, form=form)
