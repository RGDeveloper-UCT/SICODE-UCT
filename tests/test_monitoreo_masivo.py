from datetime import date
from pathlib import Path
import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.models.expediente import Expediente
from app.models.usuario import Usuario


ROOT = Path(__file__).resolve().parents[1]
MONITOREO_MASIVO_JS = ROOT / "app" / "static" / "js" / "coordinacion_monitoreo_masivo.js"


@pytest.fixture()
def app_monitoreo_masivo():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Masivo",
            usuario="masivo-admin",
            correo="masivo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expedientes = [
            Expediente(
                codigo_interno="SICODE-UCT-0101",
                no_sp="101",
                nombre_referencia="SP 101",
                estado_administrativo="Activo",
                estado_fisico_documental="Pendiente de verificación",
                expediente_fisico_registrado=True,
                activo=True,
            ),
            Expediente(
                codigo_interno="SICODE-UCT-0102",
                no_sp="102",
                nombre_referencia="SP 102",
                estado_administrativo="Activo",
                estado_fisico_documental="Pendiente de verificación",
                expediente_fisico_registrado=True,
                activo=True,
            ),
        ]
        db.session.add(usuario)
        db.session.add_all(expedientes)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_masivo(app_monitoreo_masivo):
    cliente = app_monitoreo_masivo.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "masivo-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _abrir_lote(cliente):
    respuesta = cliente.get("/coordinacion/monitoreo/masivo")
    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    encontrado = re.search(r'data-lote-id="([0-9a-f]+)"', texto)
    assert encontrado
    return encontrado.group(1), texto


def _rectificar(cliente, lote_id, sp, folios, anexos):
    respuesta = cliente.post(
        "/coordinacion/monitoreo/masivo/rectificar",
        json={
            "lote_id": lote_id,
            "no_sp": sp,
            "total_folios": folios,
            "total_anexos": anexos,
            "confirmado": True,
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["rectificado_lote"] is True
    return respuesta


def test_opcion_masiva_aparece_en_registros_y_redirige(cliente_masivo):
    inicio = cliente_masivo.get("/coordinacion")
    texto = inicio.get_data(as_text=True)
    assert inicio.status_code == 200
    assert "Registro masivo de monitoreo" in texto
    assert "/coordinacion/registrar/monitoreo-masivo" in texto

    acceso = cliente_masivo.get("/coordinacion/registrar/monitoreo-masivo", follow_redirects=False)
    assert acceso.status_code == 302
    assert acceso.headers["Location"].endswith("/coordinacion/monitoreo/masivo")


def test_panel_masivo_tiene_revision_rectificacion_y_sin_observaciones(cliente_masivo):
    _lote, texto = _abrir_lote(cliente_masivo)
    assert "Registro masivo de reportes de monitoreo" in texto
    assert "Datos comunes del lote" in texto
    assert "Rectificar expediente" in texto
    assert "Verificación final del lote" in texto
    assert "vencido/histórico" in texto.lower()
    assert "observaciones" not in texto.lower()


def test_registro_masivo_guarda_monitoreo_anexo_y_actualiza_secuencia(app_monitoreo_masivo, cliente_masivo):
    lote_id, _ = _abrir_lote(cliente_masivo)
    _rectificar(cliente_masivo, lote_id, "101", 150, 3)

    respuesta = cliente_masivo.post(
        "/coordinacion/monitoreo/masivo",
        json={
            "lote_id": lote_id,
            "confirmacion_final": True,
            "tipo_referencia": "RC",
            "rc": "202624183",
            "providencia": "5908-2026",
            "fecha_recepcion": "2026-09-02",
            "persona_entrega": "Centro de Control y Monitoreo",
            "reportes": [{
                "no_sp": "101",
                "numero_reporte": "RM-0101",
                "tipo_evento": "No comunicación",
                "folios": "151-154",
                "numero_anexo": 4,
                "es_vencido": False,
            }],
        },
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["ok"] is True
    assert datos["cantidad"] == 1
    assert "tipo=MONITOREO" in datos["redirect_url"]

    with app_monitoreo_masivo.app_context():
        registro = RegistroCoordinacion.query.filter_by(tipo="MONITOREO").one()
        reporte = ReporteMonitoreo.query.filter_by(registro_id=registro.id).one()
        anexo = AnexoCoordinacion.query.filter_by(registro_id=registro.id).one()
        detalle = AnexoRectificado.query.filter_by(
            expediente_id=registro.expediente_id,
            numero_anexo="4",
            activo=True,
        ).one()
        expediente = Expediente.query.filter_by(no_sp="101").one()

        assert registro.rc == "RC 202624183"
        assert registro.providencia == "5908-2026"
        assert registro.fecha_recepcion == date(2026, 9, 2)
        assert registro.folios_recepcion == "151-154"
        assert registro.observaciones is None
        assert registro.origen_registro == "MASIVO"
        assert registro.lote_importacion.startswith("MON-")
        assert reporte.numero_reporte == "RM-0101"
        assert reporte.tipo_evento == "No comunicación"
        assert anexo.numero_anexo == "4"
        assert anexo.es_vencido is False
        assert detalle.folios == "151-154"
        assert expediente.folios_rectificados == 150
        assert expediente.anexos_rectificados == 4


def test_lote_es_atomico_si_una_fila_falla_secuencia(app_monitoreo_masivo, cliente_masivo):
    lote_id, _ = _abrir_lote(cliente_masivo)
    _rectificar(cliente_masivo, lote_id, "101", 100, 1)
    _rectificar(cliente_masivo, lote_id, "102", 200, 2)

    respuesta = cliente_masivo.post(
        "/coordinacion/monitoreo/masivo",
        json={
            "lote_id": lote_id,
            "confirmacion_final": True,
            "tipo_referencia": "RC",
            "rc": "202699999",
            "providencia": "9999-2026",
            "fecha_recepcion": "2026-09-02",
            "reportes": [
                {
                    "no_sp": "101",
                    "numero_reporte": "RM-A",
                    "tipo_evento": "No comunicación",
                    "folios": "101-102",
                    "numero_anexo": 2,
                    "es_vencido": False,
                },
                {
                    "no_sp": "102",
                    "numero_reporte": "RM-B",
                    "tipo_evento": "Salida",
                    "folios": "201-202",
                    "numero_anexo": 9,
                    "es_vencido": False,
                },
            ],
        },
    )

    assert respuesta.status_code == 400
    assert "Fila 2" in respuesta.get_json()["mensaje"]

    with app_monitoreo_masivo.app_context():
        assert RegistroCoordinacion.query.filter_by(tipo="MONITOREO").count() == 0
        assert ReporteMonitoreo.query.count() == 0
        assert AnexoCoordinacion.query.count() == 0
        assert AnexoRectificado.query.count() == 0
        assert Expediente.query.filter_by(no_sp="101").one().anexos_rectificados == 1
        assert Expediente.query.filter_by(no_sp="102").one().anexos_rectificados == 2


def test_ui_masiva_ocupa_viewport_y_marca_filas_completas_en_verde():
    javascript = MONITOREO_MASIVO_JS.read_text(encoding="utf-8")

    assert "body.vista-monitoreo-masivo .contenedor" in javascript
    assert "max-width: none !important;" in javascript
    assert "min-width: 0 !important;" in javascript
    assert "overflow-x: hidden !important;" in javascript
    assert "table-layout: fixed !important;" in javascript
    assert "function filaEstaLista(tr)" in javascript
    assert 'tr.classList.toggle("fila-lista", filaEstaLista(tr))' in javascript
    assert "tr.fila-lista td" in javascript
    assert "estado?.rectificado_lote" in javascript
