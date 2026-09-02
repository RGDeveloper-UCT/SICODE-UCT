from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnalisisRiesgo, AnexoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_analisis_riesgo():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Riesgo",
            usuario="riesgo-admin",
            correo="riesgo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0031",
            no_sp="31",
            nombre_referencia="SP análisis de riesgo",
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
def cliente_riesgo(app_analisis_riesgo):
    cliente = app_analisis_riesgo.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "riesgo-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _rectificar(cliente, total):
    respuesta = cliente.post(
        "/coordinacion/monitoreo/rectificar-anexos",
        json={"expediente_id": 1, "total_anexos": total},
    )
    assert respuesta.status_code == 200
    return respuesta.get_json()


def _datos_analisis(numero_anexo="4", correlativo="AR-2026-001", vencido=False):
    datos = {
        "no_sp": "31",
        "fecha_recepcion": "2026-09-02",
        "persona_entrega": "Área de Análisis de Riesgo",
        "tipo_referencia": "RC",
        "rc": "202626001",
        "providencia": "6100-2026",
        "folios": "331-336",
        "numero_anexo_monitoreo": numero_anexo,
        "confirmacion_file_server": "y",
        "tipo_documento": "PROVIDENCIA",
        "correlativo_analisis": correlativo,
        "tipo_evento": "No comunicación",
        "observaciones": "Análisis recibido para incorporar al expediente.",
    }
    if vencido:
        datos["anexo_vencido"] = "y"
    return datos


def test_panel_analisis_reutiliza_control_de_monitoreo_y_cambia_correlativo(cliente_riesgo):
    respuesta = cliente_riesgo.get("/coordinacion/registrar/analisis-riesgo")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Registrar Análisis de riesgo" in texto
    assert "Control de secuencia de anexos" in texto
    assert "numero_anexo_monitoreo" in texto
    assert "ANEXO VENCIDO / HISTÓRICO" in texto
    assert "correlativo_analisis" in texto
    assert "Correlativo de análisis de riesgo" in texto
    assert 'name="numero_reporte"' not in texto


def test_inicio_agrupa_monitoreo_y_analisis_dentro_de_anexos(cliente_riesgo):
    respuesta = cliente_riesgo.get("/coordinacion/")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "subpanel-anexos" in texto
    assert "Anexo general" not in texto
    assert "Reporte de monitoreo" in texto
    assert "Análisis de riesgo" in texto
    assert "/coordinacion/registrar/monitoreo" in texto
    assert "/coordinacion/registrar/analisis-riesgo" in texto
    assert "tarjeta-registro-coordinacion--monitoreo" not in texto


def test_analisis_riesgo_se_guarda_como_siguiente_anexo(app_analisis_riesgo, cliente_riesgo):
    estado = _rectificar(cliente_riesgo, 3)
    assert estado["siguiente_anexo"] == 4

    respuesta = cliente_riesgo.post(
        "/coordinacion/registrar/analisis-riesgo",
        data=_datos_analisis(),
        follow_redirects=False,
    )

    assert respuesta.status_code == 302
    assert "/coordinacion/registros/" in respuesta.headers["Location"]

    with app_analisis_riesgo.app_context():
        registro = RegistroCoordinacion.query.filter_by(tipo="ANALISIS_RIESGO").one()
        analisis = AnalisisRiesgo.query.filter_by(registro_id=registro.id).one()
        anexo = AnexoCoordinacion.query.filter_by(registro_id=registro.id).one()
        rectificado = AnexoRectificado.query.filter_by(
            expediente_id=1,
            numero_anexo="4",
            activo=True,
        ).one()
        expediente = db.session.get(Expediente, 1)

        assert registro.persona_entrega == "Área de Análisis de Riesgo"
        assert registro.folios_recepcion == "331-336"
        assert analisis.correlativo == "AR-2026-001"
        assert analisis.tipo_documento == "PROVIDENCIA"
        assert analisis.tipo_evento == "No comunicación"
        assert anexo.tipo_anexo == "ANÁLISIS DE RIESGO"
        assert anexo.numero_anexo == "4"
        assert anexo.es_vencido is False
        assert rectificado.titulo.startswith("Análisis de riesgo Correlativo AR-2026-001")
        assert rectificado.fecha_recepcion == date(2026, 9, 2)
        assert expediente.anexos_rectificados == 4

    detalle = cliente_riesgo.get(respuesta.headers["Location"])
    html = detalle.get_data(as_text=True)
    assert detalle.status_code == 200
    assert "Correlativo de análisis de riesgo" in html
    assert "AR-2026-001" in html


def test_analisis_riesgo_vencido_no_avanza_secuencia(app_analisis_riesgo, cliente_riesgo):
    _rectificar(cliente_riesgo, 7)

    respuesta = cliente_riesgo.post(
        "/coordinacion/registrar/analisis-riesgo",
        data=_datos_analisis(numero_anexo="2", correlativo="AR-HIST-002", vencido=True),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_analisis_riesgo.app_context():
        expediente = db.session.get(Expediente, 1)
        registro = RegistroCoordinacion.query.filter_by(tipo="ANALISIS_RIESGO").one()
        anexo = AnexoCoordinacion.query.filter_by(registro_id=registro.id).one()
        assert anexo.numero_anexo == "2"
        assert anexo.es_vencido is True
        assert expediente.anexos_rectificados == 7

    estado = cliente_riesgo.get("/coordinacion/monitoreo/estado-sp?no_sp=31").get_json()
    assert estado["total_rectificado"] == 7
    assert estado["siguiente_anexo"] == 8


def test_analisis_riesgo_no_puede_saltar_la_secuencia(app_analisis_riesgo, cliente_riesgo):
    _rectificar(cliente_riesgo, 3)

    respuesta = cliente_riesgo.post(
        "/coordinacion/registrar/analisis-riesgo",
        data=_datos_analisis(numero_anexo="5"),
        follow_redirects=False,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "El anexo vigente debe registrarse como Anexo 4" in texto

    with app_analisis_riesgo.app_context():
        assert RegistroCoordinacion.query.filter_by(tipo="ANALISIS_RIESGO").count() == 0
        assert db.session.get(Expediente, 1).anexos_rectificados == 3
