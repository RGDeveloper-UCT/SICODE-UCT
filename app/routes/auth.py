from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.models.usuario import Usuario
from app.forms.login_form import LoginForm
from app.services.bitacora_service import registrar_bitacora

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.inicio"))

    form = LoginForm()

    if form.validate_on_submit():
        usuario_texto = form.usuario.data.strip().lower()
        password = form.password.data

        usuario = Usuario.query.filter_by(usuario=usuario_texto, activo=True).first()

        if usuario and check_password_hash(usuario.password_hash, password):
            login_user(usuario)

            registrar_bitacora(
                accion="LOGIN_EXITOSO",
                modulo="Autenticación",
                descripcion=f"Inicio de sesión exitoso para el usuario {usuario.usuario}.",
                usuario_id=usuario.id,
            )

            flash("Inicio de sesión correcto.", "success")

            siguiente = request.args.get("next")
            if siguiente:
                return redirect(siguiente)

            return redirect(url_for("dashboard.inicio"))

        registrar_bitacora(
            accion="LOGIN_FALLIDO",
            modulo="Autenticación",
            descripcion=f"Intento fallido de inicio de sesión para el usuario ingresado: {usuario_texto}.",
            usuario_id=usuario.id if usuario else None,
        )

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("auth/login.html", form=form)

@auth_bp.route("/logout")
@login_required
def logout():
    usuario_id = current_user.id
    usuario_nombre = current_user.usuario

    registrar_bitacora(
        accion="LOGOUT",
        modulo="Autenticación",
        descripcion=f"Cierre de sesión del usuario {usuario_nombre}.",
        usuario_id=usuario_id,
    )

    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
