import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.favorito_usuario import FavoritoUsuario
from app.models.usuario import Usuario


@pytest.fixture()
def app_favoritos():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuarios = [
            Usuario(
                nombre="Usuario Favoritos",
                usuario="favoritos-user",
                correo="favoritos-user@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                rol="usuario_autorizado",
                activo=True,
            ),
            Usuario(
                nombre="Visor Favoritos",
                usuario="favoritos-visor",
                correo="favoritos-visor@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                rol="visor",
                activo=True,
            ),
        ]
        for usuario in usuarios:
            usuario.debe_cambiar_password = False
        db.session.add_all(usuarios)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login(app, usuario):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": usuario, "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_usuario_puede_guardar_hasta_seis_favoritos(app_favoritos):
    cliente = _login(app_favoritos, "favoritos-user")

    for numero in range(1, 7):
        respuesta = cliente.post(
            "/favoritos/",
            json={"titulo": f"Expediente {numero}", "url": f"/expedientes/{numero}"},
        )
        assert respuesta.status_code == 201
        assert respuesta.get_json()["total"] == numero

    excedente = cliente.post(
        "/favoritos/",
        json={"titulo": "Séptimo", "url": "/pagos/historico"},
    )
    assert excedente.status_code == 409
    assert "máximo de 6" in excedente.get_json()["error"]

    listado = cliente.get("/favoritos/").get_json()
    assert listado["total"] == 6
    assert listado["maximo"] == 6
    assert [item["orden"] for item in listado["favoritos"]] == [1, 2, 3, 4, 5, 6]


def test_favorito_duplicado_no_ocupa_otro_espacio_y_se_puede_eliminar(app_favoritos):
    cliente = _login(app_favoritos, "favoritos-user")
    primero = cliente.post(
        "/favoritos/",
        json={"titulo": "SP 001", "url": "/expedientes/1"},
    )
    assert primero.status_code == 201
    favorito_id = primero.get_json()["favorito"]["id"]

    duplicado = cliente.post(
        "/favoritos/",
        json={"titulo": "Mismo SP", "url": "/expedientes/1"},
    )
    assert duplicado.status_code == 200
    assert duplicado.get_json()["ya_existia"] is True
    assert duplicado.get_json()["total"] == 1

    eliminado = cliente.delete(f"/favoritos/{favorito_id}")
    assert eliminado.status_code == 200
    assert eliminado.get_json()["total"] == 0

    with app_favoritos.app_context():
        assert FavoritoUsuario.query.count() == 0


def test_favoritos_son_personales_y_visor_tambien_puede_usarlos(app_favoritos):
    cliente_usuario = _login(app_favoritos, "favoritos-user")
    creado = cliente_usuario.post(
        "/favoritos/",
        json={"titulo": "Pagos", "url": "/pagos/"},
    )
    assert creado.status_code == 201

    cliente_visor = _login(app_favoritos, "favoritos-visor")
    listado_visor = cliente_visor.get("/favoritos/")
    assert listado_visor.status_code == 200
    assert listado_visor.get_json()["total"] == 0

    creado_visor = cliente_visor.post(
        "/favoritos/",
        json={"titulo": "Búsqueda", "url": "/buscar"},
    )
    assert creado_visor.status_code == 201

    listado_usuario = cliente_usuario.get("/favoritos/").get_json()
    assert listado_usuario["total"] == 1
    assert listado_usuario["favoritos"][0]["titulo"] == "Pagos"


def test_favoritos_rechaza_destinos_externos(app_favoritos):
    cliente = _login(app_favoritos, "favoritos-user")
    respuesta = cliente.post(
        "/favoritos/",
        json={"titulo": "Sitio externo", "url": "https://example.com"},
    )
    assert respuesta.status_code == 400


def test_panel_favoritos_aparece_junto_a_modulos_sicode(app_favoritos):
    cliente = _login(app_favoritos, "favoritos-user")
    respuesta = cliente.get("/dashboard")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert 'id="nav-modulos-sicode"' in html
    assert 'id="nav-favoritos-sicode"' in html
    assert html.index('id="nav-modulos-sicode"') < html.index('id="nav-favoritos-sicode"')
    assert 'data-favorito-agregar' in html
    assert 'data-favoritos-lista' in html
    assert 'css/favoritos.css' in html
