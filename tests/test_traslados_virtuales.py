import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.expediente import Expediente
from app.models.traslado_virtual import TrasladoVirtualExpediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_virtual():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Operador Virtual",
            usuario="virtual-op",
            correo="virtual-op@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0010",
            no_sp="10",
            nombre_referencia="Persona Prueba Virtual",
            estado_administrativo="Activo",
            estado_fisico_documental="Verificado",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_virtual(app_virtual):
    cliente = app_virtual.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "virtual-op", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_panel_muestra_acciones_fisica_y_virtual(cliente_virtual):
    respuesta = cliente_virtual.get("/prestamos")
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Generar préstamo físico" in texto
    assert "Generar constancia de traslado de expediente virtual" in texto
    assert "Persona Prueba Virtual" in texto


def test_crear_traslado_virtual_y_generar_pdf(app_virtual, cliente_virtual):
    respuesta = cliente_virtual.post(
        "/expedientes/1/traslado-virtual/nuevo",
        data={
            "destinatario": "Lic. Persona Destino",
            "dependencia_destino": "Unidad de Prueba",
            "plataforma": "Proton Drive",
            "enlace_corto": "https://proton.me/drive/test-link",
            "asunto": "Traslado para consulta administrativa",
            "observaciones": "Constancia sin firma.",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert "/constancia/pdf" in respuesta.headers["Location"]

    with app_virtual.app_context():
        traslado = TrasladoVirtualExpediente.query.one()
        assert traslado.destinatario == "Lic. Persona Destino"
        assert traslado.plataforma == "Proton Drive"
        assert traslado.enlace_corto == "https://proton.me/drive/test-link"
        traslado_id = traslado.id

    pdf = cliente_virtual.get(f"/prestamos/traslado-virtual/{traslado_id}/constancia/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
