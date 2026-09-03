import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.cola_recepcion import ColaRecepcionDocumental
from app.models.usuario import Usuario


@pytest.fixture()
def app_cola():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Administrador Cola",
            usuario="admin-cola",
            correo="admin-cola@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        usuario = Usuario(
            nombre="Usuario Operativo",
            usuario="operativo-cola",
            correo="operativo-cola@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="usuario_autorizado",
            activo=True,
        )
        db.session.add_all([admin, usuario])
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


def test_cola_es_exclusiva_de_administracion(app_cola):
    cliente = app_cola.test_client()
    _login(cliente, "operativo-cola")

    respuesta = cliente.get("/admin/cola-recepcion")
    assert respuesta.status_code == 403


def test_admin_registra_pendiente_con_correlativo_y_tareas(app_cola):
    cliente = app_cola.test_client()
    _login(cliente, "admin-cola")

    respuesta = cliente.post(
        "/admin/cola-recepcion",
        data={
            "recibido_en": "2026-09-03T15:00",
            "recibido_de": "Coordinación de monitoreo",
            "descripcion": "300 folders recibidos para procesamiento posterior",
            "ubicacion_temporal": "Archivo personal · estante superior",
            "acciones": ["ARCHIVAR", "REGISTRAR_SICODE", "FOLIAR", "REVISAR_FILE_SERVER"],
            "observaciones": "Priorizar el registro antes del archivo definitivo.",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/admin/cola-recepcion")

    with app_cola.app_context():
        item = ColaRecepcionDocumental.query.one()
        assert item.correlativo == "CRD-2026-00001"
        assert item.estado == "PENDIENTE"
        assert item.recibido_de == "Coordinación de monitoreo"
        assert "FOLIAR" in item.acciones
        assert not hasattr(item, "folios")
        assert Bitacora.query.filter_by(accion="REGISTRAR_COLA_RECEPCION").count() == 1


def test_cola_exige_al_menos_una_tarea(app_cola):
    cliente = app_cola.test_client()
    _login(cliente, "admin-cola")

    respuesta = cliente.post(
        "/admin/cola-recepcion",
        data={
            "recibido_en": "2026-09-03T15:00",
            "recibido_de": "Archivo",
            "descripcion": "Folders pendientes",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Seleccione por lo menos una tarea pendiente" in respuesta.get_data(as_text=True)

    with app_cola.app_context():
        assert ColaRecepcionDocumental.query.count() == 0


def test_admin_actualiza_estado_y_genera_pdf(app_cola):
    cliente = app_cola.test_client()
    _login(cliente, "admin-cola")

    cliente.post(
        "/admin/cola-recepcion",
        data={
            "recibido_en": "2026-09-03T15:00",
            "recibido_de": "Coordinación",
            "descripcion": "Lote para archivo",
            "acciones": ["ARCHIVAR", "RECTIFICAR"],
        },
    )

    with app_cola.app_context():
        item_id = ColaRecepcionDocumental.query.one().id

    respuesta_estado = cliente.post(
        f"/admin/cola-recepcion/{item_id}/estado",
        data={"estado": "COMPLETADO"},
        follow_redirects=False,
    )
    assert respuesta_estado.status_code == 302

    with app_cola.app_context():
        item = db.session.get(ColaRecepcionDocumental, item_id)
        assert item.estado == "COMPLETADO"
        assert item.completado_en is not None

    respuesta_pdf = cliente.get(f"/admin/cola-recepcion/{item_id}/pdf")
    assert respuesta_pdf.status_code == 200
    assert respuesta_pdf.mimetype == "application/pdf"
    assert respuesta_pdf.data.startswith(b"%PDF")
    assert len(respuesta_pdf.data) > 1000

    with app_cola.app_context():
        assert Bitacora.query.filter_by(accion="GENERAR_PDF_COLA_RECEPCION").count() == 1
