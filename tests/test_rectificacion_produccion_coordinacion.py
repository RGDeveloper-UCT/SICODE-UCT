import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.coordinacion import RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_rectificacion_produccion():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin Producción",
            usuario="admin-produccion",
            correo="admin-produccion@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0358",
            no_sp="358",
            nombre_referencia="SP Rectificación Producción",
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
def cliente_rectificacion_produccion(app_rectificacion_produccion):
    cliente = app_rectificacion_produccion.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-produccion", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_formulario_coordinacion_carga_modal_de_rectificacion(cliente_rectificacion_produccion):
    respuesta = cliente_rectificacion_produccion.get("/coordinacion/registrar/anexo")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "js/rectificacion_produccion.js" in texto

    script = cliente_rectificacion_produccion.get("/static/js/rectificacion_produccion.js")
    contenido = script.get_data(as_text=True)
    assert script.status_code == 200
    assert "Control obligatorio de producción" in contenido
    assert "Total actual de folios del expediente" in contenido
    assert "Total actual de anexos del expediente" in contenido
    assert "SICODE-UCT ya se encuentra en producción" in contenido
    assert "No se cuenta con el expediente físico aún" in contenido
    assert "sin_expediente_fisico" in contenido


def test_estado_rectificacion_produccion_consulta_sp(cliente_rectificacion_produccion):
    respuesta = cliente_rectificacion_produccion.get(
        "/coordinacion/rectificacion-produccion/estado?no_sp=358"
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["ok"] is True
    assert datos["no_sp"] == "358"
    assert datos["expediente_fisico_registrado"] is True
    assert datos["folios_rectificados"] is None
    assert datos["anexos_rectificados"] is None


def test_rectificacion_produccion_actualiza_maestro_y_bitacora(
    app_rectificacion_produccion,
    cliente_rectificacion_produccion,
):
    respuesta = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": 412,
            "total_anexos": 7,
            "confirmado": True,
            "origen": "anexo",
        },
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["ok"] is True
    assert datos["expediente_fisico_registrado"] is True
    assert datos["folios_rectificados"] == 412
    assert datos["anexos_rectificados"] == 7
    assert datos["rectificacion_completa"] is True

    with app_rectificacion_produccion.app_context():
        expediente = Expediente.query.filter_by(no_sp="358").one()
        assert expediente.expediente_fisico_registrado is True
        assert expediente.folios_rectificados == 412
        assert expediente.anexos_rectificados == 7
        assert expediente.rectificado_en is not None
        assert expediente.rectificado_por_id is not None

        evento = Bitacora.query.filter_by(accion="RECTIFICAR_EXPEDIENTE_PRODUCCION").one()
        assert evento.expediente_id == expediente.id
        assert evento.datos_posteriores["expediente_fisico_registrado"] is True
        assert evento.datos_posteriores["folios_rectificados"] == 412
        assert evento.datos_posteriores["anexos_rectificados"] == 7


def test_rectificacion_produccion_permite_confirmar_sin_expediente_fisico(
    app_rectificacion_produccion,
    cliente_rectificacion_produccion,
):
    respuesta = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": None,
            "total_anexos": 4,
            "sin_expediente_fisico": True,
            "confirmado": True,
            "origen": "analisis riesgo",
        },
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["ok"] is True
    assert datos["expediente_fisico_registrado"] is False
    assert datos["folios_rectificados"] is None
    assert datos["anexos_rectificados"] == 4
    assert datos["rectificacion_completa"] is False
    assert datos["rectificado_en"] is None
    assert "sin expediente físico" in datos["mensaje"].lower()

    with app_rectificacion_produccion.app_context():
        expediente = Expediente.query.filter_by(no_sp="358").one()
        assert expediente.expediente_fisico_registrado is False
        assert expediente.folios_rectificados is None
        assert expediente.anexos_rectificados == 4
        assert expediente.rectificado_en is None
        assert expediente.rectificado_por_id is None
        assert expediente.disponibilidad == "Sin expediente físico"
        assert expediente.estado_fisico_documental == "Sin expediente físico"

        evento = Bitacora.query.filter_by(
            accion="MARCAR_SIN_EXPEDIENTE_FISICO_PRODUCCION"
        ).one()
        assert evento.expediente_id == expediente.id
        assert evento.datos_posteriores["expediente_fisico_registrado"] is False
        assert evento.datos_posteriores["folios_rectificados"] is None
        assert evento.datos_posteriores["anexos_rectificados"] == 4

    listado = cliente_rectificacion_produccion.get("/expedientes")
    contenido = listado.get_data(as_text=True)
    assert listado.status_code == 200
    assert 'title="Sin expediente físico"' in contenido
    assert "estado-icono-rojo" in contenido


