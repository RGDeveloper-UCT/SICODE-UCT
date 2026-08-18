import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.coordinacion import RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.services.busqueda_service import buscar_global
from app.services.integridad_service import ejecutar_control_integridad


@pytest.fixture()
def app_control(tmp_path):
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Admin",
            usuario="admin-control",
            correo="control@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            rol="administrador",
            activo=True,
        )
        db.session.add(admin)
        db.session.flush()
        sp = Expediente(
            codigo_interno="SICODE-UCT-0455",
            no_sp="455",
            nombre_referencia="Persona de prueba",
            estado_administrativo="Activo",
            estado_fisico_documental="Sin expediente físico",
            expediente_fisico_registrado=False,
            activo=True,
        )
        db.session.add(sp)
        db.session.flush()
        db.session.add(RegistroCoordinacion(
            tipo="MONITOREO",
            expediente_id=sp.id,
            no_sp_referencia="455",
            rc="202624183",
            providencia="5956-2026",
            usuario_id=admin.id,
            estado="Información pendiente",
        ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_motor_detecta_sp_sin_expediente_fisico(app_control):
    with app_control.app_context():
        control = ejecutar_control_integridad()
        codigos = {item.codigo for item in control["hallazgos"]}
        assert "EXP-FISICO-001" in codigos
        assert "COORD-PEND-001" in codigos
        assert control["advertencias"] >= 1


def test_busqueda_global_encuentra_sp_y_coordinacion(app_control):
    with app_control.app_context():
        por_sp = buscar_global("455")
        assert any(item["categoria"] == "SP / Expediente" for item in por_sp)
        por_rc = buscar_global("202624183")
        assert any(item["categoria"] == "Coordinación" for item in por_rc)


def test_busqueda_corta_no_hace_consulta(app_control):
    with app_control.app_context():
        assert buscar_global("4") == []


def test_rutas_nuevas_estan_registradas(app_control):
    rutas = {str(regla) for regla in app_control.url_map.iter_rules()}
    assert "/buscar" in rutas
    assert "/admin/integridad/" in rutas
    assert "/expedientes/pendientes-fisicos" in rutas
    app_control.jinja_env.get_template("admin/integridad.html")
    app_control.jinja_env.get_template("busqueda/resultados.html")
