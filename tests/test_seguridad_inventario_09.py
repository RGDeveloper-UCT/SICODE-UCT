"""Pruebas del control 09 en base temporal, nunca en producción."""
import pytest
from app import create_app, db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.usuario import Usuario
from app.services.bitacora_service import registrar_bitacora
from app.models.bitacora import Bitacora

@pytest.fixture
def contexto():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        try:
            usuario = Usuario(nombre="Responsable Pruebas", usuario="prueba-seg-09",
                password_hash="irrelevante-en-pruebas", rol=Usuario.ROL_ADMINISTRADOR,
                activo=True, debe_cambiar_password=False)
            db.session.add(usuario)
            db.session.commit()
            yield app, usuario.id
        finally:
            db.session.remove()
            db.drop_all()

def _sesion(client, usuario_id):
    with client.session_transaction() as sesion:
        sesion["_user_id"] = str(usuario_id)
        sesion["_fresh"] = True

def _formulario(**cambios):
    datos = dict(codigo="UCT-TEST-001", nombre="Equipo de pruebas",
        tipo="COMPUTADORA", estado="ACTIVO", tipo_acceso="INTERNO",
        acceso_institucional="si", area="Coordinación")
    datos.update(cambios)
    return datos

def test_registro_edicion_y_bitacora(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    respuesta = client.post("/coordinacion/seguridad/equipos/nuevo",
        data=_formulario(), follow_redirects=False)
    assert respuesta.status_code == 302
    equipo = EquipoInstitucional.query.filter_by(codigo="UCT-TEST-001").one()
    assert Bitacora.query.filter_by(accion="CREAR_EQUIPO_INSTITUCIONAL", entidad_id=str(equipo.id)).count() == 1
    respuesta = client.post(f"/coordinacion/seguridad/equipos/{equipo.id}/editar",
        data=_formulario(nombre="Equipo corregido", motivo="Corrección de captura"))
    assert respuesta.status_code == 302
    db.session.refresh(equipo)
    assert equipo.nombre == "Equipo corregido"
    evento = Bitacora.query.filter_by(accion="EDITAR_EQUIPO_INSTITUCIONAL", entidad_id=str(equipo.id)).one()
    assert evento.datos_anteriores["nombre"] == "Equipo de pruebas"
    assert evento.datos_posteriores["nombre"] == "Equipo corregido"
    assert evento.motivo == "Corrección de captura"

def test_edicion_exige_motivo(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    client.post("/coordinacion/seguridad/equipos/nuevo", data=_formulario())
    equipo = EquipoInstitucional.query.filter_by(codigo="UCT-TEST-001").one()
    respuesta = client.post(f"/coordinacion/seguridad/equipos/{equipo.id}/editar",
        data=_formulario(nombre="No autorizado", motivo=""))
    assert respuesta.status_code == 200
    db.session.refresh(equipo)
    assert equipo.nombre == "Equipo de pruebas"

def test_duplicados_y_constancia(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    client.post("/coordinacion/seguridad/equipos/nuevo", data=_formulario())
    resultado = client.post("/coordinacion/seguridad/equipos/nuevo", data=_formulario())
    assert resultado.status_code == 200
    assert EquipoInstitucional.query.count() == 1
    equipo = EquipoInstitucional.query.one()
    pdf = client.get(f"/coordinacion/seguridad/equipos/{equipo.id}/constancia.pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")
