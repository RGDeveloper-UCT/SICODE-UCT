import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.usuario import Usuario


@pytest.fixture()
def app_admin():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Único Administrador",
            usuario="admin-unico",
            correo="admin-unico@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(admin)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_admin(app_admin):
    cliente = app_admin.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-unico", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_no_se_puede_degradar_al_ultimo_administrador(app_admin, cliente_admin):
    respuesta = cliente_admin.post(
        "/admin/usuarios/1/editar",
        data={
            "nombre": "Único Administrador",
            "usuario": "admin-unico",
            "correo": "admin-unico@uct.local",
            "rol": "usuario_autorizado",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 200
    assert "último administrador activo" in respuesta.get_data(as_text=True)

    with app_admin.app_context():
        assert db.session.get(Usuario, 1).rol == "administrador"


def test_exportacion_bitacora_no_falla_y_se_audita(app_admin, cliente_admin):
    with app_admin.app_context():
        db.session.add(Bitacora(
            usuario_id=1,
            accion="PRUEBA",
            modulo="QA",
            descripcion="Evento de prueba",
        ))
        db.session.commit()

    respuesta = cliente_admin.get("/bitacora/exportar/excel")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(respuesta.data) > 100

    with app_admin.app_context():
        assert Bitacora.query.filter_by(accion="EXPORTAR_BITACORA_EXCEL").count() == 1
