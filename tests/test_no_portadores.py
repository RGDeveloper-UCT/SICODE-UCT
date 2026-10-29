"""No Portadores: aislamiento SP, control documental, préstamos y permisos."""
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models.expediente import Expediente
from app.models.no_portador import NoPortador, DocumentoNP, PrestamoNP, AnexoNP, VerificacionNP, TrasladoVirtualNP
from app.models.usuario import Usuario
from app.models.bitacora import Bitacora


@pytest.fixture()
def app_np():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all([
            Usuario(nombre="Operador NP", usuario="np-operador", correo="np@uct.local",
                    password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                    rol="administrador", activo=True, debe_cambiar_password=False),
            Usuario(nombre="Visor NP", usuario="np-visor", correo="npvisor@uct.local",
                    password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                    rol="visor", activo=True, debe_cambiar_password=False),
            Expediente(codigo_interno="UCT-SP-001", no_sp="001", nombre_referencia="Portador existente",
                       expediente_fisico_registrado=True, activo=True),
        ])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_np(app_np):
    cliente = app_np.test_client()
    respuesta = cliente.post("/login", data={"usuario": "np-operador", "password": "Password123"})
    assert respuesta.status_code == 302
    return cliente


def _crear_np(cliente, numero="001", fisico=True):
    data = {"numero_np": numero, "codigo_interno": f"UCT-NP-{numero}",
            "nombre_referencia": "No Portador Prueba",
            "motivo_no_instalacion": "Instalación no concretada",
            "estado_administrativo": "Activo"}
    if fisico:
        data["expediente_fisico_registrado"] = "y"
    return cliente.post("/no-portadores/nuevo", data=data, follow_redirects=False)


def test_np_independiente_sp_menu_auditoria(app_np, cliente_np):
    r = _crear_np(cliente_np)
    assert r.status_code == 302
    with app_np.app_context():
        np = NoPortador.query.one()
        assert np.numero_np == "NP-001"
        assert np.codigo_interno == "UCT-NP-001"
        assert Expediente.query.count() == 1
        assert Expediente.query.one().no_sp == "1"
        auditoria = Bitacora.query.filter_by(entidad="NoPortador", entidad_id=str(np.id)).one()
        assert auditoria.expediente_id is None
        assert auditoria.modulo == "No Portadores"
        assert "NP" in auditoria.descripcion
    pagina = cliente_np.get("/no-portadores/")
    assert pagina.status_code == 200
    assert "NO PORTADORES" in pagina.get_data(as_text=True)
    assert "NP-001" in pagina.get_data(as_text=True)
    assert "NP-001" not in cliente_np.get("/expedientes").get_data(as_text=True)


def test_registro_duplicado_np_no_modifica_sp(app_np, cliente_np):
    assert _crear_np(cliente_np).status_code == 302
    r = cliente_np.post("/no-portadores/nuevo", data={
        "numero_np": "NP-001", "codigo_interno": "UCT-NP-002",
        "motivo_no_instalacion": "Duplicado", "estado_administrativo": "Activo"
    })
    assert r.status_code == 200
    with app_np.app_context():
        assert NoPortador.query.count() == 1
        assert Expediente.query.count() == 1


