"""Pruebas del control 09 en base temporal, nunca en producción."""
import pytest
from flask_login import login_user
from app import create_app, db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.usuario import Usuario
from app.services.bitacora_service import registrar_bitacora
from app.models.bitacora import Bitacora

@pytest.fixture
def contexto():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    # La sesión real de Flask-Login usa protección strong y un identificador
    # de cliente; simular solo _user_id provoca redirección a /login.
    @app.get("/__pruebas_seguridad_09_login")
    def acceso_prueba():
        usuario = Usuario.query.filter_by(usuario="prueba-seg-09").one()
        login_user(usuario, fresh=True)
        return "ok"

    with app.app_context():
        db.create_all()
        try:
            usuario = Usuario(nombre="Responsable Pruebas", usuario="prueba-seg-09",
                password_hash="irrelevante-en-pruebas", rol=Usuario.ROL_ADMINISTRADOR,
                activo=True)
            # El validador de password_hash marca nuevas claves como temporales.
            # En esta prueba, simular explícitamente el cambio ya completado.
            usuario.debe_cambiar_password = False
            db.session.add(usuario)
            db.session.commit()
            yield app, usuario.id
        finally:
            db.session.remove()
            db.drop_all()

def _sesion(client, usuario_id):
    # Solo existe en la aplicación de pruebas, nunca en producción.
    respuesta = client.get("/__pruebas_seguridad_09_login")
    assert respuesta.status_code == 200

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
    assert "/seguridad/" in respuesta.headers["Location"]
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


def test_visor_consulta_pero_no_puede_modificar(contexto):
    app, usuario_id = contexto
    usuario = db.session.get(Usuario, usuario_id)
    usuario.rol = Usuario.ROL_VISOR
    db.session.commit()
    client = app.test_client()
    _sesion(client, usuario_id)

    assert client.get("/coordinacion/seguridad/").status_code == 200
    assert client.get("/coordinacion/seguridad/equipos/nuevo").status_code == 403
    assert client.post("/coordinacion/seguridad/equipos/nuevo",
                       data=_formulario()).status_code == 403
    assert EquipoInstitucional.query.count() == 0

    # Crear un registro desde el contexto de BD solo para probar edición.
    equipo = EquipoInstitucional(**{
        "codigo": "UCT-VISOR-001", "tipo": "COMPUTADORA",
        "nombre": "Consulta visor", "creado_por_id": usuario_id
    })
    db.session.add(equipo)
    db.session.commit()
    url = f"/coordinacion/seguridad/equipos/{equipo.id}/editar"
    assert client.get(url).status_code == 403
    assert client.post(url, data=_formulario(motivo="Intento")).status_code == 403
    db.session.refresh(equipo)
    assert equipo.nombre == "Consulta visor"
    assert Bitacora.query.filter_by(accion="EDITAR_EQUIPO_INSTITUCIONAL").count() == 0


def test_usuario_autorizado_puede_registrar(contexto):
    app, usuario_id = contexto
    usuario = db.session.get(Usuario, usuario_id)
    usuario.rol = Usuario.ROL_AUTORIZADO
    db.session.commit()
    client = app.test_client()
    _sesion(client, usuario_id)
    respuesta = client.post("/coordinacion/seguridad/equipos/nuevo",
                            data=_formulario(codigo="UCT-AUT-001"))
    assert respuesta.status_code == 302
    assert EquipoInstitucional.query.filter_by(codigo="UCT-AUT-001").count() == 1


def test_constancia_requiere_sesion_y_registra_emision(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    equipo = EquipoInstitucional(codigo="UCT-PDF-001", tipo="COMPUTADORA",
                                 nombre="Equipo constancia", creado_por_id=usuario_id)
    db.session.add(equipo)
    db.session.commit()
    url = f"/coordinacion/seguridad/equipos/{equipo.id}/constancia.pdf"
    anonimo = client.get(url)
    assert anonimo.status_code == 302
    assert "/login" in anonimo.headers["Location"]
    _sesion(client, usuario_id)
    pdf = client.get(url)
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert Bitacora.query.filter_by(
        accion="GENERAR_CONSTANCIA_INVENTARIO_EQUIPO",
        entidad_id=str(equipo.id)
    ).count() == 1


def test_paginas_inventario_y_formulario_renderizan(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    pagina = client.get("/coordinacion/seguridad/")
    assert pagina.status_code == 200
    assert b"Inventario institucional" in pagina.data
    nuevo = client.get("/coordinacion/seguridad/equipos/nuevo")
    assert nuevo.status_code == 200
    assert b'name="csrf_token"' in nuevo.data
    assert b'name="codigo"' in nuevo.data

    equipo = EquipoInstitucional(codigo="UCT-HTML-001", nombre="Equipo interfaz",
                                 tipo="COMPUTADORA", creado_por_id=usuario_id)
    db.session.add(equipo)
    db.session.commit()
    listado = client.get("/coordinacion/seguridad/")
    assert listado.status_code == 200
    assert b"UCT-HTML-001" in listado.data
    editar = client.get(f"/coordinacion/seguridad/equipos/{equipo.id}/editar")
    assert editar.status_code == 200
    assert b'name="motivo"' in editar.data
