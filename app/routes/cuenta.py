from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.forms.cuenta_form import CambiarPasswordPropiaForm
from app.services.bitacora_service import registrar_bitacora


cuenta_bp = Blueprint("cuenta", __name__, url_prefix="/mi-cuenta")


@cuenta_bp.route("/")
@login_required
def detalle():
    return render_template("cuenta/detalle.html")


@cuenta_bp.route("/cambiar-password", methods=["GET", "POST"])
@login_required
def cambiar_password():
    form = CambiarPasswordPropiaForm()

    if form.validate_on_submit():
        if not check_password_hash(current_user.password_hash, form.password_actual.data):
            flash("La contraseña actual no es correcta.", "danger")
            registrar_bitacora(
                accion="CAMBIO_PASSWORD_PROPIO_FALLIDO",
                modulo="Mi cuenta",
                descripcion=f"Intento fallido de cambio de contraseña del usuario {current_user.usuario}.",
                usuario_id=current_user.id,
            )
            return render_template("cuenta/cambiar_password.html", form=form)

        current_user.password_hash = generate_password_hash(form.nueva_password.data, method="pbkdf2:sha256")
        # El validador del modelo marca toda asignación como temporal. En este
        # flujo el propio usuario la eligió y por eso queda como definitiva.
        current_user.debe_cambiar_password = False

        registrar_bitacora(
            accion="CAMBIAR_PASSWORD_PROPIO",
            modulo="Mi cuenta",
            descripcion=f"El usuario {current_user.usuario} cambió su propia contraseña.",
            usuario_id=current_user.id,
            entidad="Usuario",
            entidad_id=current_user.id,
            datos_posteriores={"debe_cambiar_password": False},
            commit=False,
        )
        db.session.commit()

        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("cuenta.detalle"))

    return render_template(
        "cuenta/cambiar_password.html",
        form=form,
        cambio_obligatorio=current_user.debe_cambiar_password,
    )
