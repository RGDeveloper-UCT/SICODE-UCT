import json

from app import create_app
from app.routes.admin_sicodeiav3 import (
    GENERADOR_SICODEIAV3,
    SCHEMA_SICODEIAV3,
    _payload_motor,
    _payload_sicodeiav3_desde_texto,
)


def _payload_base(total=1):
    return {
        "schema": SCHEMA_SICODEIAV3,
        "generado_por": GENERADOR_SICODEIAV3,
        "lote": "07092026-ANEXOS-v1",
        "origen_lectura": {
            "proveedor": "GEMINI",
            "fuente": "GOOGLE_DRIVE",
            "carpeta": "07092026",
        },
        "control": {"total_registros": total},
        "registros": [
            {
                "id_fuente": "ANEXO-202",
                "clase_registro": "ANEXO",
                "no_sp": "202",
                "tipo_referencia": "RE",
                "referencia": "RE/20251260",
                "anexo": {
                    "tipo_codigo": "REEMPLAZO_COMPONENTES",
                    "numero_anexo": None,
                    "componentes": ["DCT", "CORREA"],
                    "es_vencido": False,
                },
            }
        ],
    }


def test_rutas_sicodeiav3_quedan_registradas_en_admin():
    app = create_app()
    reglas = {regla.endpoint: regla.rule for regla in app.url_map.iter_rules()}
    assert reglas["admin.sicodeiav3"] == "/admin/sicodeiav3"
    assert reglas["admin.validar_sicodeiav3"] == "/admin/sicodeiav3/validar"
    assert reglas["admin.registrar_sicodeiav3"] == "/admin/sicodeiav3/registrar"


def test_contrato_sicodeiav3_acepta_archivo_final_y_lo_pasa_al_motor():
    payload, error = _payload_sicodeiav3_desde_texto(json.dumps(_payload_base()))
    assert error is None
    assert payload["schema"] == SCHEMA_SICODEIAV3
    assert payload["control"]["total_registros"] == 1

    interno, error = _payload_motor(payload)
    assert error is None
    assert interno["registros"][0]["clase_registro"] == "ANEXO"
    assert interno["registros"][0]["anexo"]["componentes"] == ["DCT", "CORREA"]


def test_sicodeiav3_rechaza_respuesta_directa_de_gemini():
    directo = {
        "schema": "sicode.geminiassist.v1",
        "lote": "07092026",
        "registros": [],
    }
    _datos, error = _payload_sicodeiav3_desde_texto(json.dumps(directo))
    assert error is not None
    assert "No pegue la respuesta de Gemini directamente" in error


def test_sicodeiav3_detecta_archivo_truncado_por_total_inconsistente():
    payload = _payload_base(total=63)
    _datos, error = _payload_sicodeiav3_desde_texto(json.dumps(payload))
    assert error is not None
    assert "declara 63" in error
    assert "contiene 1" in error


def test_sicodeiav3_exige_generador_y_objeto_anexo():
    payload = _payload_base()
    payload["generado_por"] = "GEMINI"
    _datos, error = _payload_sicodeiav3_desde_texto(json.dumps(payload))
    assert error is not None

    payload = _payload_base()
    payload["registros"][0].pop("anexo")
    _datos, error = _payload_sicodeiav3_desde_texto(json.dumps(payload))
    assert error is not None
    assert "requiere el objeto anexo" in error
