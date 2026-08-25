import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_sin_expediente():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Sin Expediente",
            usuario="sin-exp-admin",
            correo="sin-exp@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0405",
            no_sp="405",
            nombre_referencia="SP sin expediente recibido",
            estado_administrativo="Activo",
            estado_fisico_documental="Verificado",
            expediente_fisico_registrado=True,
            folios_rectificados=286,
            anexos_rectificados=29,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.flush()
        db.session.add(
            AnexoRectificado(
                expediente_id=expediente.id,
                numero_anexo="1",
                titulo="Anexo de prueba",
                creado_por_id=usuario.id,
                activo=True,
            )
        )
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_sin_expediente(app_sin_expediente):
    cliente = app_sin_expediente.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "sin-exp-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_rectificacion_muestra_boton_sin_expediente(cliente_sin_expediente):
    respuesta = cliente_sin_expediente.get("/expedientes/1/rectificar")
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Sin expediente físico en Coordinación" in texto
    assert "/expedientes/1/marcar-sin-expediente" in texto


def test_marcar_sin_expediente_limpia_rectificacion_y_bloquea_prestamo(
    app_sin_expediente, cliente_sin_expediente
):
    respuesta = cliente_sin_expediente.post(
        "/expedientes/1/marcar-sin-expediente",
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_sin_expediente.app_context():
        expediente = db.session.get(Expediente, 1)
        assert expediente.expediente_fisico_registrado is False
        assert expediente.folios_rectificados is None
        assert expediente.anexos_rectificados is None
        assert expediente.rectificado_en is None
        assert expediente.rectificado_por_id is None
        assert expediente.rectificacion_completa is False
        assert expediente.estado_fisico_documental == "Pendiente de verificación"
        assert AnexoRectificado.query.filter_by(expediente_id=1, activo=True).count() == 0

    prestamo = cliente_sin_expediente.get(
        "/expedientes/1/prestamos/nuevo",
        follow_redirects=False,
    )
    assert prestamo.status_code == 302
    assert "/expedientes/1/rectificar" in prestamo.headers["Location"]
