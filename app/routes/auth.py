from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.forms.login_form import LoginForm
from app.models.bitacora import Bitacora
from app.models.usuario import Usuario
from app.security import es_url_interna
from app.services.bitacora_service import registrar_bitacora
from app.services.presencia_service import cerrar_presencia


auth_bp = Blueprint("auth", __name__)

MAX_INTENTOS_LOGIN = 5
VENTANA_LOGIN_MINUTOS = 5


def _login_temporalmente_limitado(usuario_texto):
    desde = datetime.utcnow() - timedelta(minutes=VENTANA_LOGIN_MINUTOS)
    ip = request.remote_addr
    consulta = Bitacora.query.filter(
        Bitacora.accion == "LOGIN_FALLIDO",
        Bitacora.entidad == "Autenticacion",
        Bitacora.entidad_id == usuario_texto,
        Bitacora.creado_en >= desde,
    )
    if ip:
        consulta = consulta.filter(Bitacora.ip_origen == ip)
    return consulta.count() >= MAX_INTENTOS_LOGIN


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.inicio"))

    form = LoginForm()

    if form.validate_on_submit():
        usuario_texto = form.usuario.data.strip().lower()
        password = form.password.data

        if _login_temporalmente_limitado(usuario_texto):
            registrar_bitacora(
                accion="LOGIN_BLOQUEADO_RATE_LIMIT",
                modulo="Autenticación",
                descripcion=(
                    f"Acceso temporalmente limitado para el usuario ingresado {usuario_texto} "
                    f"por {MAX_INTENTOS_LOGIN} intentos fallidos dentro de {VENTANA_LOGIN_MINUTOS} minutos."
                ),
                entidad="Autenticacion",
                entidad_id=usuario_texto,
            )
            flash(
                "Se alcanzó el límite temporal de intentos para esta cuenta desde este origen. Intente nuevamente en unos minutos o contacte al administrador.",
                "danger",
            )
            return render_template("auth/login.html", form=form), 429

        usuario = Usuario.query.filter_by(usuario=usuario_texto, activo=True).first()

        if usuario and check_password_hash(usuario.password_hash, password):
            login_user(usuario)
            session.permanent = True

            registrar_bitacora(
                accion="LOGIN_EXITOSO",
                modulo="Autenticación",
                descripcion=f"Inicio de sesión exitoso para el usuario {usuario.usuario}.",
                usuario_id=usuario.id,
                entidad="Autenticacion",
                entidad_id=usuario.usuario,
            )

            flash("Inicio de sesión correcto.", "success")

            siguiente = request.args.get("next")
            if siguiente and es_url_interna(siguiente):
                return redirect(siguiente)

            return redirect(url_for("dashboard.inicio"))

        registrar_bitacora(
            accion="LOGIN_FALLIDO",
            modulo="Autenticación",
            descripcion=f"Intento fallido de inicio de sesión para el usuario ingresado: {usuario_texto}.",
            usuario_id=usuario.id if usuario else None,
            entidad="Autenticacion",
            entidad_id=usuario_texto,
        )

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    usuario_id = current_user.id
    usuario_nombre = current_user.usuario

    registrar_bitacora(
        accion="LOGOUT",
        modulo="Autenticación",
        descripcion=f"Cierre de sesión del usuario {usuario_nombre}.",
        usuario_id=usuario_id,
        entidad="Autenticacion",
        entidad_id=usuario_nombre,
    )

    cerrar_presencia(usuario_id)
    logout_user()
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
