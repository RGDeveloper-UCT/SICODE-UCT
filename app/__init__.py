from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from sqlalchemy import text
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Debe iniciar sesión para acceder al sistema."
    login_manager.login_message_category = "warning"

    from app.models import Usuario, Expediente, UbicacionFisica, Bitacora, DocumentoExpediente, Alerta

    @login_manager.user_loader
    def load_user(usuario_id):
        return Usuario.query.get(int(usuario_id))

    from app.routes import auth_bp, dashboard_bp, expedientes_bp, bitacora_bp, indice_documental_bp, alertas_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expedientes_bp)
    app.register_blueprint(bitacora_bp)
    app.register_blueprint(indice_documental_bp)
    app.register_blueprint(alertas_bp)

    @app.route("/")
    def inicio():
        return redirect(url_for("auth.login"))

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(text("SELECT 1"))
            return "Conexion a PostgreSQL correcta"
        except Exception as error:
            return f"Error de conexion a PostgreSQL: {error}", 500

    return app
