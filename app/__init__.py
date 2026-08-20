from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

from config import Config


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    Config.validar()

    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Debe iniciar sesión para acceder al sistema."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    from app.models import (
        Usuario,
        Expediente,
        UbicacionFisica,
        Bitacora,
        DocumentoExpediente,
        Alerta,
        PrestamoExpediente,
        TrasladoVirtualExpediente,
        ImportacionPortadores,
        VerificacionExpediente,
    )
    from app.services.integridad_events import registrar_eventos_integridad
    from app.services.version_service import obtener_version

    registrar_eventos_integridad()

    @login_manager.user_loader
    def load_user(usuario_id):
        try:
            usuario = db.session.get(Usuario, int(usuario_id))
        except (TypeError, ValueError):
            return None
        if not usuario or not usuario.activo:
            return None
        return usuario

    from app.routes import (
        auth_bp, dashboard_bp, expedientes_bp, expedientes_admin_bp, expediente_fisico_bp, verificaciones_bp,
        bitacora_bp, indice_documental_bp, alertas_bp, prestamos_bp, admin_bp,
        integridad_bp, busqueda_bp, cuenta_bp, coordinacion_bp, coordinacion_export_bp, portadores_bp,
    )
    for blueprint in (
        auth_bp, dashboard_bp, expedientes_bp, expedientes_admin_bp, expediente_fisico_bp, verificaciones_bp,
        bitacora_bp, indice_documental_bp, alertas_bp, prestamos_bp, admin_bp,
        integridad_bp, busqueda_bp, cuenta_bp, coordinacion_bp, coordinacion_export_bp, portadores_bp,
    ):
        app.register_blueprint(blueprint)

    @app.before_request
    def exigir_cambio_password_temporal():
        if not current_user.is_authenticated or not current_user.debe_cambiar_password:
            return None
        if request.endpoint in {"cuenta.cambiar_password", "auth.logout", "static"}:
            return None
        flash("Debe cambiar su contraseña temporal antes de continuar en SICODE.", "warning")
        return redirect(url_for("cuenta.cambiar_password"))

    @app.context_processor
    def contexto_version():
        return {"sicode_version": obtener_version()}

    @app.route("/")
    def inicio():
        return redirect(url_for("auth.login"))

    @app.route("/health")
    def health():
        return {"status": "ok", "version": obtener_version()}

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(text("SELECT 1")).scalar()
            return "Conexion a PostgreSQL correcta"
        except Exception:
            db.session.rollback()
            return "Base de datos no disponible", 503

    @app.errorhandler(403)
    def prohibido(_error):
        return render_template("errores/403.html"), 403

    @app.errorhandler(404)
    def no_encontrado(_error):
        return render_template("errores/404.html"), 404

    @app.errorhandler(500)
    def error_interno(error):
        db.session.rollback()
        app.logger.error("Error interno no controlado en SICODE", exc_info=error)
        return render_template("errores/500.html"), 500

    return app