def test_rectificacion_documentos_y_prestamo_np(app_np, cliente_np):
    _crear_np(cliente_np)
    prestamo_sin_rectificar = cliente_np.post("/no-portadores/1/prestamos/nuevo",
        data={"solicitante": "Solicitante", "persona_entrega": "Archivo", "persona_recibe": "Unidad"})
    assert prestamo_sin_rectificar.status_code == 302
    with app_np.app_context():
        assert PrestamoNP.query.count() == 0

    assert cliente_np.post("/no-portadores/1/rectificar",
        data={"folios_rectificados": "150", "anexos_rectificados": "0"}).status_code == 302
    with app_np.app_context():
        assert NoPortador.query.one().rectificacion_completa is True

    assert cliente_np.post("/no-portadores/1/documentos/nuevo", data={
        "nombre_documento": "Resolución", "tipo_documento": "Resolución",
        "folio_inicio": "1", "folio_fin": "12", "estado_revision": "Verificado"
    }).status_code == 302
    assert cliente_np.post("/no-portadores/1/documentos/nuevo", data={
        "nombre_documento": "Duplicado", "tipo_documento": "Resolución",
        "folio_inicio": "10", "folio_fin": "15", "estado_revision": "Verificado"
    }).status_code == 302
    with app_np.app_context():
        assert DocumentoNP.query.filter_by(activo=True).count() == 1
        assert NoPortador.query.one().total_folios_activos == 12

    futuro = (date.today() + timedelta(days=7)).isoformat()
    p = cliente_np.post("/no-portadores/1/prestamos/nuevo", data={
        "solicitante": "Solicitante", "persona_entrega": "Archivo",
        "persona_recibe": "Unidad", "fecha_estimada_devolucion": futuro
    })
    assert p.status_code == 302
    assert "/comprobante/pdf" in p.headers["Location"]
    with app_np.app_context():
        prestamo = PrestamoNP.query.one()
        assert prestamo.numero_control.startswith("PRE-NP-")
        assert NoPortador.query.one().disponibilidad == "En préstamo"
    assert cliente_np.get(p.headers["Location"]).data.startswith(b"%PDF")

    doble = cliente_np.post("/no-portadores/1/prestamos/nuevo", data={
        "solicitante": "Otro", "persona_entrega": "Archivo", "persona_recibe": "Unidad"})
    assert doble.status_code == 302
    with app_np.app_context():
        assert PrestamoNP.query.count() == 1

    retorno = cliente_np.post("/no-portadores/1/prestamos/1/devolver", data={
        "persona_devuelve": "Unidad", "persona_recibe_devolucion": "Archivo"})
    assert retorno.status_code == 302
    with app_np.app_context():
        assert PrestamoNP.query.one().estado == "Devuelto"
        assert NoPortador.query.one().disponibilidad == "Disponible"
        assert Expediente.query.count() == 1


def test_anexos_verificaciones_y_traslado_np(app_np, cliente_np):
    _crear_np(cliente_np)
    cliente_np.post("/no-portadores/1/rectificar",
        data={"folios_rectificados": "90", "anexos_rectificados": "1"})
    r = cliente_np.post("/no-portadores/1/anexos/nuevo", data={
        "titulo": "Anexo administrativo", "numero_anexo": "1", "tipo_anexo": "Resolución",
        "folios": "10-14", "escaneado": "y"})
    assert r.status_code == 302
    r = cliente_np.post("/no-portadores/1/verificar", data={
        "tipo": "INTEGRAL", "resultado": "Con observaciones",
        "folios_verificados": "90"})
    assert r.status_code == 302
    with app_np.app_context():
        assert AnexoNP.query.count() == 1
        assert VerificacionNP.query.count() == 1
        assert NoPortador.query.one().estado_fisico_documental == "Con observaciones"

    r = cliente_np.post("/no-portadores/1/traslados/nuevo", data={
        "destinatario": "Unidad de archivo", "dependencia_destino": "UCT",
        "plataforma": "Proton Drive", "enlace_corto": "https://example.org/consulta",
        "asunto": "Consulta de expediente"})
    assert r.status_code == 302
    assert "/constancia/pdf" in r.headers["Location"]
    assert cliente_np.get(r.headers["Location"]).data.startswith(b"%PDF")
    with app_np.app_context():
        assert TrasladoVirtualNP.query.count() == 1


def test_np_visor_solo_lectura(app_np, cliente_np):
    _crear_np(cliente_np)
    visor = app_np.test_client()
    assert visor.post("/login", data={"usuario": "np-visor", "password": "Password123"}).status_code == 302
    assert visor.get("/no-portadores/").status_code == 200
    assert visor.get("/no-portadores/1").status_code == 200
    assert visor.post("/no-portadores/1/rectificar",
        data={"folios_rectificados": "10", "anexos_rectificados": "0"}).status_code == 403
    assert visor.get("/no-portadores/exportar/excel").status_code == 403


def test_np_excel(app_np, cliente_np):
    _crear_np(cliente_np)
    respuesta = cliente_np.get("/no-portadores/exportar/excel")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
