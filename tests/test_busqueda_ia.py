from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.ubicacion import UbicacionFisica
from app.models.usuario import Usuario
from app.services.busqueda_ia_service import buscar_por_filtros, interpretar_reglas, normalizar_filtros


@pytest.fixture()
def app_busqueda_ia():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, AI_SEARCH_ENABLED=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin IA",
            usuario="admin-ia",
            correo="admin-ia@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0011",
            no_sp="11",
            nombre_referencia="Sujeto IA",
            estado_administrativo="Activo",
            estado_fisico_documental="Verificado",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.flush()
        db.session.add(UbicacionFisica(expediente_id=expediente.id, archivador="2", estante="A", caja="4"))
        db.session.add(PrestamoExpediente(
            expediente_id=expediente.id,
            numero_control="PRE-IA-001",
            solicitante="Ronny",
            persona_entrega="Admin IA",
            persona_recibe="Ronny",
            fecha_estimada_devolucion=date.today() - timedelta(days=1),
            estado="En préstamo",
            activo=True,
        ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_ia(app_busqueda_ia):
    cliente = app_busqueda_ia.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-ia", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_interpretacion_basica_ubica_sp_y_normaliza_numero():
    filtros = interpretar_reglas("¿Dónde está el expediente del SP 011?")
    assert filtros["ambito"] == "ubicacion"
    assert filtros["no_sp"] == "11"


def test_filtros_ia_descartan_campos_no_autorizados():
    filtros = normalizar_filtros({
        "ambito": "prestamos",
        "prestamo": "vencido",
        "sql": "DROP TABLE expedientes",
        "endpoint": "admin.usuarios",
    })
    assert filtros["ambito"] == "prestamos"
    assert filtros["prestamo"] == "vencido"
    assert "sql" not in filtros
    assert "endpoint" not in filtros


def test_busqueda_estructurada_encuentra_prestamo_vencido(app_busqueda_ia):
    with app_busqueda_ia.app_context():
        filtros = normalizar_filtros({"ambito": "prestamos", "prestamo": "vencido"})
        resultados = buscar_por_filtros(filtros)
        assert len(resultados) == 1
        assert resultados[0]["titulo"] == "PRE-IA-001"
        assert "SP 11" in resultados[0]["detalle"]


def test_panel_ia_explica_uso_y_muestra_estado_de_espera(cliente_ia):
    respuesta = cliente_ia.get("/buscar")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Cómo usar la búsqueda con IA" in texto
    assert "La búsqueda con IA no es instantánea" in texto
    assert "IA procesando la consulta" in texto
    assert "Presione" in texto and "una sola vez" in texto
    assert "¿Cuántos anexos tiene el SP 24?" in texto
    assert 'id="busqueda-ia-cargando"' in texto
    assert 'data-consulta="¿Dónde está el expediente del SP 11?"' in texto


def test_timeout_ia_da_margen_a_servidor_cpu(app_busqueda_ia):
    assert float(app_busqueda_ia.config["OLLAMA_TIMEOUT"]) >= 45


def test_ruta_ia_muestra_resultado_y_registra_bitacora(app_busqueda_ia, cliente_ia, monkeypatch):
    monkeypatch.setattr(
        "app.services.busqueda_ia_service._consultar_ollama",
        lambda _consulta: normalizar_filtros({"ambito": "ubicacion", "no_sp": "11"}),
    )
    respuesta = cliente_ia.post(
        "/buscar/ia",
        data={"consulta_ia": "¿Dónde está el SP 11?"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert b"SP 11" in respuesta.data
    assert b"Ollama local" in respuesta.data

    with app_busqueda_ia.app_context():
        registro = Bitacora.query.filter_by(accion="CONSULTA_IA", modulo="BÚSQUEDA").one()
        assert "cantidad_resultados" in (registro.datos_posteriores or {})
