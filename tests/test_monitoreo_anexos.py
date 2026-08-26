from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_monitoreo_anexos():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Monitoreo",
            usuario="monitoreo-admin",
            correo="monitoreo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0021",
            no_sp="21",
            nombre_referencia="SP de monitoreo",
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
def cliente_monitoreo(app_monitoreo_anexos):
    cliente = app_monitoreo_anexos.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "monitoreo-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_panel_monitoreo_incluye_control_y_rectificacion(cliente_monitoreo):
    respuesta = cliente_monitoreo.get("/coordinacion/registrar/monitoreo")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Control del anexo del expediente" in texto
    assert "Rectificar anexos" in texto
    assert "File Server" in texto
    assert "numero_anexo_monitoreo" in texto


def test_sp_sin_total_exige_rectificacion_y_luego_sugiere_siguiente(app_monitoreo_anexos, cliente_monitoreo):
    inicial = cliente_monitoreo.get("/coordinacion/monitoreo/estado-sp?no_sp=21")
    datos = inicial.get_json()

    assert inicial.status_code == 200
    assert datos["requiere_rectificacion"] is True
    assert datos["siguiente_anexo"] is None

    rectificacion = cliente_monitoreo.post(
        "/coordinacion/monitoreo/rectificar-anexos",
        json={"expediente_id": 1, "total_anexos": 3},
    )
    rectificado = rectificacion.get_json()

    assert rectificacion.status_code == 200
    assert rectificado["total_rectificado"] == 3
    assert rectificado["siguiente_anexo"] == 4
    assert rectificado["requiere_rectificacion"] is False

    with app_monitoreo_anexos.app_context():
        expediente = db.session.get(Expediente, 1)
        assert expediente.anexos_rectificados == 3
        assert expediente.rectificado_por_id is not None
        assert expediente.rectificado_en is not None


def test_reporte_monitoreo_se_guarda_como_siguiente_anexo(app_monitoreo_anexos, cliente_monitoreo):
    cliente_monitoreo.post(
        "/coordinacion/monitoreo/rectificar-anexos",
        json={"expediente_id": 1, "total_anexos": 3},
    )

    respuesta = cliente_monitoreo.post(
        "/coordinacion/registrar/monitoreo",
        data={
            "no_sp": "21",
            "fecha_recepcion": "2026-08-26",
            "persona_entrega": "Centro de Control y Monitoreo",
            "tipo_referencia": "RC",
            "rc": "202624183",
            "providencia": "5908-2026",
            "folios": "325-330",
            "numero_anexo_monitoreo": "4",
            "confirmacion_file_server": "y",
            "tipo_documento": "PROVIDENCIA",
            "numero_reporte": "RM-004",
            "tipo_evento": "No comunicación",
            "observaciones": "Reporte recibido para expediente físico.",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 302
    assert "/coordinacion/registros/" in respuesta.headers["Location"]

    with app_monitoreo_anexos.app_context():
        registro = RegistroCoordinacion.query.filter_by(tipo="MONITOREO").one()
        reporte = ReporteMonitoreo.query.filter_by(registro_id=registro.id).one()
        anexo_coord = AnexoCoordinacion.query.filter_by(registro_id=registro.id).one()
        anexo_rectificado = AnexoRectificado.query.filter_by(
            expediente_id=1,
            numero_anexo="4",
            activo=True,
        ).one()
        expediente = db.session.get(Expediente, 1)

        assert reporte.numero_reporte == "RM-004"
        assert anexo_coord.numero_anexo == "4"
        assert anexo_coord.tipo_anexo == "REPORTE DE MONITOREO"
        assert anexo_rectificado.titulo.startswith("Reporte de monitoreo")
        assert anexo_rectificado.fecha_recepcion == date(2026, 8, 26)
        assert expediente.anexos_rectificados == 4


def test_no_permite_saltar_numero_sin_rectificar(app_monitoreo_anexos, cliente_monitoreo):
    cliente_monitoreo.post(
        "/coordinacion/monitoreo/rectificar-anexos",
        json={"expediente_id": 1, "total_anexos": 3},
    )

    respuesta = cliente_monitoreo.post(
        "/coordinacion/registrar/monitoreo",
        data={
            "no_sp": "21",
            "fecha_recepcion": "2026-08-26",
            "tipo_referencia": "RC",
            "numero_anexo_monitoreo": "5",
            "confirmacion_file_server": "y",
            "tipo_documento": "PROVIDENCIA",
            "numero_reporte": "RM-005",
        },
        follow_redirects=False,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "El reporte debe registrarse como Anexo 4" in texto

    with app_monitoreo_anexos.app_context():
        assert RegistroCoordinacion.query.filter_by(tipo="MONITOREO").count() == 0
        assert db.session.get(Expediente, 1).anexos_rectificados == 3