def test_sin_expediente_fisico_puede_conservar_total_anexos_existente(
    app_rectificacion_produccion,
    cliente_rectificacion_produccion,
):
    with app_rectificacion_produccion.app_context():
        expediente = Expediente.query.filter_by(no_sp="358").one()
        expediente.anexos_rectificados = 9
        db.session.commit()

    respuesta = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": None,
            "total_anexos": None,
            "sin_expediente_fisico": True,
            "confirmado": True,
            "origen": "monitoreo",
        },
    )
    assert respuesta.status_code == 200

    with app_rectificacion_produccion.app_context():
        expediente = Expediente.query.filter_by(no_sp="358").one()
        assert expediente.expediente_fisico_registrado is False
        assert expediente.folios_rectificados is None
        assert expediente.anexos_rectificados == 9


def test_rectificacion_produccion_exige_confirmacion_y_totales_validos(
    cliente_rectificacion_produccion,
):
    sin_confirmar = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": 100,
            "total_anexos": 2,
            "confirmado": False,
        },
    )
    assert sin_confirmar.status_code == 400

    folios_invalidos = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": 0,
            "total_anexos": 2,
            "confirmado": True,
        },
    )
    assert folios_invalidos.status_code == 400

    anexos_invalidos = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": 100,
            "total_anexos": -1,
            "confirmado": True,
        },
    )
    assert anexos_invalidos.status_code == 400

    anexos_invalidos_sin_fisico = cliente_rectificacion_produccion.post(
        "/coordinacion/rectificacion-produccion/guardar",
        json={
            "no_sp": "358",
            "total_folios": None,
            "total_anexos": -1,
            "sin_expediente_fisico": True,
            "confirmado": True,
        },
    )
    assert anexos_invalidos_sin_fisico.status_code == 400


def test_guard_de_produccion_bloquea_registro_hasta_rectificar(
    app_rectificacion_produccion,
    cliente_rectificacion_produccion,
):
    app_rectificacion_produccion.config["TESTING"] = False
    try:
        bloqueado = cliente_rectificacion_produccion.post(
            "/coordinacion/registrar/anexo",
            data={"no_sp": "358", "tipo_referencia": "RC"},
            follow_redirects=False,
        )
        assert bloqueado.status_code == 302
        assert "/coordinacion/registrar/anexo" in bloqueado.headers["Location"]

        with app_rectificacion_produccion.app_context():
            assert RegistroCoordinacion.query.count() == 0

        rectificacion = cliente_rectificacion_produccion.post(
            "/coordinacion/rectificacion-produccion/guardar",
            json={
                "no_sp": "358",
                "total_folios": 180,
                "total_anexos": 3,
                "confirmado": True,
                "origen": "anexo",
            },
        )
        assert rectificacion.status_code == 200

        permitido = cliente_rectificacion_produccion.post(
            "/coordinacion/registrar/anexo",
            data={
                "no_sp": "358",
                "tipo_referencia": "RC",
                "numero_anexo": "4",
                "confirmacion_file_server": "y",
            },
            follow_redirects=False,
        )
        assert permitido.status_code == 302

        with app_rectificacion_produccion.app_context():
            assert RegistroCoordinacion.query.filter_by(tipo="ANEXO").count() == 1
    finally:
        app_rectificacion_produccion.config["TESTING"] = True


def test_guard_de_produccion_permite_registro_si_se_confirma_sin_expediente(
    app_rectificacion_produccion,
    cliente_rectificacion_produccion,
):
    app_rectificacion_produccion.config["TESTING"] = False
    try:
        confirmacion = cliente_rectificacion_produccion.post(
            "/coordinacion/rectificacion-produccion/guardar",
            json={
                "no_sp": "358",
                "total_folios": None,
                "total_anexos": 0,
                "sin_expediente_fisico": True,
                "confirmado": True,
                "origen": "anexo",
            },
        )
        assert confirmacion.status_code == 200

        permitido = cliente_rectificacion_produccion.post(
            "/coordinacion/registrar/anexo",
            data={
                "no_sp": "358",
                "tipo_referencia": "RC",
                "numero_anexo": "1",
                "confirmacion_file_server": "y",
            },
            follow_redirects=False,
        )
        assert permitido.status_code == 302

        with app_rectificacion_produccion.app_context():
            expediente = Expediente.query.filter_by(no_sp="358").one()
            assert expediente.expediente_fisico_registrado is False
            assert expediente.folios_rectificados is None
            assert RegistroCoordinacion.query.filter_by(tipo="ANEXO").count() == 1
    finally:
        app_rectificacion_produccion.config["TESTING"] = True
