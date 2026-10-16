"""Pruebas de control de acceso y exposición de la exportación completa."""
from unittest.mock import patch

from flask import Flask
from flask_login import LoginManager, UserMixin, login_user

from app.routes.bitacora import bitacora_bp


class Actor(UserMixin):
    def __init__(self, rol):
        self.id = "1"
        self.rol = rol
        self.debe_cambiar_password = False


def crear_cliente(rol):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="solo-pruebas", TESTING=True)
    login = LoginManager(app)
    actor = Actor(rol)

    @login.user_loader
    def cargar_usuario(_id):
        return actor

    app.register_blueprint(bitacora_bp)
    with app.test_client() as client:
        with client.session_transaction() as sesion:
            sesion["_user_id"] = actor.id
            sesion["_fresh"] = True
        yield client


def test_exportacion_completa_rechaza_usuario_autorizado():
    for client in crear_cliente("usuario_autorizado"):
        respuesta = client.get("/bitacora/exportar/completo")
        assert respuesta.status_code == 403


def test_exportacion_completa_rechaza_visor():
    for client in crear_cliente("visor"):
        respuesta = client.get("/bitacora/exportar/completo")
        assert respuesta.status_code == 403
