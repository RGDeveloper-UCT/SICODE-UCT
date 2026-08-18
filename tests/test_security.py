import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.expediente import Expediente
from app.models.usuario import Usuario


TOKEN_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


def extraer_csrf(respuesta):
    coincidencia = TOKEN_RE.search(respuesta.get_data(as_text=True))
    assert coincidencia, "No se encontró token CSRF en la respuesta"
    return coincidencia.group(1)


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = Usuario(
            nombre="Administrador",
            usuario="admin",
            correo="admin@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            rol="administrador",
            activo=True,
        )
        usuario = Usuario(
            nombre="Usuario",
            usuario="usuario",
            correo="usuario@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            rol="usuario_autorizado",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0001",
            no_sp="1",
            nombre_referencia="Prueba",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            activo=True,
        )
        db.session.add_all([admin, usuario, expediente])
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, usuario="admin", password="Password123", next_url=None):
    ruta = "/login"
    if next_url:
        ruta += f"?next={next_url}"
    pagina = client.get(ruta)
    token = extraer_csrf(pagina)
    return client.post(
        ruta,
        data={"usuario": usuario, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def test_open_redirect_se_rechaza(client):
    respuesta = login(client, next_url="https://example.org/phishing")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/dashboard")


def test_usuario_desactivado_pierde_sesion(app, client):
    assert login(client, usuario="usuario").status_code == 302
    assert client.get("/dashboard").status_code == 200

    with app.app_context():
        usuario = Usuario.query.filter_by(usuario="usuario").one()
        usuario.activo = False
        db.session.commit()

    respuesta = client.get("/dashboard", follow_redirects=False)
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_portadores_requiere_administrador(client):
    assert login(client, usuario="usuario").status_code == 302
    respuesta = client.get("/expedientes/portadores/importar", follow_redirects=False)
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/dashboard")


def test_post_mutante_sin_csrf_es_rechazado(client):
    assert login(client).status_code == 302
    respuesta = client.post("/expedientes/1/desactivar")
    assert respuesta.status_code == 400


def test_post_mutante_con_csrf_funciona(app, client):
    assert login(client).status_code == 302
    detalle = client.get("/expedientes/1")
    token = extraer_csrf(detalle)
    respuesta = client.post(
        "/expedientes/1/desactivar",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app.app_context():
        assert db.session.get(Expediente, 1).activo is False


def test_health_no_expone_detalles(client):
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"status": "ok"}
