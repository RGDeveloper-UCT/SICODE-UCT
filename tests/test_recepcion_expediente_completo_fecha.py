from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.coordinacion import RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


GUATEMALA_TZ = ZoneInfo("America/Guatemala")


@pytest.fixture()
def app_recepcion_completa():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin Recepción",
            usuario="admin-recepcion",
            correo="admin-recepcion@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0378",
            no_sp="378",
            nombre_referencia="SP Recepción Fecha",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
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
def cliente_recepcion_completa(app_recepcion_completa):
    cliente = app_recepcion_completa.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-recepcion", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_formulario_fecha_recepcion_carga_hoy(cliente_recepcion_completa):
    respuesta = cliente_recepcion_completa.get("/coordinacion/registrar/expediente-completo")
    texto = respuesta.get_data(as_text=True)
    hoy = datetime.now(GUATEMALA_TZ).date().isoformat()

    assert respuesta.status_code == 200
    assert 'name="fecha_recepcion"' in texto
    assert f'value="{hoy}"' in texto
    assert "puede modificarla" in texto.lower()


def test_recepcion_completa_guarda_fecha_modificada(
    app_recepcion_completa,
    cliente_recepcion_completa,
):
    with app_recepcion_completa.app_context():
        expediente = Expediente.query.filter_by(no_sp="378").one()
        expediente_id = expediente.id

    respuesta = cliente_recepcion_completa.post(
        "/coordinacion/registrar/expediente-completo",
        data={
            "expediente_id": expediente_id,
            "forma_registro": "BASE_EDITABLE",
            "fecha_recepcion": "2026-08-27",
            "tipo_referencia": "RE",
            "numero_referencia": "20261591",
            "persona_entrega": "Coordinación de prueba",
            "documento_1": "Solicitud de Informe de Factibilidad",
            "folio_inicio_1": "1",
            "folio_fin_1": "4",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 302

    with app_recepcion_completa.app_context():
        registro = RegistroCoordinacion.query.filter_by(tipo="EXPEDIENTE_COMPLETO").one()
        assert registro.fecha_recepcion.isoformat() == "2026-08-27"
        assert registro.creado_en is not None

        evento = Bitacora.query.filter_by(accion="REGISTRAR_EXPEDIENTE_COMPLETO").one()
        assert evento.datos_posteriores["fecha_recepcion"] == "2026-08-27"
        assert "hora_registro" in evento.datos_posteriores
        assert "fecha_hora_registro" in evento.datos_posteriores
        assert evento.datos_posteriores["zona_horaria_registro"] == "America/Guatemala"
