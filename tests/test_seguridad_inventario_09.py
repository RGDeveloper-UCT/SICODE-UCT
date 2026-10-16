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
        acceso_institucional="si", area="Coordinación Administrativa")
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
    assert "Inventario Tecnológico" in pagina.get_data(as_text=True)
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


def test_personal_y_sicoin_ip(contexto):
    from app.models.personal_institucional import PersonalInstitucional
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    creado = client.post("/coordinacion/seguridad/personal/nuevo", data={
        "nombre": "Persona", "apellido": "Ejemplo",
        "coordinacion": "Coordinación Administrativa",
    })
    assert creado.status_code == 302
    persona = PersonalInstitucional.query.one()
    assert persona.nombre_completo == "Persona Ejemplo"
    r = client.post("/coordinacion/seguridad/equipos/nuevo",
                    data=_formulario(codigo="SICOIN-TEST-01",
                                    ip_estatica="192.0.2.15",
                                    responsable_personal_id=str(persona.id)))
    assert r.status_code == 302
    equipo = EquipoInstitucional.query.filter_by(codigo="SICOIN-TEST-01").one()
    assert equipo.numero_registro.startswith("UCT-EQ-")
    assert equipo.ip_estatica == "192.0.2.15"
    assert equipo.nombre_responsable == "Persona Ejemplo"
    assert equipo.numero_boleta is None


