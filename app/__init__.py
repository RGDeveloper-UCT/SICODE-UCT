from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text
from config import Config

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.models import Usuario, Expediente, UbicacionFisica, Bitacora

    @app.route("/")
    def inicio():
        return "SICODE-UCT funcionando correctamente"

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(text("SELECT 1"))
            return "Conexion a PostgreSQL correcta"
        except Exception as error:
            return f"Error de conexion a PostgreSQL: {error}", 500

    return app
