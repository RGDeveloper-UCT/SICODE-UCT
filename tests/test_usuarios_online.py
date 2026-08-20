from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.presencia import PresenciaUsuario
from app.models.usuario import Usuario


@pytest.fixture()
def app_uo():
    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        UO_ONLINE_TTL_SECONDS=75,
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuarios = [
            Usuario(
                nombre="Administrador UO",
                usuario="admin-uo",
                correo="admin-uo@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="administrador",
                activo=True,
            ),
            Usuario(
                nombre="Operador UO",
                usuario="operador-uo",
                correo="operador-uo@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="usuario_autorizado",
                activo=True,
            ),
            Usuario(
                nombre="Visor UO",
                usuario="visor-uo",
                correo="visor-uo@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="visor",
                activo=True,
            ),
        ]
        db.session.add_all(usuarios)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login(cliente, usuario):
    respuesta = cliente.post(
        "/login",
        data={"usuario": usuario, "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302


def _pulso(cliente, ruta="/buscar", pagina="Buscar — SICODE-UCT"):
    return cliente.post(
        "/presencia/pulso",
        json={"ruta": ruta, "pagina": pagina},
    )


def test_uo_muestra_presencia_y_no_expone_sesion(app_uo):
    operador = app_uo.test_client()
    admin = app_uo.test_client()
    _login(operador, "operador-uo")
    assert _pulso(operador).status_code == 200

    _login(admin, "admin-uo")
    respuesta = admin.get("/admin/uo/datos")
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["total_usuarios"] == 1
    assert datos["total_sesiones"] == 1
    assert datos["usuarios"][0]["usuario"] == "operador-uo"
    assert datos["usuarios"][0]["ruta"] == "/buscar"
    assert "sesion_id" not in datos["usuarios"][0]


def test_uo_agrupa_dos_sesiones_de_un_mismo_usuario(app_uo):
    navegador_a = app_uo.test_client()
    navegador_b = app_uo.test_client()
    admin = app_uo.test_client()

    _login(navegador_a, "operador-uo")
    _login(navegador_b, "operador-uo")
    assert _pulso(navegador_a, "/buscar").status_code == 200
    assert _pulso(navegador_b, "/prestamos", "Préstamos — SICODE-UCT").status_code == 200

    _login(admin, "admin-uo")
    datos = admin.get("/admin/uo/datos").get_json()
    assert datos["total_usuarios"] == 1
    assert datos["total_sesiones"] == 2
    assert datos["usuarios"][0]["sesiones"] == 2


def test_uo_panel_es_solo_administrador(app_uo):
    operador = app_uo.test_client()
    admin = app_uo.test_client()
    _login(operador, "operador-uo")
    _login(admin, "admin-uo")

    respuesta_operador = operador.get("/admin/uo", follow_redirects=False)
    assert respuesta_operador.status_code == 302
    assert "/dashboard" in respuesta_operador.headers["Location"]

    respuesta_admin = admin.get("/admin/uo")
    assert respuesta_admin.status_code == 200
    assert "UO · Usuarios Online" in respuesta_admin.get_data(as_text=True)


def test_logout_elimina_presencia_inmediatamente(app_uo):
    cliente = app_uo.test_client()
    _login(cliente, "operador-uo")
    assert _pulso(cliente).status_code == 200

    with app_uo.app_context():
        assert PresenciaUsuario.query.count() == 1

    respuesta = cliente.get("/logout", follow_redirects=False)
    assert respuesta.status_code == 302

    with app_uo.app_context():
        assert PresenciaUsuario.query.count() == 0


def test_presencia_vencida_no_aparece_online(app_uo):
    operador = app_uo.test_client()
    admin = app_uo.test_client()
    _login(operador, "operador-uo")
    assert _pulso(operador).status_code == 200

    with app_uo.app_context():
        presencia = PresenciaUsuario.query.one()
        presencia.ultimo_pulso_en = datetime.utcnow() - timedelta(minutes=5)
        db.session.commit()

    _login(admin, "admin-uo")
    datos = admin.get("/admin/uo/datos").get_json()
    assert datos["total_usuarios"] == 0
    assert datos["total_sesiones"] == 0


def test_visor_puede_enviar_pulso_sin_obtener_permisos_admin(app_uo):
    visor = app_uo.test_client()
    _login(visor, "visor-uo")
    assert _pulso(visor, "/coordinacion", "Coordinación — SICODE-UCT").status_code == 200
    assert visor.get("/admin/uo", follow_redirects=False).status_code == 302
