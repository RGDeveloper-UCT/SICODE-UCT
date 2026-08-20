import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.usuario import Usuario


TOKEN_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
ROLES = ("administrador", "usuario_autorizado", "visor")
PASSWORD_TEMPORAL = "Temporal123"
PASSWORD_NUEVA = "NuevaClave456"


def _csrf(respuesta):
    coincidencia = TOKEN_RE.search(respuesta.get_data(as_text=True))
    assert coincidencia, "No se encontró token CSRF en la respuesta"
    return coincidencia.group(1)


def _login(cliente, usuario):
    pagina = cliente.get("/login")
    token = _csrf(pagina)
    return cliente.post(
        "/login",
        data={
            "usuario": usuario,
            "password": PASSWORD_TEMPORAL,
            "csrf_token": token,
        },
        follow_redirects=False,
    )


@pytest.fixture()
def app_roles_temporales():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    with app.app_context():
        db.drop_all()
        db.create_all()

        for rol in ROLES:
            usuario = Usuario(
                nombre=f"Prueba {rol}",
                usuario=f"temp-{rol}",
                correo=f"temp-{rol}@uct.local",
                rol=rol,
                activo=True,
                password_hash=generate_password_hash(PASSWORD_TEMPORAL, method="pbkdf2:sha256"),
            )
            db.session.add(usuario)
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.mark.parametrize("rol", ROLES)
def test_todos_los_roles_son_obligados_a_cambiar_password(app_roles_temporales, rol):
    cliente = app_roles_temporales.test_client()
    usuario = f"temp-{rol}"

    respuesta_login = _login(cliente, usuario)
    assert respuesta_login.status_code == 302

    respuesta_dashboard = cliente.get("/dashboard", follow_redirects=False)
    assert respuesta_dashboard.status_code == 302
    assert "/mi-cuenta/cambiar-password" in respuesta_dashboard.headers["Location"]

    pagina_cambio = cliente.get("/mi-cuenta/cambiar-password")
    assert pagina_cambio.status_code == 200
    html = pagina_cambio.get_data(as_text=True)
    assert "Cambie su contraseña temporal" in html
    assert 'name="password_actual"' in html
    assert 'name="nueva_password"' in html
    assert 'name="confirmar_password"' in html
    assert "Actualizar contraseña" in html


@pytest.mark.parametrize("rol", ROLES)
def test_todos_los_roles_pueden_completar_cambio_obligatorio(app_roles_temporales, rol):
    cliente = app_roles_temporales.test_client()
    usuario = f"temp-{rol}"

    assert _login(cliente, usuario).status_code == 302

    pagina_cambio = cliente.get("/mi-cuenta/cambiar-password")
    token = _csrf(pagina_cambio)
    respuesta = cliente.post(
        "/mi-cuenta/cambiar-password",
        data={
            "password_actual": PASSWORD_TEMPORAL,
            "nueva_password": PASSWORD_NUEVA,
            "confirmar_password": PASSWORD_NUEVA,
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/mi-cuenta/")

    with app_roles_temporales.app_context():
        registro = Usuario.query.filter_by(usuario=usuario).one()
        assert registro.debe_cambiar_password is False

    assert cliente.get("/dashboard").status_code == 200


def test_visor_conserva_formulario_permitido_y_restricciones_visuales():
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    plantilla = (raiz / "app/templates/cuenta/cambiar_password.html").read_text(encoding="utf-8")
    css_visor = (raiz / "app/static/css/visor.css").read_text(encoding="utf-8")
    css_permisos = (raiz / "app/static/css/visor_permisos.css").read_text(encoding="utf-8")

    assert "visor-post-permitido" in plantilla
    assert 'body.modo-visor form[method="POST"]' in css_visor
    assert "form.visor-post-permitido" in css_permisos
    assert "display: block !important" in css_permisos
