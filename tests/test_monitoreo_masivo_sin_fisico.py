import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.coordinacion import RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_masivo_sin_fisico():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Masivo Físico",
            usuario="masivo-fisico",
            correo="masivo-fisico@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0777",
            no_sp="777",
            nombre_referencia="SP sin expediente físico",
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
def cliente_masivo_sin_fisico(app_masivo_sin_fisico):
    cliente = app_masivo_sin_fisico.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "masivo-fisico", "password": "Password123"},
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


def test_masivo_carga_opcion_sin_expediente_fisico(cliente_masivo_sin_fisico):
    _lote_id, texto = _abrir_lote(cliente_masivo_sin_fisico)
    assert "coordinacion_monitoreo_masivo_fisico.js" in texto

    script = cliente_masivo_sin_fisico.get(
        "/static/js/coordinacion_monitoreo_masivo_fisico.js"
    )
    contenido = script.get_data(as_text=True)
    assert script.status_code == 200
    assert "No se cuenta con el expediente físico aún" in contenido
    assert "sin_expediente_fisico" in contenido
    assert "No se registrarán folios ficticios" in contenido


def test_rectificacion_masiva_permite_sin_expediente_y_mantiene_indicador_rojo(
    app_masivo_sin_fisico,
    cliente_masivo_sin_fisico,
):
    lote_id, _ = _abrir_lote(cliente_masivo_sin_fisico)

    rectificacion = cliente_masivo_sin_fisico.post(
        "/coordinacion/monitoreo/masivo/rectificar",
        json={
            "lote_id": lote_id,
            "no_sp": "777",
            "total_folios": None,
            "total_anexos": 0,
            "sin_expediente_fisico": True,
            "confirmado": True,
        },
    )
    datos = rectificacion.get_json()
    assert rectificacion.status_code == 200
    assert datos["ok"] is True
    assert datos["rectificado_lote"] is True
    assert datos["expediente_fisico_registrado"] is False
    assert datos["folios_rectificados"] is None
    assert datos["anexos_rectificados"] == 0

    with app_masivo_sin_fisico.app_context():
        expediente = Expediente.query.filter_by(no_sp="777").one()
        assert expediente.expediente_fisico_registrado is False
        assert expediente.folios_rectificados is None
        assert expediente.anexos_rectificados == 0
        assert expediente.disponibilidad == "Sin expediente físico"
        assert expediente.estado_fisico_documental == "Sin expediente físico"
        evento = Bitacora.query.filter_by(
            accion="MARCAR_SIN_EXPEDIENTE_FISICO_MONITOREO_MASIVO"
        ).one()
        assert evento.expediente_id == expediente.id
        assert evento.datos_posteriores["sin_expediente_fisico"] is True

    listado = cliente_masivo_sin_fisico.get("/expedientes")
    contenido = listado.get_data(as_text=True)
    assert listado.status_code == 200
    assert 'title="Sin expediente físico"' in contenido
    assert "estado-icono-rojo" in contenido


def test_lote_masivo_se_puede_registrar_sin_folios_del_expediente_principal(
    app_masivo_sin_fisico,
    cliente_masivo_sin_fisico,
):
    lote_id, _ = _abrir_lote(cliente_masivo_sin_fisico)
    rectificacion = cliente_masivo_sin_fisico.post(
        "/coordinacion/monitoreo/masivo/rectificar",
        json={
            "lote_id": lote_id,
            "no_sp": "777",
            "total_folios": None,
            "total_anexos": 0,
            "sin_expediente_fisico": True,
            "confirmado": True,
        },
    )
    assert rectificacion.status_code == 200

    respuesta = cliente_masivo_sin_fisico.post(
        "/coordinacion/monitoreo/masivo",
        json={
            "lote_id": lote_id,
            "confirmacion_final": True,
            "tipo_referencia": "RC",
            "rc": "202600777",
            "providencia": "777-2026",
            "fecha_recepcion": "2026-09-02",
            "persona_entrega": "Centro de Control y Monitoreo",
            "reportes": [{
                "no_sp": "777",
                "numero_reporte": "RM-777",
                "tipo_evento": "No comunicación",
                "folios": "1-2",
                "numero_anexo": 1,
                "es_vencido": False,
            }],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["cantidad"] == 1

    with app_masivo_sin_fisico.app_context():
        expediente = Expediente.query.filter_by(no_sp="777").one()
        assert expediente.expediente_fisico_registrado is False
        assert expediente.folios_rectificados is None
        assert expediente.anexos_rectificados == 1
        assert RegistroCoordinacion.query.filter_by(tipo="MONITOREO").count() == 1


def test_rectificacion_fisica_posterior_desde_masivo_reactiva_indicador(
    app_masivo_sin_fisico,
    cliente_masivo_sin_fisico,
):
    lote_id, _ = _abrir_lote(cliente_masivo_sin_fisico)
    sin_fisico = cliente_masivo_sin_fisico.post(
        "/coordinacion/monitoreo/masivo/rectificar",
        json={
            "lote_id": lote_id,
            "no_sp": "777",
            "total_anexos": 0,
            "sin_expediente_fisico": True,
            "confirmado": True,
        },
    )
    assert sin_fisico.status_code == 200

    con_fisico = cliente_masivo_sin_fisico.post(
        "/coordinacion/monitoreo/masivo/rectificar",
        json={
            "lote_id": lote_id,
            "no_sp": "777",
            "total_folios": 250,
            "total_anexos": 0,
            "sin_expediente_fisico": False,
            "confirmado": True,
        },
    )
    datos = con_fisico.get_json()
    assert con_fisico.status_code == 200
    assert datos["expediente_fisico_registrado"] is True
    assert datos["folios_rectificados"] == 250
    assert datos["rectificado_lote"] is True

    with app_masivo_sin_fisico.app_context():
        expediente = Expediente.query.filter_by(no_sp="777").one()
        assert expediente.expediente_fisico_registrado is True
        assert expediente.folios_rectificados == 250
        assert expediente.estado_fisico_documental != "Sin expediente físico"
