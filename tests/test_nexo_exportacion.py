import json

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.lote_documental import AprendizajeDocumental, PatronAprendizajeDocumental
from app.models.usuario import Usuario


@pytest.fixture()
def app_nexo_export():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all([
            Usuario(
                nombre="Admin NEXO",
                usuario="admin-export",
                correo="admin-export@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="administrador",
                activo=True,
            ),
            Usuario(
                nombre="Usuario NEXO",
                usuario="usuario-export",
                correo="usuario-export@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="usuario_autorizado",
                activo=True,
            ),
        ])
        db.session.add(AprendizajeDocumental(
            tipo_documento="PROVIDENCIA",
            muestras_confirmadas=7,
            clasificaciones_correctas=6,
            reclasificaciones=1,
            campos_confirmados=20,
            campos_corregidos=3,
            nivel_aprendizaje=34,
        ))
        db.session.add(PatronAprendizajeDocumental(
            tipo_documento="PROVIDENCIA",
            caracteristica="kw_providencia",
            aciertos=6,
            errores=1,
            peso=2.0,
        ))
        db.session.add(Bitacora(
            accion="CEREBRO_SICODE_APRENDIZAJE",
            modulo="SICODE.IA",
            entidad="SegmentoDocumental",
            entidad_id="123",
            descripcion="Aprendizaje seguro",
            datos_posteriores={"tipo_confirmado": "PROVIDENCIA", "solo_metadatos": True},
        ))
        db.session.add(Bitacora(
            accion="CEREBRO_SICODE_HALLAZGO",
            modulo="SICODE.IA",
            entidad="CerebroSicode",
            entidad_id="hallazgo-test",
            descripcion="Catálogo con variante documental.",
            datos_posteriores={
                "categoria": "catalogo",
                "prioridad": "media",
                "recomendacion": "Normalizar el catálogo.",
                "evidencia": {"valores": {"Providencia": 3}},
            },
        ))
        db.session.add(Bitacora(
            accion="CEREBRO_SICODE_ESQUEMA",
            modulo="SICODE.IA",
            entidad="CerebroSicode",
            entidad_id="firma-test",
            descripcion="Inventario técnico",
            datos_posteriores={
                "firma_esquema": "firma-test",
                "tablas_total": 2,
                "columnas_total": 4,
                "tablas": [
                    {"tabla": "expedientes", "columnas": ["id", "no_sp"]},
                    {"tabla": "bitacora", "columnas": ["id", "accion"]},
                ],
                "cambio_detectado": False,
                "inventariado_en": "2026-08-31T12:00:00Z",
            },
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


def _parches_exportacion(monkeypatch):
    monkeypatch.setattr(
        "app.services.nexo_export_service.absorber_verificaciones_pendientes",
        lambda usuario_id=None: 0,
    )
    monkeypatch.setattr(
        "app.services.nexo_export_service.inventariar_esquema_sicode",
        lambda usuario_id=None: {
            "firma": "firma-test",
            "tablas_total": 2,
            "columnas_total": 4,
            "cambio_detectado": False,
            "primera_lectura": False,
        },
    )
    monkeypatch.setattr(
        "app.services.nexo_export_service.analizar_sicode",
        lambda: {
            "aprendizaje": {"nivel": 34, "muestras": 7, "precision": 86, "tipos_aprendidos": 1},
            "totales": {"objetos_estudiados": 50},
            "hallazgos": [
                {
                    "firma": "actual-test",
                    "categoria": "catalogo",
                    "titulo": "Variante nueva",
                    "detalle": "Se detectó una variante.",
                    "recomendacion": "Revisar catálogo.",
                    "prioridad": "media",
                    "evidencia": {"variantes": {"ACTA": 2}},
                }
            ],
            "hallazgos_total": 1,
            "estado": "observando",
            "analizado_en": "2026-08-31T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        "app.services.nexo_export_service.guardar_hallazgos",
        lambda resultado, usuario_id=None: 0,
    )


def _claves(objeto):
    claves = set()
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            claves.add(clave)
            claves.update(_claves(valor))
    elif isinstance(objeto, list):
        for valor in objeto:
            claves.update(_claves(valor))
    return claves


def test_admin_descarga_memoria_nexo_json_segura(app_nexo_export, monkeypatch):
    _parches_exportacion(monkeypatch)
    cliente = app_nexo_export.test_client()
    _login(cliente, "admin-export")

    respuesta = cliente.get("/nexo/exportar-aprendizaje")
    data = json.loads(respuesta.get_data(as_text=True))

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/json"
    assert "attachment; filename=\"SICODE_NEXO_APRENDIZAJE_" in respuesta.headers["Content-Disposition"]
    assert respuesta.headers["Cache-Control"].startswith("no-store")
    assert data["formato"] == "SICODE-NEXO-APRENDIZAJE"
    assert data["version_formato"] == 2
    assert data["estado_exportacion"] == "completa"
    assert data["diagnostico_exportacion"]["degradado"] is False
    assert data["aprendizaje"]["perfiles_documentales"][0]["tipo_documento"] == "PROVIDENCIA"
    assert data["aprendizaje"]["patrones_clasificacion"][0]["caracteristica"] == "kw_providencia"
    assert data["aprendizaje"]["eventos_aprendizaje"]["total"] == 1
    assert data["hallazgos_historicos"][0]["firma"] == "hallazgo-test"
    assert data["historial_esquema"][0]["firma_esquema"] == "firma-test"

    claves = _claves(data)
    assert "datos_detectados" not in claves
    assert "datos_confirmados" not in claves
    assert "ip_origen" not in claves
    assert "user_agent" not in claves
    assert "password_hash" not in claves


def test_exportacion_nexo_parcial_no_devuelve_500_si_falla_analisis(app_nexo_export, monkeypatch):
    _parches_exportacion(monkeypatch)

    def fallar_analisis():
        raise RuntimeError("fallo simulado que no debe salir al JSON")

    monkeypatch.setattr("app.services.nexo_export_service.analizar_sicode", fallar_analisis)
    cliente = app_nexo_export.test_client()
    _login(cliente, "admin-export")

    respuesta = cliente.get("/nexo/exportar-aprendizaje")
    data = json.loads(respuesta.get_data(as_text=True))

    assert respuesta.status_code == 200
    assert data["estado_exportacion"] == "parcial"
    assert data["diagnostico_exportacion"]["degradado"] is True
    assert "analisis_sicode" in data["diagnostico_exportacion"]["etapas_con_error"]
    assert data["hallazgos_historicos"][0]["firma"] == "hallazgo-test"
    assert "fallo simulado" not in respuesta.get_data(as_text=True)


def test_exportacion_nexo_genera_diagnostico_aun_si_falla_constructor(app_nexo_export, monkeypatch):
    cliente = app_nexo_export.test_client()
    _login(cliente, "admin-export")

    def fallar_constructor(usuario_id=None):
        raise RuntimeError("detalle interno reservado")

    monkeypatch.setattr("app.routes.nexo_ia.construir_exportacion_nexo", fallar_constructor)

    respuesta = cliente.get("/nexo/exportar-aprendizaje")
    data = json.loads(respuesta.get_data(as_text=True))

    assert respuesta.status_code == 200
    assert data["estado_exportacion"] == "parcial"
    assert data["diagnostico_exportacion"]["etapas_con_error"] == ["exportar_aprendizaje"]
    assert data["diagnostico_exportacion"]["errores"][0]["tipo"] == "RuntimeError"
    assert "detalle interno reservado" not in respuesta.get_data(as_text=True)


def test_exportacion_nexo_restringida_a_administrador(app_nexo_export, monkeypatch):
    _parches_exportacion(monkeypatch)
    cliente = app_nexo_export.test_client()
    _login(cliente, "usuario-export")

    respuesta = cliente.get("/nexo/exportar-aprendizaje")

    assert respuesta.status_code == 403


def test_interfaz_nexo_muestra_boton_exportar_solo_admin():
    from pathlib import Path

    plantilla = Path("app/templates/nexo/inicio.html").read_text(encoding="utf-8")
    assert "Exportar aprendizaje" in plantilla
    assert "nexo_ia.exportar_aprendizaje" in plantilla
    assert 'current_user.rol == "administrador"' in plantilla
