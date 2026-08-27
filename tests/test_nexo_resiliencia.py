import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.usuario import Usuario


@pytest.fixture()
def app_nexo():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin NEXO",
            usuario="admin-nexo",
            correo="admin-nexo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(usuario)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_nexo(app_nexo):
    cliente = app_nexo.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-nexo", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _resultado_ok():
    return {
        "aprendizaje": {"nivel": 12, "muestras": 4, "precision": 100, "tipos_aprendidos": 2},
        "totales": {
            "expedientes": 10,
            "documentos_indice": 20,
            "registros_coordinacion": 5,
            "muestras_ia": 4,
            "objetos_estudiados": 39,
        },
        "hallazgos": [],
        "hallazgos_total": 0,
        "estado": "estable",
        "analizado_en": "2026-08-27T10:00:00Z",
    }


def test_nexo_estado_completo_responde_json(app_nexo, cliente_nexo, monkeypatch):
    monkeypatch.setattr("app.routes.nexo_ia.absorber_verificaciones_pendientes", lambda usuario_id=None: 1)
    monkeypatch.setattr(
        "app.routes.nexo_ia.inventariar_esquema_sicode",
        lambda usuario_id=None: {
            "firma": "abc",
            "tablas_total": 12,
            "columnas_total": 80,
            "cambio_detectado": False,
            "primera_lectura": False,
        },
    )
    monkeypatch.setattr("app.routes.nexo_ia.analizar_sicode", _resultado_ok)
    monkeypatch.setattr("app.routes.nexo_ia.guardar_hallazgos", lambda resultado, usuario_id=None: 0)
    monkeypatch.setattr(
        "app.routes.nexo_ia._estado_ollama",
        lambda: {"nombre": "Ollama", "modo": "IA local", "disponible": True, "modelo": "test"},
    )

    respuesta = cliente_nexo.get("/nexo/estado")
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    assert data["estado"] == "estable"
    assert data["diagnostico"]["degradado"] is False
    assert data["integraciones"]["postgresql"]["disponible"] is True
    assert data["retroalimentaciones_nuevas"] == 1
    assert data["totales"]["objetos_estudiados"] == 39


def test_nexo_aisla_fallo_del_analizador_y_no_devuelve_500(app_nexo, cliente_nexo, monkeypatch):
    monkeypatch.setattr("app.routes.nexo_ia.absorber_verificaciones_pendientes", lambda usuario_id=None: 0)
    monkeypatch.setattr(
        "app.routes.nexo_ia.inventariar_esquema_sicode",
        lambda usuario_id=None: {
            "firma": "abc",
            "tablas_total": 12,
            "columnas_total": 80,
            "cambio_detectado": False,
            "primera_lectura": False,
        },
    )

    def fallar_analisis():
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr("app.routes.nexo_ia.analizar_sicode", fallar_analisis)
    monkeypatch.setattr(
        "app.routes.nexo_ia._estado_ollama",
        lambda: {"nombre": "Ollama", "modo": "IA local", "disponible": False, "modelo": "test"},
    )

    respuesta = cliente_nexo.get("/nexo/estado")
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    assert data["estado"] == "degradado"
    assert data["diagnostico"]["degradado"] is True
    assert "analisis_sicode" in data["diagnostico"]["etapas_con_error"]
    assert "guardar_hallazgos" in data["diagnostico"]["etapas_omitidas"]
    assert data["integraciones"]["postgresql"]["disponible"] is True
    assert data["aprendizaje"]["nivel"] == 0


def test_interfaz_nexo_muestra_diagnostico_parcial_y_tiene_timeout():
    from pathlib import Path

    javascript = Path("app/static/js/nexo.js").read_text(encoding="utf-8")
    assert "AbortController" in javascript
    assert "análisis parcial con diagnóstico" in javascript
    assert "etapas_con_error" in javascript
    assert "actualizarConexion('PostgreSQL'" in javascript
