from flask import Flask, redirect, url_for
from flask_login import LoginManager
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
        ImportacionPortadores,
    )

    from app.services.integridad_events import registrar_eventos_integridad
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
        auth_bp,
        dashboard_bp,
        expedientes_bp,
        expediente_fisico_bp,
        bitacora_bp,
        indice_documental_bp,
        alertas_bp,
        prestamos_bp,
        admin_bp,
        integridad_bp,
        busqueda_bp,
        cuenta_bp,
        coordinacion_bp,
        portadores_bp,
    )
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expedientes_bp)
    app.register_blueprint(expediente_fisico_bp)
    app.register_blueprint(bitacora_bp)
    app.register_blueprint(indice_documental_bp)
    app.register_blueprint(alertas_bp)
    app.register_blueprint(prestamos_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(integridad_bp)
    app.register_blueprint(busqueda_bp)
    app.register_blueprint(cuenta_bp)
    app.register_blueprint(coordinacion_bp)
    app.register_blueprint(portadores_bp)

    @app.route("/")
    def inicio():
        return redirect(url_for("auth.login"))

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(text("SELECT 1")).scalar()
            return "Conexion a PostgreSQL correcta"
        except Exception:
            db.session.rollback()
            return "Base de datos no disponible", 503

    return app
