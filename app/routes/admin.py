import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.security import generate_password_hash

from app import db
from app.models.usuario import Usuario
from app.forms.usuario_admin_form import (
    UsuarioCrearForm,
    UsuarioEditarForm,
    CambiarPasswordUsuarioForm,
)
from app.services.bitacora_service import registrar_bitacora

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(funcion):
    @wraps(funcion)
    def wrapper(*args, **kwargs):
        if current_user.rol != "administrador":
            flash("No tiene permisos para acceder a este módulo.", "danger")
            return redirect(url_for("dashboard.inicio"))
        return funcion(*args, **kwargs)
    return wrapper


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
        consulta = consulta.filter(
            or_(
                Usuario.nombre.ilike(filtro),
                Usuario.usuario.ilike(filtro),
                Usuario.correo.ilike(filtro),
            )
        )

    if filtro_rol:
        consulta = consulta.filter(Usuario.rol == filtro_rol)

    if filtro_activo == "activo":
        consulta = consulta.filter(Usuario.activo == True)

    elif filtro_activo == "inactivo":
        consulta = consulta.filter(Usuario.activo == False)

    usuarios = consulta.order_by(Usuario.nombre.asc()).all()

    return render_template(
        "admin/usuarios.html",
        usuarios=usuarios,
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
        usuario_existente = Usuario.query.filter_by(usuario=form.usuario.data.strip()).first()

        if usuario_existente:
            flash("Ya existe un usuario con ese nombre de usuario.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="crear")

        correo_limpio = form.correo.data.strip() if form.correo.data else None

        if correo_limpio:
            correo_existente = Usuario.query.filter_by(correo=correo_limpio).first()
            if correo_existente:
                flash("Ya existe un usuario con ese correo.", "danger")
                return render_template("admin/formulario_usuario.html", form=form, modo="crear")

        nuevo = Usuario(
            nombre=form.nombre.data.strip(),
            usuario=form.usuario.data.strip(),
            correo=correo_limpio,
            rol=form.rol.data,
            activo=True,
            password_hash=generate_password_hash(form.password.data, method="pbkdf2:sha256"),
        )

        db.session.add(nuevo)
        db.session.commit()

        registrar_bitacora(
            accion="CREAR_USUARIO",
            modulo="Administración",
            descripcion=f"Se creó el usuario {nuevo.usuario} con rol {nuevo.rol}.",
            usuario_id=current_user.id,
        )

        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("admin.usuarios"))

    return render_template("admin/formulario_usuario.html", form=form, modo="crear")


@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    form = UsuarioEditarForm(obj=usuario)

    if form.validate_on_submit():
        usuario_existente = (
            Usuario.query
            .filter(Usuario.usuario == form.usuario.data.strip(), Usuario.id != usuario.id)
            .first()
        )

        if usuario_existente:
            flash("Ya existe otro usuario con ese nombre de usuario.", "danger")
            return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)

        correo_limpio = form.correo.data.strip() if form.correo.data else None

        if correo_limpio:
            correo_existente = (
                Usuario.query
                .filter(Usuario.correo == correo_limpio, Usuario.id != usuario.id)
                .first()
            )

            if correo_existente:
                flash("Ya existe otro usuario con ese correo.", "danger")
                return render_template("admin/formulario_usuario.html", form=form, modo="editar", usuario=usuario)

        usuario.nombre = form.nombre.data.strip()
        usuario.usuario = form.usuario.data.strip()
        usuario.correo = correo_limpio
        usuario.rol = form.rol.data

        db.session.commit()

        registrar_bitacora(
            accion="EDITAR_USUARIO",
            modulo="Administración",
            descripcion=f"Se editó el usuario {usuario.usuario}.",
            usuario_id=current_user.id,
        )

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
        db.session.commit()

        registrar_bitacora(
            accion="CAMBIAR_PASSWORD_USUARIO",
            modulo="Administración",
            descripcion=f"Se actualizó la contraseña temporal del usuario {usuario.usuario}.",
            usuario_id=current_user.id,
        )

        flash("Contraseña actualizada correctamente.", "success")
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

    usuario.activo = False
    db.session.commit()

    registrar_bitacora(
        accion="DESACTIVAR_USUARIO",
        modulo="Administración",
        descripcion=f"Se desactivó el usuario {usuario.usuario}.",
        usuario_id=current_user.id,
    )

    flash("Usuario desactivado correctamente.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/<int:usuario_id>/reactivar", methods=["POST"])
