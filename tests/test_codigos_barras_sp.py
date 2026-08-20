import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_codigos_barras():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Admin Códigos",
            usuario="admin-codigos",
            correo="admin-codigos@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        visor = Usuario(
            nombre="Visor Códigos",
            usuario="visor-codigos",
            correo="visor-codigos@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="visor",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0467",
            no_sp="467",
            nombre_referencia="Sujeto Prueba Código",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([admin, visor, expediente])
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


def test_codigo_barras_svg_se_genera_para_cada_sp(app_codigos_barras):
    cliente = app_codigos_barras.test_client()
    _login(cliente, "admin-codigos")

    respuesta = cliente.get("/expedientes/1/codigo-barras.svg")

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/svg+xml"
    assert respuesta.get_data(as_text=True).lstrip().startswith("<?xml")
    assert len(respuesta.data) > 1000


def test_etiqueta_pdf_usa_codigo_interno_y_deja_bitacora(app_codigos_barras):
    cliente = app_codigos_barras.test_client()
    _login(cliente, "admin-codigos")

    respuesta = cliente.get("/expedientes/1/exportar/etiqueta-codigo-barras.pdf")

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/pdf"
    assert respuesta.data.startswith(b"%PDF")

    with app_codigos_barras.app_context():
        evento = Bitacora.query.filter_by(accion="EXPORTAR_ETIQUETA_CODIGO_BARRAS").one()
        assert evento.expediente_id == 1


def test_ficha_sp_muestra_vista_panoramica_y_codigo(app_codigos_barras):
    cliente = app_codigos_barras.test_client()
    _login(cliente, "admin-codigos")

    respuesta = cliente.get("/expedientes/1")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert 'class="panel panel-expediente"' in texto
    assert 'class="sp-layout-principal"' in texto
    assert "/expedientes/1/codigo-barras.svg" in texto
    assert "SICODE-UCT-0467" in texto
    assert "Etiqueta PDF" in texto


def test_visor_puede_ver_codigo_pero_no_exportar_etiqueta(app_codigos_barras):
    cliente = app_codigos_barras.test_client()
    _login(cliente, "visor-codigos")

    svg = cliente.get("/expedientes/1/codigo-barras.svg")
    etiqueta = cliente.get("/expedientes/1/exportar/etiqueta-codigo-barras.pdf")
    detalle = cliente.get("/expedientes/1").get_data(as_text=True)

    assert svg.status_code == 200
    assert etiqueta.status_code == 403
    assert "Etiqueta PDF" not in detalle
