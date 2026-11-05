"""HashPass HP-001: bóvedas privadas con autorización independiente.

Modelo deliberadamente SIN sesión criptográfica persistente: se solicita la
maestra de nuevo para cada operación sensible. No se almacena en cookie,
sesión, Redis, disco ni base de datos. No habilitar sin auditoría institucional.
"""
from datetime import datetime, timedelta
from secrets import choice
from string import ascii_letters, digits, punctuation
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import check_password_hash
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models.bitacora import Bitacora
from app.models.usuario import Usuario
from app.services.bitacora_service import registrar_bitacora
from app.services.hashpass_crypto import (
    abrir_boveda, cifrar_registro, crear_boveda, descifrar_registro, reenvolver_clave,
)

hashpass_bp = Blueprint("hashpass", __name__, url_prefix="/hashpass")

TIPOS = {
    "web": ("Sitio web", [("url", "URL", "url"), ("correo", "Correo", "email"), ("doble_factor", "Método de 2FA", "text")]),
    "aplicacion": ("Aplicación", [("aplicacion", "Nombre de aplicación", "text"), ("servidor", "Servidor", "text"), ("ambiente", "Ambiente", "text")]),
    "servidor": ("Servidor / máquina", [("ip", "IP", "text"), ("hostname", "Nombre de equipo", "text"), ("so", "Sistema operativo", "text"), ("protocolo", "Protocolo", "text"), ("puerto", "Puerto", "text")]),
    "red": ("Equipo de red", [("ip", "IP de administración", "text"), ("marca", "Marca", "text"), ("modelo", "Modelo", "text"), ("inventario", "Inventario", "text")]),
    "bd": ("Base de datos", [("motor", "Motor", "text"), ("host", "Servidor", "text"), ("puerto", "Puerto", "text"), ("base", "Base de datos", "text"), ("esquema", "Esquema", "text")]),
    "correo": ("Correo electrónico", [("correo", "Dirección de correo", "email"), ("proveedor", "Proveedor", "text"), ("recuperacion", "Contacto de recuperación", "text")]),
    "api": ("Token / API", [("endpoint", "Endpoint", "url"), ("cliente", "Client ID", "text"), ("permisos", "Scopes", "text"), ("vencimiento", "Vencimiento", "text")]),
    "wifi": ("Wi-Fi", [("ssid", "Nombre de red SSID", "text"), ("tipo_seguridad", "Tipo de seguridad", "text"), ("ubicacion", "Ubicación", "text")]),
    "servicio": ("Cuenta de servicio", [("sistema", "Sistema", "text"), ("equipo", "Equipo", "text"), ("privilegios", "Privilegios", "text")]),
    "personalizado": ("Personalizado", [("campo1", "Campo adicional 1", "text"), ("campo2", "Campo adicional 2", "text"), ("campo3", "Campo adicional 3", "text")]),
}


class HashPassPermiso(db.Model):
    __tablename__ = "hashpass_permisos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    autorizado = db.Column(db.Boolean, nullable=False, default=False)
    autorizado_por = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"))
    actualizado_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    usuario = db.relationship(
        "Usuario", foreign_keys=[usuario_id],
        backref=db.backref("permiso_hashpass", uselist=False),
    )


