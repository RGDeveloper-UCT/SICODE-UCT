from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.coordinacion import PagoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_pendientes():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()

        usuario = Usuario(
            nombre="Administrador Pendientes",
            usuario="admin-pendientes",
            correo="admin-pendientes@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-PEND-001",
            no_sp="9001",
            nombre_referencia="Prueba pendientes",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.flush()

        registro = RegistroCoordinacion(
            tipo="PAGO",
            expediente_id=expediente.id,
            no_sp_referencia=expediente.no_sp,
            rc="RC 100",
            providencia="PROV-100",
            fecha_recepcion=date(2026, 9, 1),
            persona_entrega="Mesa de entrada",
            folios_recepcion="10-11",
            usuario_id=usuario.id,
            usuario_origen=usuario.nombre,
            estado="Información pendiente",
            origen_registro="HISTORICO",
        )
        db.session.add(registro)
        db.session.flush()
        db.session.add(PagoCoordinacion(
            registro_id=registro.id,
            boleta="B-100",
            banco="BANRURAL",
            total=100,
        ))
        db.session.commit()
        registro_id = registro.id

    yield app, registro_id

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _cliente(app):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-pendientes", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _datos_base(confirmar=True, **cambios):
    datos = {
        "no_sp": "9001",
        "fecha_recepcion": "2026-09-01",
        "rc": "RC 100",
        "providencia": "PROV-100",
        "persona_entrega": "Mesa de entrada",
        "folios_recepcion": "10-11",
        "observaciones": "",
        "periodo_desde": "",
        "periodo_hasta": "",
        "periodo_texto": "",
        "boleta": "B-100",
        "banco": "BANRURAL",
        "total": "100.00",
        "motivo_rectificacion": "",
    }
    if confirmar:
        datos["confirmacion_file_server"] = "1"
    datos.update(cambios)
    return datos


def test_tarjeta_coordinacion_carga_enlace_a_bandeja(app_pendientes):
    app, _ = app_pendientes
    cliente = _cliente(app)
    respuesta = cliente.get("/coordinacion/")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "js/coordinacion_pendientes.js" in html
    assert "Información pendiente" in html


def test_bandeja_lista_registro_pendiente(app_pendientes):
    app, registro_id = app_pendientes
    cliente = _cliente(app)
    respuesta = cliente.get("/coordinacion/pendientes")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Verificación de información pendiente" in html
    assert "RC 100" in html
    assert f"/coordinacion/pendientes/{registro_id}" in html


def test_no_permite_verificar_sin_confirmar_file_server(app_pendientes):
    app, registro_id = app_pendientes
    cliente = _cliente(app)

    respuesta = cliente.post(
        f"/coordinacion/pendientes/{registro_id}",
        data=_datos_base(confirmar=False),
        follow_redirects=False,
    )
    assert respuesta.status_code == 400

    with app.app_context():
        registro = db.session.get(RegistroCoordinacion, registro_id)
        assert registro.estado == "Información pendiente"
        assert Bitacora.query.filter_by(accion="VERIFICAR_COORDINACION_FILE_SERVER").count() == 0


def test_verificacion_sin_cambios_cierra_pendiente_y_deja_bitacora(app_pendientes):
    app, registro_id = app_pendientes
    cliente = _cliente(app)

    respuesta = cliente.post(
        f"/coordinacion/pendientes/{registro_id}",
        data=_datos_base(),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app.app_context():
        registro = db.session.get(RegistroCoordinacion, registro_id)
        assert registro.estado == "Completo"
        evento = Bitacora.query.filter_by(
            accion="VERIFICAR_COORDINACION_FILE_SERVER",
            entidad="RegistroCoordinacion",
            entidad_id=registro_id,
        ).one()
        assert evento.motivo == "Verificación humana contra File Server"


def test_rectificacion_exige_motivo_y_guarda_antes_despues(app_pendientes):
    app, registro_id = app_pendientes
    cliente = _cliente(app)

    sin_motivo = cliente.post(
        f"/coordinacion/pendientes/{registro_id}",
        data=_datos_base(rc="RC 101"),
        follow_redirects=False,
    )
    assert sin_motivo.status_code == 400

    with app.app_context():
        assert db.session.get(RegistroCoordinacion, registro_id).rc == "RC 100"

    respuesta = cliente.post(
        f"/coordinacion/pendientes/{registro_id}",
        data=_datos_base(
            rc="RC 101",
            motivo_rectificacion="RC corregida luego de contrastar con File Server.",
        ),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app.app_context():
        registro = db.session.get(RegistroCoordinacion, registro_id)
        assert registro.rc == "RC 101"
        assert registro.estado == "Completo"
        evento = Bitacora.query.filter_by(
            accion="VERIFICAR_Y_RECTIFICAR_COORDINACION",
            entidad="RegistroCoordinacion",
            entidad_id=registro_id,
        ).one()
        assert evento.datos_anteriores["rc"] == "RC 100"
        assert evento.datos_posteriores["rc"] == "RC 101"
        assert "File Server" in evento.motivo