@login_required
@admin_required
def reactivar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)

    usuario.activo = True
    db.session.commit()

    registrar_bitacora(
        accion="REACTIVAR_USUARIO",
        modulo="Administración",
        descripcion=f"Se reactivó el usuario {usuario.usuario}.",
        usuario_id=current_user.id,
    )

    flash("Usuario reactivado correctamente.", "success")
    return redirect(url_for("admin.usuarios"))


def obtener_directorio_backups():
    directorio = Path(current_app.root_path).parent / "backups"
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio


@admin_bp.route("/backups")
@login_required
@admin_required
def backups():
    directorio = obtener_directorio_backups()

    archivos = []

    for archivo in directorio.glob("backup_sicode_uct_*.sql"):
        stat = archivo.stat()
        archivos.append({
            "nombre": archivo.name,
            "tamano_mb": round(stat.st_size / (1024 * 1024), 2),
            "modificado": datetime.fromtimestamp(stat.st_mtime),
        })

    archivos = sorted(archivos, key=lambda item: item["modificado"], reverse=True)

    return render_template("admin/backups.html", archivos=archivos)


@admin_bp.route("/backups/generar", methods=["POST"])
@login_required
@admin_required
def generar_backup():
    database_url = (
        current_app.config.get("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_URL")
    )

    if not database_url:
        flash("No se encontró la configuración de conexión a la base de datos.", "danger")
        return redirect(url_for("admin.backups"))

    pg_dump_path = shutil.which("pg_dump")

    if not pg_dump_path:
        flash("No se encontró pg_dump en el sistema. Verifique la instalación de PostgreSQL.", "danger")
        return redirect(url_for("admin.backups"))

    directorio = obtener_directorio_backups()
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"backup_sicode_uct_{marca_tiempo}.sql"
    ruta_backup = directorio / nombre_archivo

    comando = [
        pg_dump_path,
        "--dbname", database_url,
        "--file", str(ruta_backup),
        "--format", "plain",
        "--encoding", "UTF8",
        "--no-owner",
        "--no-privileges",
    ]

    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=180,
        )

    except subprocess.TimeoutExpired:
        flash("El respaldo tardó demasiado y fue cancelado.", "danger")
        return redirect(url_for("admin.backups"))

    except Exception as error:
        flash(f"No se pudo generar el respaldo: {error}", "danger")
        return redirect(url_for("admin.backups"))

    if resultado.returncode != 0:
        mensaje_error = resultado.stderr or "Error desconocido al ejecutar pg_dump."
        flash(f"No se pudo generar el respaldo: {mensaje_error}", "danger")
        return redirect(url_for("admin.backups"))

    registrar_bitacora(
        accion="GENERAR_BACKUP_DB",
        modulo="Administración",
        descripcion=f"Se generó respaldo de base de datos: {nombre_archivo}.",
        usuario_id=current_user.id,
    )

    flash("Respaldo generado correctamente.", "success")
    return redirect(url_for("admin.backups"))


@admin_bp.route("/backups/<nombre_archivo>/descargar")
@login_required
@admin_required
def descargar_backup(nombre_archivo):
    if not nombre_archivo.startswith("backup_sicode_uct_") or not nombre_archivo.endswith(".sql"):
        flash("Nombre de archivo no permitido.", "danger")
        return redirect(url_for("admin.backups"))

    directorio = obtener_directorio_backups()
    ruta_backup = (directorio / nombre_archivo).resolve()

    if ruta_backup.parent != directorio.resolve():
        flash("Ruta de archivo no permitida.", "danger")
        return redirect(url_for("admin.backups"))

    if not ruta_backup.exists():
        flash("El respaldo solicitado no existe.", "danger")
        return redirect(url_for("admin.backups"))

    registrar_bitacora(
        accion="DESCARGAR_BACKUP_DB",
        modulo="Administración",
        descripcion=f"Se descargó respaldo de base de datos: {nombre_archivo}.",
        usuario_id=current_user.id,
    )

    return send_file(
        ruta_backup,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/sql",
    )