class HashPassBoveda(db.Model):
    __tablename__ = "hashpass_bovedas"
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    sal = db.Column(db.LargeBinary, nullable=False)
    nonce = db.Column(db.LargeBinary, nullable=False)
    clave_envuelta = db.Column(db.LargeBinary, nullable=False)
    version = db.Column(db.SmallInteger, nullable=False, default=1)
    creado_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class HashPassRegistro(db.Model):
    __tablename__ = "hashpass_registros"
    id = db.Column(db.String(36), primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = db.Column(db.String(32), nullable=False)
    nonce = db.Column(db.LargeBinary, nullable=False)
    contenido_cifrado = db.Column(db.LargeBinary, nullable=False)
    archivado = db.Column(db.Boolean, nullable=False, default=False, index=True)
    creado_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


def permiso_activo(usuario_id):
    registro = HashPassPermiso.query.filter_by(usuario_id=usuario_id, autorizado=True).first()
    return registro is not None


def _auditar(accion, entidad_id=None, commit=True):
    registrar_bitacora(
        accion=accion, modulo="HashPass", usuario_id=current_user.id,
        descripcion="Evento de seguridad HashPass", entidad="HashPass",
        entidad_id=entidad_id, commit=commit,
    )


@hashpass_bp.before_request
def verificar_acceso():
    if not current_app.config.get("HASHPASS_ENABLED", False):
        abort(404)
    # El módulo de secretos NO acepta HTTP ni cookies de sesión inseguras
    # en uso real. Sólo las pruebas aisladas con TESTING pueden usar HTTP.
    if not current_app.testing and (
        not current_app.config.get("HASHPASS_REQUIRE_HTTPS", True)
        or not current_app.config.get("SESSION_COOKIE_SECURE", False)
        or not request.is_secure
    ):
        abort(403)
    try:
        inspector = inspect(db.engine)
        if not all(inspector.has_table(t) for t in (
            "hashpass_permisos", "hashpass_bovedas", "hashpass_registros",
        )):
            abort(503, description="HashPass requiere migración Alembic.")
    except SQLAlchemyError:
        db.session.rollback()
        abort(503, description="No se pudo comprobar la base de HashPass.")
    if not current_user.is_authenticated:
        abort(401)
    if not current_user.activo or current_user.debe_cambiar_password:
        abort(403)
    if request.endpoint == "hashpass.permiso":
        if current_user.rol != Usuario.ROL_ADMINISTRADOR:
            abort(403)
        return
    if not permiso_activo(current_user.id):
        abort(403)


@hashpass_bp.after_request
def proteger_respuesta(respuesta):
    respuesta.headers["Cache-Control"] = "no-store, max-age=0, private"
    respuesta.headers["Pragma"] = "no-cache"
    # Flask-WTF exige Referer en POST sobre HTTPS (WTF_CSRF_SSL_STRICT).
    # "no-referrer" impide al navegador incluirlo y bloquea la maestra con 400.
    # "same-origin" conserva el control CSRF y no transmite Referer fuera de SICODE.
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    return respuesta


def _boveda():
    return db.session.get(HashPassBoveda, current_user.id)


def _limite_intentos():
    desde = datetime.utcnow() - timedelta(minutes=10)
    return Bitacora.query.filter(
        Bitacora.usuario_id == current_user.id,
        Bitacora.accion == "HASHPASS_MAESTRA_FALLIDA",
        Bitacora.creado_en >= desde,
    ).count() >= 5


def _abrir(maestra):
    boveda = _boveda()
    if not boveda:
        abort(409)
    if _limite_intentos():
        _auditar("HASHPASS_ACCESO_LIMITADO")
        abort(429)
    try:
        return abrir_boveda(maestra or "", current_user.id, boveda.sal, boveda.nonce, boveda.clave_envuelta)
    except (ValueError, InvalidTag, UnicodeError):
        _auditar("HASHPASS_MAESTRA_FALLIDA")
        return None


def _tipo_actual(valor):
    return valor if valor in TIPOS else "web"


def _campos():
    tipo = _tipo_actual(request.form.get("tipo", "web"))
    nombre = (request.form.get("nombre") or "").strip()
    secreto = request.form.get("secreto") or ""
    if not 1 <= len(nombre) <= 180 or not 1 <= len(secreto) <= 4096:
        return None
    campos = {
        "nombre": nombre, "usuario": (request.form.get("usuario") or "")[:250],
        "secreto": secreto, "notas": (request.form.get("notas") or "")[:4000],
    }
    for campo, _etiqueta, _tipo_html in TIPOS[tipo][1]:
        campos[campo] = (request.form.get(campo) or "")[:1000]
    return tipo, campos


@hashpass_bp.route("/", methods=["GET", "POST"])
def inicio():
    _auditar("HASHPASS_ABRIR_MODULO")
    boveda = _boveda()
    if boveda is None:
        return redirect(url_for("hashpass.configurar"))
    # No mostrar ni siquiera tipos, UUID o fechas sin la maestra.
    registros = []
    nombres = {}
    filtro = ""
    desbloqueada = False
    if request.method == "POST":
        dek = _abrir(request.form.get("maestra"))
        if dek is None:
            flash("No fue posible desbloquear el listado.", "danger")
        else:
            desbloqueada = True
            registros = HashPassRegistro.query.filter_by(
                usuario_id=current_user.id, archivado=False
            ).order_by(HashPassRegistro.actualizado_utc.desc()).all()
            filtro = (request.form.get("q") or "").strip().casefold()[:180]
            for registro in registros:
                try:
                    datos = descifrar_registro(
                        dek, current_user.id, registro.id,
                        registro.nonce, registro.contenido_cifrado,
                    )
                except (InvalidTag, ValueError, UnicodeError):
                    _auditar("HASHPASS_INTEGRIDAD_FALLIDA", registro.id)
                    abort(409)
                nombre = str(datos.get("nombre", "Sin nombre"))
                if not filtro or filtro in nombre.casefold():
                    nombres[registro.id] = nombre
            _auditar("HASHPASS_DESBLOQUEAR_LISTADO")
    return render_template(
        "hashpass.html", modo="lista", registros=registros,
        nombres=nombres, filtrado=bool(filtro), desbloqueada=desbloqueada, tipos=TIPOS,
    )


@hashpass_bp.route("/configurar", methods=["GET", "POST"])
def configurar():
    if _boveda():
        return redirect(url_for("hashpass.inicio"))
    if request.method == "POST":
        maestra = request.form.get("maestra", "")
        confirmar = request.form.get("confirmar", "")
        if maestra != confirmar or not 15 <= len(maestra) <= 1024:
            flash("La contraseña maestra debe coincidir y tener al menos 15 caracteres.", "danger")
        elif check_password_hash(current_user.password_hash, maestra):
            flash("La maestra debe ser distinta de la contraseña de SICODE.", "danger")
        else:
            sal, nonce, clave = crear_boveda(maestra, current_user.id)
            db.session.add(HashPassBoveda(usuario_id=current_user.id, sal=sal, nonce=nonce, clave_envuelta=clave))
            _auditar("HASHPASS_CONFIGURAR_BOVEDA", commit=False)
            db.session.commit()
            flash("Bóveda creada. La maestra no puede ser recuperada por administración.", "success")
            return redirect(url_for("hashpass.inicio"))
    return render_template("hashpass.html", modo="configurar", tipos=TIPOS)


@hashpass_bp.route("/permiso/<int:usuario_id>", methods=["POST"])
def permiso(usuario_id):
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario:
        abort(404)
    registro = HashPassPermiso.query.filter_by(usuario_id=usuario_id).first()
    if not registro:
        registro = HashPassPermiso(usuario_id=usuario_id)
        db.session.add(registro)
    # Sólo se concede a cuentas activas; revocar siempre es posible.
    conceder = request.form.get("accion") == "conceder"
    if request.form.get("accion") not in ("conceder", "revocar"):
        abort(400)
    if conceder and not usuario.activo:
        abort(400)
    registro.autorizado = conceder
    registro.autorizado_por = current_user.id
    registro.actualizado_utc = datetime.utcnow()
    _auditar("HASHPASS_CONCEDER_PERMISO" if conceder else "HASHPASS_REVOCAR_PERMISO", usuario_id, commit=False)
    db.session.commit()
    flash("Permiso HashPass actualizado.", "success")
    return redirect(url_for("admin.usuarios"))


@hashpass_bp.route("/registro/nuevo", methods=["GET", "POST"])
def nuevo():
    if _boveda() is None:
        return redirect(url_for("hashpass.configurar"))
    tipo = _tipo_actual(request.values.get("tipo"))
    if request.method == "POST":
        dek = _abrir(request.form.get("maestra"))
        if dek is None:
            flash("No fue posible desbloquear la bóveda.", "danger")
        else:
            validacion = _campos()
            if not validacion:
                flash("Debe proporcionar nombre y contraseña/clave.", "danger")
            else:
                tipo, datos = validacion
                identificador = str(uuid4())
                nonce, contenido = cifrar_registro(dek, current_user.id, identificador, datos)
                db.session.add(HashPassRegistro(
                    id=identificador, usuario_id=current_user.id, tipo=tipo,
                    nonce=nonce, contenido_cifrado=contenido,
                ))
                _auditar("HASHPASS_CREAR_REGISTRO", identificador, commit=False)
                db.session.commit()
                flash("Credencial guardada cifrada.", "success")
                return redirect(url_for("hashpass.inicio"))
    return render_template("hashpass.html", modo="formulario", tipo=tipo, tipos=TIPOS, editando=False)


def _registro_propio(registro_id):
    # Filtra por propietario en SQL: ni el administrador ve secretos ajenos.
    registro = HashPassRegistro.query.filter_by(
        id=registro_id, usuario_id=current_user.id, archivado=False
    ).first()
    if not registro:
        abort(404)
    return registro


@hashpass_bp.route("/registro/<uuid:registro_id>/ver", methods=["GET", "POST"])
def ver(registro_id):
    registro = _registro_propio(str(registro_id))
    if request.method == "POST":
        dek = _abrir(request.form.get("maestra"))
        if dek is not None:
            try:
                datos = descifrar_registro(dek, current_user.id, registro.id, registro.nonce, registro.contenido_cifrado)
            except (InvalidTag, ValueError, UnicodeError):
                _auditar("HASHPASS_INTEGRIDAD_FALLIDA", registro.id)
                abort(409)
            _auditar("HASHPASS_REVELAR_REGISTRO", registro.id)
            return render_template("hashpass.html", modo="detalle", registro=registro, datos=datos, tipos=TIPOS)
        flash("No fue posible desbloquear la bóveda.", "danger")
    return render_template("hashpass.html", modo="pedir_maestra", registro=registro, tipos=TIPOS)


@hashpass_bp.route("/registro/<uuid:registro_id>/editar", methods=["GET", "POST"])
def editar(registro_id):
    registro = _registro_propio(str(registro_id))
    tipo = _tipo_actual(request.values.get("tipo") or registro.tipo)
    if request.method == "POST":
        dek = _abrir(request.form.get("maestra"))
        if dek is None:
            flash("No fue posible desbloquear la bóveda.", "danger")
        else:
            validacion = _campos()
            if not validacion:
                flash("Debe proporcionar nombre y contraseña/clave.", "danger")
            else:
                tipo, datos = validacion
                nonce, contenido = cifrar_registro(dek, current_user.id, registro.id, datos)
                registro.tipo, registro.nonce, registro.contenido_cifrado = tipo, nonce, contenido
                registro.actualizado_utc = datetime.utcnow()
                _auditar("HASHPASS_EDITAR_REGISTRO", registro.id, commit=False)
                db.session.commit()
                flash("Credencial actualizada.", "success")
                return redirect(url_for("hashpass.inicio"))
    return render_template("hashpass.html", modo="formulario", tipo=tipo, tipos=TIPOS, editando=True, registro=registro)


@hashpass_bp.route("/registro/<uuid:registro_id>/archivar", methods=["POST"])
def archivar(registro_id):
    registro = _registro_propio(str(registro_id))
    if _abrir(request.form.get("maestra")) is None:
        flash("No fue posible desbloquear la bóveda.", "danger")
    else:
        registro.archivado = True
        _auditar("HASHPASS_ARCHIVAR_REGISTRO", registro.id, commit=False)
        db.session.commit()
        flash("Credencial archivada.", "success")
    return redirect(url_for("hashpass.inicio"))


@hashpass_bp.route("/cambiar-maestra", methods=["GET", "POST"])
def cambiar_maestra():
    if _boveda() is None:
        return redirect(url_for("hashpass.configurar"))
    if request.method == "POST":
        dek = _abrir(request.form.get("maestra_actual"))
        nueva = request.form.get("maestra_nueva", "")
        if dek is None:
            flash("Contraseña maestra actual incorrecta.", "danger")
        elif (nueva != request.form.get("confirmar") or not 15 <= len(nueva) <= 1024
              or nueva == request.form.get("maestra_actual") or check_password_hash(current_user.password_hash, nueva)):
            flash("La nueva maestra no cumple los requisitos o no es distinta.", "danger")
        else:
            boveda = _boveda()
            boveda.sal, boveda.nonce, boveda.clave_envuelta = reenvolver_clave(dek, nueva, current_user.id)
            _auditar("HASHPASS_CAMBIAR_MAESTRA", commit=False)
            db.session.commit()
            flash("Contraseña maestra actualizada.", "success")
            return redirect(url_for("hashpass.inicio"))
    return render_template("hashpass.html", modo="cambiar_maestra", tipos=TIPOS)


@hashpass_bp.route("/generador")
def generador():
    # Sólo contraseña propuesta: no se guarda ni transmite por URL.
    alfabeto = ascii_letters + digits + punctuation.replace('"', "").replace("'", "").replace("<", "").replace(">", "")
    generado = "".join(choice(alfabeto) for _ in range(24))
    return render_template("hashpass.html", modo="generador", generado=generado, tipos=TIPOS)
