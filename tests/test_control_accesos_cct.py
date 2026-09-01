import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.control_acceso import AccesoCCT
from app.models.usuario import Usuario


@pytest.fixture()
def app_accesos():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Operador CCT",
            usuario="operador-cct",
            correo="operador-cct@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(usuario)
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_accesos(app_accesos):
    cliente = app_accesos.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "operador-cct", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_panel_ca_cct_muestra_formulario_e_historico(cliente_accesos):
    respuesta = cliente_accesos.get("/ca-cct/")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Control de Accesos al Centro de Control Telemático" in texto
    assert "Servicio técnico" in texto
    assert "Visita técnica" in texto
    assert "Auditoría" in texto
    assert "Registrar y generar boleta PDF" in texto
    assert "Entradas al CCT" in texto


def test_registro_genera_correlativo_y_redirige_al_pdf(app_accesos, cliente_accesos):
    respuesta = cliente_accesos.post(
        "/ca-cct/",
        data={
            "nombre": "Visitante de Prueba",
            "cui": "1234 56789 0101",
            "motivo": "VISITA_TECNICA",
            "motivo_otro": "",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/ca-cct/1/pdf")

    with app_accesos.app_context():
        acceso = AccesoCCT.query.one()
        auditoria = Bitacora.query.filter_by(accion="REGISTRAR_ACCESO_CCT").one()
        assert acceso.correlativo == "CCT-000001"
        assert acceso.nombre == "Visitante de Prueba"
        assert acceso.cui == "1234567890101"
        assert acceso.motivo_legible == "Visita técnica"
        assert auditoria.entidad == "AccesoCCT"
        assert auditoria.datos_posteriores["cui_final"] == "0101"
        assert "cui" not in auditoria.datos_posteriores


def test_otro_exige_descripcion(cliente_accesos):
    respuesta = cliente_accesos.post(
        "/ca-cct/",
        data={"nombre": "Persona", "cui": "1234567890101", "motivo": "OTRO", "motivo_otro": ""},
    )
    assert respuesta.status_code == 400
    assert "Describa el motivo cuando seleccione Otro" in respuesta.get_data(as_text=True)


def test_boleta_pdf_carta_es_regenerable(app_accesos, cliente_accesos):
    cliente_accesos.post(
        "/ca-cct/",
        data={
            "nombre": "Auditor Externo",
            "cui": "1234567890101",
            "motivo": "AUDITORIA",
            "motivo_otro": "",
        },
        follow_redirects=False,
    )

    respuesta = cliente_accesos.get("/ca-cct/1/pdf")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/pdf"
    assert respuesta.data.startswith(b"%PDF")
    assert "CCT-000001_acceso_CCT.pdf" in respuesta.headers["Content-Disposition"]

    with app_accesos.app_context():
        auditoria = Bitacora.query.filter_by(accion="CONSULTAR_BOLETA_ACCESO_CCT_PDF").first()
        assert auditoria is not None
