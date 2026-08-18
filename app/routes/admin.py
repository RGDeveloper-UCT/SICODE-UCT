import platform
import shutil

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, text
from werkzeug.security import generate_password_hash

from app import db
from app.forms.usuario_admin_form import (
    CambiarPasswordUsuarioForm,
    UsuarioCrearForm,
    UsuarioEditarForm,
)
from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.usuario import Usuario
from app.security import admin_required
from app.services.backup_service import (
    BackupError,
    generar_backup as generar_backup_db,
    listar_backups,
    obtener_directorio_backups,
    resolver_backup,
)
from app.services.bitacora_service import registrar_bitacora


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _normalizar_usuario(valor):
    return (valor or "").strip().lower()


def _normalizar_correo(valor):
    texto = (valor or "").strip().lower()
    return texto or None


def _administradores_activos():
    return Usuario.query.filter_by(rol="administrador", activo=True).count()


@admin_bp.route("/usuarios")
@login_required
@admin_required
def usuarios():
    busqueda = request.args.get("q", "").strip()
    filtro_rol = request.args.get("rol", "").strip()
    filtro_activo = request.args.get("activo", "").strip()

    consulta = Usuario.query
    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(or_(
            Usuario.nombre.ilike(filtro),
            Usuario.usuario.ilike(filtro),
            Usuario.correo.ilike(filtro),
        ))
    if filtro_rol:
        consulta = consulta.filter(Usuario.rol == filtro_rol)
    if filtro_activo == "activo":
        consulta = consulta.filter(Usuario.activo.is_(True))
    elif filtro_activo == "inactivo":
        consulta = consulta.filter(Usuario.activo.is_(False))

    return render_template(
        "admin/usuarios.html",
        usuarios=consulta.order_by(Usuario.nombre.asc()).all(),
        busqueda=busqueda,
        filtro_rol=filtro_rol,
        filtro_activo=filtro_activo,
    )


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo_usuario():
    form = UsuarioCrearForm()
    if form.validate_on_submit():
        usuario_texto = _normalizar_usuario(form.usuario.data)
        correo = _normalizar_correo(form.correo.data)

        if Usuario.query.filter_by(usuario=usuario_texto).first():
            flash("Ya existe un usuario con ese nombre de usuario.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="crear")
        if correo and Usuario.query.filter_by(correo=correo).first():
            flash("Ya existe un usuario con ese correo.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="crear")

        nuevo = Usuario(
            nombre=form.nombre.data.strip(),
            usuario=usuario_texto,
            correo=correo,
            rol=form.rol.data,
            activo=True,
            password_hash=generate_password_hash(form.password.data, method="pbkdf2:sha256"),
        )
        db.session.add(nuevo)
        db.session.flush()
        registrar_bitacora(
            accion="CREAR_USUARIO",
            modulo="Administración",
            descripcion=f"Se creó el usuario {nuevo.usuario} con rol {nuevo.rol}; contraseña temporal obligatoria.",
            usuario_id=current_user.id,
            entidad="Usuario",
            entidad_id=nuevo.id,
            datos_posteriores={"usuario": nuevo.usuario, "rol": nuevo.rol, "activo": True, "debe_cambiar_password": True},
            commit=False,
        )
        db.session.commit()
        flash("Usuario creado. Deberá cambiar su contraseña temporal al iniciar sesión.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/formulario_usuario.html", form=form, modo="crear")


@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    form = UsuarioEditarForm(obj=usuario)

    if form.validate_on_submit():
        nuevo_usuario = _normalizar_usuario(form.usuario.data)
        nuevo_correo = _normalizar_correo(form.correo.data)
        nuevo_rol = form.rol.data

        if Usuario.query.filter(Usuario.usuario == nuevo_usuario, Usuario.id != usuario.id).first():
            flash("Ya existe otro usuario con ese nombre de usuario.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)
        if nuevo_correo and Usuario.query.filter(Usuario.correo == nuevo_correo, Usuario.id != usuario.id).first():
            flash("Ya existe otro usuario con ese correo.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)

        if usuario.rol == "administrador" and usuario.activo and nuevo_rol != "administrador" and _administradores_activos() <= 1:
            flash("No puede quitar el rol al último administrador activo.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)

        anteriores = {"nombre": usuario.nombre, "usuario": usuario.usuario, "correo": usuario.correo, "rol": usuario.rol}
        usuario.nombre = form.nombre.data.strip()
        usuario.usuario = nuevo_usuario
        usuario.correo = nuevo_correo
        usuario.rol = nuevo_rol

        registrar_bitacora(
            accion="EDITAR_USUARIO",
            modulo="Administración",
            descripcion=f"Se editó el usuario {usuario.usuario}.",
            usuario_id=current_user.id,
            entidad="Usuario",
            entidad_id=usuario.id,
            datos_anteriores=anteriores,
            datos_posteriores={"nombre": usuario.nombre, "usuario": usuario.usuario, "correo": usuario.correo, "rol": usuario.rol},
            commit=False,
        )
        db.session.commit()
        flash("Usuario actualizado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)


@admin_bp.route("/usuarios/<int:usuario_id>/password", methods=["GET", "POST"])
@login_required
@admin_required
def cambiar_password_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    form = CambiarPasswordUsuarioForm()
    if form.validate_on_submit():
        usuario.password_hash = generate_password_hash(form.password.data, method="pbkdf2:sha256")
        # El validador del modelo marca la nueva credencial como temporal.
        registrar_bitacora(
            accion="CAMBIAR_PASSWORD_USUARIO",
            modulo="Administración",
            descripcion=f"Se asignó una nueva contraseña temporal al usuario {usuario.usuario}.",
            usuario_id=current_user.id,
            entidad="Usuario",
            entidad_id=usuario.id,
            datos_posteriores={"debe_cambiar_password": True},
            commit=False,
        )
        db.session.commit()
        flash("Contraseña temporal actualizada. El usuario deberá cambiarla en su próximo acceso.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/cambiar_password.html", form=form, usuario=usuario)


@admin_bp.route("/usuarios/<int:usuario_id>/desactivar", methods=["POST"])
@login_required
@admin_required
def desactivar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)

    if usuario.id == current_user.id:
        flash("No puede desactivar su propio usuario mientras está en sesión.", "danger")
        return redirect(url_for("admin.usuarios"))
    if usuario.rol == "administrador" and usuario.activo and _administradores_activos() <= 1:
        flash("No puede desactivar al último administrador activo.", "danger")
        return redirect(url_for("admin.usuarios"))

    usuario.activo = False
    registrar_bitacora(
        accion="DESACTIVAR_USUARIO",
        modulo="Administración",
        descripcion=f"Se desactivó el usuario {usuario.usuario}.",
        usuario_id=current_user.id,
        entidad="Usuario",
        entidad_id=usuario.id,
        datos_anteriores={"activo": True},
        datos_posteriores={"activo": False},
        commit=False,
    )
    db.session.commit()
    flash("Usuario desactivado correctamente.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/<int:usuario_id>/reactivar", methods=["POST"])
@login_required
@admin_required
def reactivar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    usuario.activo = True
    registrar_bitacora(
        accion="REACTIVAR_USUARIO",
        modulo="Administración",
        descripcion=f"Se reactivó el usuario {usuario.usuario}.",
        usuario_id=current_user.id,
        entidad="Usuario",
        entidad_id=usuario.id,
        datos_anteriores={"activo": False},
        datos_posteriores={"activo": True},
        commit=False,
    )
    db.session.commit()
    flash("Usuario reactivado correctamente.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/backups")
@login_required
@admin_required
def backups():
    return render_template("admin/backups.html", archivos=listar_backups())


@admin_bp.route("/backups/generar", methods=["POST"])
@login_required
@admin_required
def generar_backup():
    try:
        ruta = generar_backup_db(current_app.config.get("SQLALCHEMY_DATABASE_URI"))
    except BackupError as error:
        flash(str(error), "danger")
        return redirect(url_for("admin.backups"))

    registrar_bitacora(
        accion="GENERAR_BACKUP_DB",
        modulo="Administración",
        descripcion=f"Se generó y validó el respaldo de base de datos: {ruta.name}.",
        usuario_id=current_user.id,
        entidad="Backup",
        entidad_id=ruta.name,
    )
    flash("Respaldo generado y validado correctamente.", "success")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/backups/<nombre_archivo>/descargar")
@login_required
@admin_required
def descargar_backup(nombre_archivo):
    try:
        ruta = resolver_backup(nombre_archivo)
    except BackupError as error:
        flash(str(error), "danger")
        return redirect(url_for("admin.backups"))

    registrar_bitacora(
        accion="DESCARGAR_BACKUP_DB",
        modulo="Administración",
        descripcion=f"Se descargó respaldo de base de datos: {ruta.name}.",
        usuario_id=current_user.id,
        entidad="Backup",
        entidad_id=ruta.name,
    )
    return send_file(ruta, as_attachment=True, download_name=ruta.name, mimetype="application/sql")


@admin_bp.route("/sistema")
@login_required
@admin_required
def sistema():
    estado_db = "Correcta"
    detalle_db = "Conexión activa con PostgreSQL."
    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error de PostgreSQL al consultar estado del sistema")
        estado_db = "Error"
        detalle_db = "No fue posible validar PostgreSQL. Revise el log del servidor."

    archivos = listar_backups()
    ultimo_backup = archivos[0] if archivos else None
    directorio_backups = obtener_directorio_backups()
    uso_disco = shutil.disk_usage(directorio_backups)

    indicadores = {
        "usuarios": Usuario.query.count(),
        "usuarios_activos": Usuario.query.filter_by(activo=True).count(),
        "expedientes": Expediente.query.count(),
        "expedientes_activos": Expediente.query.filter_by(activo=True).count(),
        "alertas": Alerta.query.count(),
        "alertas_abiertas": Alerta.query.filter_by(estado="Abierta").count(),
        "prestamos": PrestamoExpediente.query.count(),
        "prestamos_activos": PrestamoExpediente.query.filter_by(estado="En préstamo").count(),
        "eventos_bitacora": Bitacora.query.count(),
        "backups": len(archivos),
    }

    registrar_bitacora(
        accion="CONSULTAR_ESTADO_SISTEMA",
        modulo="Administración",
        descripcion="Se consultó el panel de estado del sistema.",
        usuario_id=current_user.id,
    )

    return render_template(
        "admin/sistema.html",
        estado_db=estado_db,
        detalle_db=detalle_db,
        indicadores=indicadores,
        directorio_backups=directorio_backups,
        ultimo_backup=ultimo_backup,
        espacio_total_gb=round(uso_disco.total / (1024 ** 3), 2),
        espacio_usado_gb=round(uso_disco.used / (1024 ** 3), 2),
        espacio_libre_gb=round(uso_disco.free / (1024 ** 3), 2),
        version_python=platform.python_version(),
    )
