import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.usuario import Usuario


@pytest.fixture()
def app_navegacion():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuarios = [
            Usuario(
                nombre="Administrador Navegación",
                usuario="admin-nav",
                correo="admin-nav@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="administrador",
                activo=True,
            ),
            Usuario(
                nombre="Usuario Navegación",
                usuario="usuario-nav",
                correo="usuario-nav@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="usuario_autorizado",
                activo=True,
            ),
        ]
        db.session.add_all(usuarios)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _cliente_autenticado(app, usuario):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": usuario, "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_administrador_ve_modulos_y_panel_administracion(app_navegacion):
    cliente = _cliente_autenticado(app_navegacion, "admin-nav")
    respuesta = cliente.get("/dashboard")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Módulos SICODE" in html
    assert 'id="nav-administracion-sicode"' in html
    assert 'href="/nexo/"' in html
    assert 'href="/admin/uo"' in html
    assert 'href="/admin/usuarios"' in html
    assert 'href="/admin/sistema"' in html
    assert "css/navegacion.css" in html
    assert "js/navegacion.js" in html


def test_usuario_autorizado_no_ve_panel_administracion_y_nexo_rechaza_url_directa(app_navegacion):
    cliente = _cliente_autenticado(app_navegacion, "usuario-nav")
    respuesta = cliente.get("/dashboard")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Módulos SICODE" in html
    assert 'id="nav-administracion-sicode"' not in html
    assert 'href="/nexo/"' not in html
    assert 'href="/admin/uo"' not in html
    assert 'href="/admin/usuarios"' not in html
    assert 'href="/admin/sistema"' not in html

    respuesta_nexo = cliente.get("/nexo/")
    assert respuesta_nexo.status_code == 403


def test_navegacion_incluye_controles_accesibles_y_animacion_reducible():
    from pathlib import Path

    plantilla = Path("app/templates/partials/navegacion.html").read_text(encoding="utf-8")
    javascript = Path("app/static/js/navegacion.js").read_text(encoding="utf-8")
    estilos = Path("app/static/css/navegacion.css").read_text(encoding="utf-8")

    assert 'aria-expanded="false"' in plantilla
    assert "data-nav-toggle" in plantilla
    assert "Escape" in javascript
    assert "ArrowDown" in javascript
    assert "prefers-reduced-motion" in estilos
