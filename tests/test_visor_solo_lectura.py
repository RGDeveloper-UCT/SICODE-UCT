from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.alerta import Alerta
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_visor():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.drop_all()
        db.create_all()

        visor = Usuario(
            nombre="Usuario Visor",
            usuario="visor",
            correo="visor@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="visor",
            activo=True,
        )
        admin = Usuario(
            nombre="Admin Visor Test",
            usuario="admin-visor",
            correo="admin-visor@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0900",
            no_sp="900",
            nombre_referencia="Sujeto Consulta",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([visor, admin, expediente])
        db.session.flush()
        db.session.add(Alerta(
            expediente_id=expediente.id,
            tipo_alerta="REVISION_EXPEDIENTE",
            titulo="Alerta de prueba visor",
            descripcion="Solo debe poder consultarse.",
            gravedad="Media",
            estado="Abierta",
            origen="Prueba",
        ))
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


def test_visor_consulta_paneles_y_no_ve_acciones_de_escritura(app_visor):
    cliente = app_visor.test_client()
    _login(cliente, "visor")

    for ruta in ["/dashboard", "/expedientes", "/coordinacion/", "/coordinacion/registros", "/prestamos", "/alertas"]:
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200, ruta

    coordinacion = cliente.get("/coordinacion/").get_data(as_text=True)
    assert "CONSULTA POR TIPO" in coordinacion
    assert "Registrar pago" not in coordinacion
    assert "modo-visor" in coordinacion
    assert "VISOR · SOLO CONSULTA" in coordinacion

    expedientes = cliente.get("/expedientes").get_data(as_text=True)
    assert "Nuevo expediente" not in expedientes
    assert ">Editar<" not in expedientes
    assert "Registrar físico" not in expedientes

    prestamos = cliente.get("/prestamos").get_data(as_text=True)
    assert "Exportar Excel" not in prestamos
    assert "Generar préstamo físico" not in prestamos
    assert "Generar constancia de traslado de expediente virtual" not in prestamos
    assert ">Consulta<" in prestamos

    alertas = cliente.get("/alertas").get_data(as_text=True)
    assert "Cambiar estado:" not in alertas
    assert "Exportar Excel" not in alertas
    assert "modo-visor" in alertas


def test_visor_no_puede_modificar_ni_abrir_formularios_de_accion(app_visor):
    cliente = app_visor.test_client()
    _login(cliente, "visor")

    with app_visor.app_context():
        alerta = Alerta.query.filter_by(titulo="Alerta de prueba visor").one()
        alerta_id = alerta.id

    assert cliente.post(f"/alertas/{alerta_id}/estado/Cerrada").status_code == 403
    assert cliente.post("/coordinacion/registrar/actividad", data={}).status_code == 403
    assert cliente.get("/coordinacion/registrar/actividad").status_code == 403
    assert cliente.get("/expedientes/nuevo").status_code == 403
    assert cliente.get("/alertas/exportar/excel").status_code == 403

    with app_visor.app_context():
        alerta = db.session.get(Alerta, alerta_id)
        assert alerta.estado == "Abierta"


def test_visor_puede_cambiar_su_propia_password(app_visor):
    cliente = app_visor.test_client()
    _login(cliente, "visor")

    respuesta_get = cliente.get("/mi-cuenta/cambiar-password")
    assert respuesta_get.status_code == 200

    respuesta_post = cliente.post(
        "/mi-cuenta/cambiar-password",
        data={
            "password_actual": "Password123",
            "nueva_password": "Password456",
            "confirmar_password": "Password456",
        },
        follow_redirects=False,
    )
    assert respuesta_post.status_code == 302


def test_administrador_puede_asignar_rol_visor(app_visor):
    cliente = app_visor.test_client()
    _login(cliente, "admin-visor")

    respuesta = cliente.get("/admin/usuarios/nuevo")
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert 'value="visor"' in texto
    assert "Visor · solo consulta" in texto
