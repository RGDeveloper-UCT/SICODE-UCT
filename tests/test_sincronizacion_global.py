"""Pruebas del bus de invalidaciones SSE, sin depender del Redis institucional."""
import json

import pytest
import redis
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.agenda import AgendaCumpleanos
from app.models.usuario import Usuario


class RedisFalso:
    publicados = []

    def ping(self):
        return True

    def publish(self, canal, contenido):
        self.publicados.append((canal, json.loads(contenido)))
        return 1

    def pubsub(self, **_kwargs):
        return self

    def subscribe(self, _canal):
        pass

    def get_message(self, **_kwargs):
        return None

    def close(self):
        pass


@pytest.fixture
def sistema(monkeypatch):
    falso = RedisFalso()
    falso.publicados = []
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_args, **_kw: falso)
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Usuario(
            nombre="Usuario de prueba", usuario="tiempo_real",
            correo="realtime@uct.test",
            password_hash=generate_password_hash("Prueba1234", method="pbkdf2:sha256"),
            rol="usuario_autorizado", activo=True, debe_cambiar_password=False,
        ))
        db.session.commit()
    yield app, falso
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_exige_login_y_entrega_canal_sse(sistema):
    app, _falso = sistema
    sin_sesion = app.test_client()
    assert sin_sesion.get("/sincronizacion/eventos").status_code == 302

    cliente = app.test_client()
    assert cliente.post("/login", data={
        "usuario": "tiempo_real", "password": "Prueba1234",
    }).status_code == 302
    assert cliente.get("/sincronizacion/estado").get_json() == {"conectado": True}

    respuesta = cliente.get("/sincronizacion/eventos", buffered=False)
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "text/event-stream"
    assert next(respuesta.response) == b"event: listo\ndata: {}\n\n"
    respuesta.close()


def test_publica_una_vez_despues_del_commit_y_no_tras_rollback(sistema):
    app, falso = sistema
    with app.app_context():
        usuario = Usuario.query.filter_by(usuario="tiempo_real").first()
        # Activa publicación solo en esta base de pruebas; no usa Redis externo.
        app.config["TESTING"] = False
        db.session.add(AgendaCumpleanos(
            usuario_id=usuario.id, dia=1, mes=1, visible=True,
        ))
        db.session.flush()
        assert not falso.publicados
        db.session.commit()
        assert len(falso.publicados) == 1
        canal, mensaje = falso.publicados[0]
        assert canal == "sicode:sincronizacion:v1"
        assert {"agenda", "dashboard", "global"}.issubset(mensaje["modulos"])
        db.session.add(AgendaCumpleanos(
            usuario_id=usuario.id, dia=2, mes=1, visible=True,
        ))
        db.session.flush()
        db.session.rollback()
        assert len(falso.publicados) == 1
        app.config["TESTING"] = True


def test_lecturas_y_presencia_no_provocan_invalidacion(sistema):
    app, falso = sistema
    with app.app_context():
        app.config["TESTING"] = False
        usuario = Usuario.query.filter_by(usuario="tiempo_real").first()
        assert usuario.nombre == "Usuario de prueba"
        db.session.commit()
        assert falso.publicados == []
        app.config["TESTING"] = True