def test_rechaza_ip_y_coordinacion_invalidas(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    assert client.post("/coordinacion/seguridad/equipos/nuevo",
                       data=_formulario(ip_estatica="999.999.999.999")).status_code == 200
    assert client.post("/coordinacion/seguridad/equipos/nuevo",
                       data=_formulario(area="No autorizada")).status_code == 200
    assert EquipoInstitucional.query.count() == 0


def test_boleta_usa_numero_existente_y_enlace(contexto):
    from datetime import datetime
    from app.models.soporte_tecnico import ServicioSoporteTecnico
    from app.models.coordinacion import RegistroCoordinacion
    app, usuario_id = contexto
    equipo = EquipoInstitucional(codigo="SICOIN-BOLETA-001", tipo="COMPUTADORA",
                                 nombre="Equipo relacionado", creado_por_id=usuario_id)
    db.session.add(equipo)
    db.session.flush()
    registro = RegistroCoordinacion(tipo="ACTIVIDAD",
                                   fecha_recepcion=datetime.utcnow().date(),
                                   usuario_id=usuario_id,
                                   estado="Información pendiente",
                                   origen_registro="MANUAL")
    db.session.add(registro)
    db.session.flush()
    boleta = ServicioSoporteTecnico(
        registro_id=registro.id,
        numero_boleta=f"BST-2026-{registro.id:05d}",
        fecha_hora_solicitud=datetime.utcnow(),
        usuario_solicitante="Persona ejemplo",
        coordinacion_area="Coordinación Administrativa",
        tecnico_asignado="Técnico ejemplo",
        descripcion_solicitud="Prueba de enlace",
        equipo_institucional_id=equipo.id,
    )
    db.session.add(boleta)
    db.session.commit()
    db.session.refresh(equipo)
    assert equipo.numero_boleta == boleta.numero_boleta
    assert equipo.numero_registro != boleta.numero_boleta


def test_custodio_y_usuario_habitual_son_independientes(contexto):
    from app.models.personal_institucional import PersonalInstitucional
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    custodio = PersonalInstitucional(nombre="Ana", apellido="Custodia",
                                     coordinacion="Dirección")
    usuario = PersonalInstitucional(nombre="Luis", apellido="Operador",
                                    coordinacion="Dirección")
    db.session.add_all([custodio, usuario])
    db.session.commit()
    pagina = client.get("/coordinacion/seguridad/equipos/nuevo")
    assert pagina.status_code == 200
    assert b'name="responsable_personal_id"' in pagina.data
    assert b'name="usuario_habitual_personal_id"' in pagina.data
    respuesta = client.post("/coordinacion/seguridad/equipos/nuevo",
        data=_formulario(codigo="SICOIN-DOBLE-001",
                        responsable_personal_id=str(custodio.id),
                        usuario_habitual_personal_id=str(usuario.id)))
    assert respuesta.status_code == 302
    equipo = EquipoInstitucional.query.filter_by(codigo="SICOIN-DOBLE-001").one()
    assert equipo.nombre_responsable == "Ana Custodia"
    assert equipo.nombre_usuario_habitual == "Luis Operador"
    assert equipo.snapshot()["usuario_habitual_personal_id"] == usuario.id
    assert "Ana Custodia" in client.get("/coordinacion/seguridad/").get_data(as_text=True)
    assert "Luis Operador" in client.get("/coordinacion/seguridad/").get_data(as_text=True)


def test_catalogo_perifericos_y_usuario_invalido(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    for tipo in ("IMPRESORA", "MOUSE", "TECLADO", "MONITOR", "ESCANER"):
        response = client.post("/coordinacion/seguridad/equipos/nuevo",
            data=_formulario(codigo=f"SICOIN-{tipo}", tipo=tipo))
        assert response.status_code == 302
    response = client.post("/coordinacion/seguridad/equipos/nuevo",
        data=_formulario(codigo="SICOIN-INVALIDO",
                        usuario_habitual_personal_id="999999"))
    assert response.status_code == 200
    assert EquipoInstitucional.query.filter_by(codigo="SICOIN-INVALIDO").count() == 0


def test_registro_multiple_y_pdf_conjunto(contexto):
    from pypdf import PdfReader
    from io import BytesIO
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    datos = _formulario(codigo="SICOIN-GRUPO-001")
    campos = [
        ("codigo", ["SICOIN-MON-001", "SICOIN-MOUSE-002"]),
        ("nombre", ["Monitor principal", "Mouse adicional"]),
        ("marca", ["DELL", "LOGITECH"]),
        ("modelo", ["P2422", "M185"]),
        ("serie", ["MON-001", "MOU-002"]),
        ("ip_estatica", ["", ""]),
        ("ubicacion", ["Oficina", "Oficina"]),
        ("observaciones", ["", ""]),
        ("tipo", ["MONITOR", "MOUSE"]),
        ("area", ["", ""]),
        ("tipo_acceso", ["INTERNO", "INTERNO"]),
        ("estado", ["ACTIVO", "ACTIVO"]),
        ("acceso_institucional", ["si", "no"]),
    ]
    datos.update({"adicional_" + campo: valores for campo, valores in campos})
    res = client.post("/coordinacion/seguridad/equipos/nuevo", data=datos)
    assert res.status_code == 302
    padre = EquipoInstitucional.query.filter_by(codigo="SICOIN-GRUPO-001").one()
    assert len(padre.accesorios) == 2
    assert {e.codigo for e in padre.accesorios} == {"SICOIN-MON-001", "SICOIN-MOUSE-002"}
    assert all(e.equipo_principal_id == padre.id for e in padre.accesorios)
    pdf = client.get(f"/coordinacion/seguridad/equipos/{padre.id}/constancia.pdf")
    assert pdf.status_code == 200
    lector = PdfReader(BytesIO(pdf.data))
    assert len(lector.pages) == 1
    texto = lector.pages[0].extract_text()
    assert "SICOIN-MON-001" in texto and "SICOIN-MOUSE-002" in texto


def test_grupo_no_guarda_parcial_por_codigo_duplicado(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    datos = _formulario(codigo="SICOIN-DUP-GRUPO")
    plantilla = {
        "codigo": ["SICOIN-DUP-GRUPO"], "nombre": ["Mouse"], "marca": [""],
        "modelo": [""], "serie": [""], "ip_estatica": [""],
        "ubicacion": [""], "observaciones": [""], "tipo": ["MOUSE"],
        "area": [""], "tipo_acceso": ["INTERNO"], "estado": ["ACTIVO"],
        "acceso_institucional": ["no"],
    }
    datos.update({"adicional_" + k: v for k, v in plantilla.items()})
    assert client.post("/coordinacion/seguridad/equipos/nuevo", data=datos).status_code == 200
    assert EquipoInstitucional.query.count() == 0


def test_panel_inventario_tecnologico_y_personal_uct(contexto):
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    panel = client.get("/coordinacion/seguridad/")
    assert panel.status_code == 200
    for palabra in ("Inventario Tecnológico", "PERSONAL UCT", "Exportar Excel", "Exportar PDF"):
        assert palabra in panel.get_data(as_text=True)
    personal = client.get("/coordinacion/seguridad/personal/")
    assert personal.status_code == 200
    assert "PERSONAL UCT" in personal.get_data(as_text=True)
    seleccion = client.get("/coordinacion/seguridad/exportar/")
    assert seleccion.status_code == 200
    assert b'name="campos"' in seleccion.data


def test_exportacion_columnas_y_bitacora(contexto):
    from io import BytesIO
    from openpyxl import load_workbook
    from pypdf import PdfReader
    app, usuario_id = contexto
    client = app.test_client()
    _sesion(client, usuario_id)
    equipo = EquipoInstitucional(
        codigo="SICOIN-EXPORT-001", nombre="Estación de prueba",
        tipo="COMPUTADORA", creado_por_id=usuario_id)
    db.session.add(equipo)
    db.session.commit()
    excel = client.post("/coordinacion/seguridad/exportar/",
                        data={"formato": "xlsx", "campos": ["sicoin", "nombre"]})
    assert excel.status_code == 200
    assert excel.data.startswith(b"PK")
    hoja = load_workbook(BytesIO(excel.data)).active
    assert [celda.value for celda in hoja[5]] == ["SICOIN", "Nombre"]
    assert "SICOIN-EXPORT-001" in [row[0] for row in hoja.iter_rows(min_row=6, values_only=True)]
    pdf = client.post("/coordinacion/seguridad/exportar/",
                      data={"formato": "pdf", "campos": ["sicoin", "nombre"]})
    assert pdf.status_code == 200
    texto = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages)
    assert "SICOIN-EXPORT-001" in texto
    assert "SICODE-UCT" in texto
    assert "Exportado por" in texto
    assert Bitacora.query.filter_by(accion="EXPORTAR_INVENTARIO_TECNOLOGICO").count() == 2
    invalido = client.post("/coordinacion/seguridad/exportar/",
                           data={"formato": "xlsx", "campos": ["__dict__"]})
    assert invalido.status_code == 400


def test_personal_uct_exportacion_excel_pdf_campos_y_auditoria(contexto):
    from io import BytesIO
    from openpyxl import load_workbook
    from pypdf import PdfReader
    from app.models.personal_institucional import PersonalInstitucional
    app, usuario_id = contexto
    persona = PersonalInstitucional(
        nombre="Ana", apellido="Ejemplo",
        coordinacion="Coordinación Enlace", activo=True)
    db.session.add(persona)
    db.session.commit()
    client = app.test_client()
    _sesion(client, usuario_id)
    pantalla = client.get("/coordinacion/seguridad/personal/")
    assert pantalla.status_code == 200
    assert "Exportar Excel" in pantalla.get_data(as_text=True)
    assert "Exportar PDF" in pantalla.get_data(as_text=True)
    elegir = client.get("/coordinacion/seguridad/personal/exportar/")
    assert elegir.status_code == 200
    assert 'name="campos"' in elegir.get_data(as_text=True)
    excel = client.post("/coordinacion/seguridad/personal/exportar/",
        data={"formato": "xlsx", "campos": ["nombre", "apellido"]})
    assert excel.status_code == 200
    hoja = load_workbook(BytesIO(excel.data)).active
    assert [c.value for c in hoja[5]] == ["Nombre", "Apellido"]
    assert ("Ana", "Ejemplo") in list(hoja.iter_rows(
        min_row=6, max_col=2, values_only=True))
    pdf = client.post("/coordinacion/seguridad/personal/exportar/",
        data={"formato": "pdf", "campos": ["nombre", "coordinacion"]})
    assert pdf.status_code == 200
    texto = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf.data)).pages)
    assert "Ana" in texto and "PERSONAL UCT" in texto
    assert "SICODE-UCT" in texto
    assert "Exportado por" in texto
    assert Bitacora.query.filter_by(accion="EXPORTAR_PERSONAL_UCT").count() == 2
    error = client.post("/coordinacion/seguridad/personal/exportar/",
        data={"formato": "xlsx", "campos": ["campo_prohibido"]})
    assert error.status_code == 400


def test_personal_uct_exportacion_requires_login(contexto):
    app, _ = contexto
    client = app.test_client()
    assert client.get("/coordinacion/seguridad/personal/exportar/").status_code == 302
    assert client.post("/coordinacion/seguridad/personal/exportar/",
                       data={"formato": "pdf", "campos": ["todos"]}).status_code == 302
