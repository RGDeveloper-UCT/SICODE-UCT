"""Regresiones de NEXO 2.0: permisos, propuestas, memoria y modo seguro."""
import json

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.nexo import NexoPropuesta
from app.models.usuario import Usuario
from app.services.nexo_v2_service import (
    actualizar_estado, detectar_propuestas, guardar_propuestas,
    indicadores, resumen_propuestas,
)


@pytest.fixture()
def nexo_v2_app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        for nombre, rol in [("admin-v2", "administrador"), ("usuario-v2", "usuario_autorizado"),
                            ("visor-v2", "visor")]:
            db.session.add(Usuario(
                nombre=nombre, usuario=nombre,
                correo=nombre + "@uct.local",
                password_hash=generate_password_hash("Password123"),
                rol=rol, debe_cambiar_password=False, activo=True,
            ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def login(client, username):
    r = client.post("/login", data={"usuario": username, "password": "Password123"})
    assert r.status_code == 302


def test_analizador_propuestas_solo_usa_cantidades(nexo_v2_app):
    with nexo_v2_app.app_context():
        datos = indicadores()
        assert datos["expedientes_total"] == 0
        assert detectar_propuestas(datos) == []
        datos["prestamos_vencidos"] = 3
        propuestas = detectar_propuestas(datos)
        assert len(propuestas) == 1
        assert propuestas[0]["evidencia"] == {"indicador": "prestamos_vencidos", "cantidad": 3}
        assert "SP" not in propuestas[0]["evidencia"]
        assert guardar_propuestas(propuestas) == 1
        assert guardar_propuestas(propuestas) == 0
        assert NexoPropuesta.query.count() == 1
        memoria = resumen_propuestas()
        assert memoria["por_estado"]["nueva"] == 1
        identificador = memoria["propuestas"][0]["id"]
        actualizada = actualizar_estado(identificador, "aprobada", 1)
        assert actualizada["estado"] == "aprobada"
        assert guardar_propuestas(propuestas) == 0
        assert NexoPropuesta.query.first().estado == "aprobada"


@pytest.mark.parametrize("usuario", ["usuario-v2", "visor-v2"])
def test_no_admin_no_consulta_ni_conversa_ni_revisa(nexo_v2_app, usuario):
    client = nexo_v2_app.test_client()
    login(client, usuario)
    for ruta in ["/nexo/", "/nexo/estado", "/nexo/propuestas", "/nexo/informe",
                 "/coordinacion/analisis-documental/ia/cerebro/estado"]:
        assert client.get(ruta).status_code == 403
    for ruta, datos in [
        ("/nexo/chat", {"pregunta": "Recomienda mejoras"}),
        ("/nexo/revision", {}),
        ("/nexo/propuestas/1/estado", {"estado": "aprobada"}),
    ]:
        assert client.post(ruta, json=datos).status_code == 403


def test_chat_admin_sin_ollama_mantiene_respuesta_agrupada(nexo_v2_app, monkeypatch):
    from urllib.error import URLError

    def ollama_caido(*args, **kwargs):
        raise URLError("fuera de servicio")

    monkeypatch.setattr("app.services.nexo_chat_service.urlrequest.urlopen", ollama_caido)
    client = nexo_v2_app.test_client()
    login(client, "admin-v2")
    r = client.post("/nexo/chat", json={"pregunta": "¿Qué debemos mejorar?"})
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["modo"] == "reglas"
    assert "indicadores" in datos["respuesta"].lower()
    assert client.post("/nexo/chat", json={"pregunta": "1"}).status_code == 400


def test_admin_puede_revisar_y_consultar_reporte(nexo_v2_app):
    client = nexo_v2_app.test_client()
    login(client, "admin-v2")
    r = client.get("/nexo/informe")
    assert r.status_code == 200
    assert r.get_json()["version"] == "NEXO-2.0"
    with nexo_v2_app.app_context():
        guardar_propuestas(detectar_propuestas({"alertas_abiertas": 2}))
        propuesta_id = NexoPropuesta.query.first().id
    r = client.post(f"/nexo/propuestas/{propuesta_id}/estado", json={"estado": "en_revision"})
    assert r.status_code == 200
    assert r.get_json()["propuesta"]["estado"] == "en_revision"
    assert client.post(
        f"/nexo/propuestas/{propuesta_id}/estado", json={"estado": "ejecutada"}
    ).status_code == 400


def test_interfaz_nexo_v2_preserva_csrf_y_no_usar_sql_libre():
    from pathlib import Path
    js = Path("app/static/js/nexo.js").read_text(encoding="utf-8")
    html = Path("app/templates/nexo/inicio.html").read_text(encoding="utf-8")
    assert "X-CSRFToken" in js
    assert "textContent" in js
    assert "data-chat-form" in html
    assert "data-proposals-list" in html
    assert "nexo_ia.informe" in html



def test_aprendizaje_no_queda_atrapado_en_verificaciones_ya_procesadas(nexo_v2_app):
    from app.models.analisis_documental import AnalisisDocumental
    from app.models.bitacora import Bitacora
    from app.models.lote_documental import AprendizajeDocumental, SegmentoDocumental
    from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes

    with nexo_v2_app.app_context():
        analisis = AnalisisDocumental(
            usuario_id=1, tipo_objetivo="LOTE", tipo_detectado="LOTE_DOCUMENTAL",
            metodo_extraccion="SICODE_IA",
            datos_detectados={"modo": "SICODE_IA"},
        )
        db.session.add(analisis)
        db.session.flush()
        for orden in range(1, 14):
            segmento = SegmentoDocumental(
                analisis_id=analisis.id, orden=orden, pagina_inicio=1, pagina_fin=1,
                tipo_detectado="ACTA", tipo_confirmado="ACTA",
                estado="VERIFICADO_HUMANO",
                datos_detectados={"tipo_documento_lote": "ACTA"},
                datos_confirmados={"tipo_documento_lote": "ACTA"},
                caracteristicas_clasificacion=["kw_acta"],
            )
            db.session.add(segmento)
            db.session.flush()
            if orden <= 12:
                db.session.add(Bitacora(
                    accion="CEREBRO_SICODE_APRENDIZAJE", modulo="SICODE.IA",
                    entidad="SegmentoDocumental", entidad_id=str(segmento.id),
                ))
        db.session.commit()
        assert absorber_verificaciones_pendientes(max_examinadas=2, lote=1) == 1
        assert AprendizajeDocumental.query.filter_by(tipo_documento="ACTA").first().muestras_confirmadas == 1
        assert absorber_verificaciones_pendientes(max_examinadas=2, lote=1) == 0
