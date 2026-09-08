import json

from app import create_app
from app.routes.admin_anexos_asistidos import SCHEMA_GEMINIASSIST, _payload_desde_texto


def test_rutas_geminiassist_y_compatibilidad_quedan_registradas_en_admin():
    app = create_app()
    reglas = {regla.endpoint: regla.rule for regla in app.url_map.iter_rules()}

    assert reglas["admin.geminiassist"] == "/admin/geminiassist"
    assert reglas["admin.validar_geminiassist"] == "/admin/geminiassist/validar"
    assert reglas["admin.registrar_geminiassist"] == "/admin/geminiassist/registrar"
    assert reglas["admin.anexos_asistidos"] == "/admin/anexos-asistidos"


def test_payload_geminiassist_normaliza_anexo_y_pago():
    payload = {
        "schema": SCHEMA_GEMINIASSIST,
        "lote": "07092026",
        "registros": [
            {
                "clase_registro": "ANEXO",
                "no_sp": "202",
                "tipo_referencia": "RE",
                "referencia": "RE/20251260",
                "anexo": {
                    "tipo_codigo": "REEMPLAZO_COMPONENTES",
                    "numero_anexo": None,
                    "componentes": ["DCT", "CORREA"],
                },
            },
            {
                "clase_registro": "PAGO",
                "no_sp": "202",
                "pago": {
                    "periodo_texto": "Agosto 2026",
                    "boleta": "123",
                    "banco": "BANRURAL",
                    "monto": "100.00",
                },
            },
        ],
    }

    datos, error = _payload_desde_texto(json.dumps(payload))
    assert error is None
    assert datos["schema"] == SCHEMA_GEMINIASSIST
    assert datos["registros"][0]["clase_registro"] == "ANEXO"
    assert datos["registros"][0]["anexo"]["componentes"] == ["DCT", "CORREA"]
    assert datos["registros"][1]["clase_registro"] == "PAGO"
    assert datos["registros"][1]["pago"]["boleta"] == "123"


def test_payload_geminiassist_tolera_bloque_json_de_gemini():
    contenido = """Aquí está el resultado:\n```json\n{\"schema\":\"sicode.geminiassist.v1\",\"lote\":\"L1\",\"registros\":[{\"clase_registro\":\"ANEXO\",\"no_sp\":\"1\",\"anexo\":{\"tipo_codigo\":\"PRORROGA_DISPOSITIVO\"}}]}\n```"""
    datos, error = _payload_desde_texto(contenido)
    assert error is None
    assert datos["lote"] == "L1"


def test_payload_legacy_se_convierte_al_contrato_nuevo():
    legado = {
        "schema": "sicode.anexos_asistidos.v1",
        "lote": "LEGACY",
        "registros": [
            {
                "no_sp": "202",
                "tipo_codigo": "REEMPLAZO_COMPONENTES",
                "componentes": ["DCT"],
                "rc": "RE/20251260",
                "tipo_referencia": "RE",
            }
        ],
    }
    datos, error = _payload_desde_texto(json.dumps(legado))
    assert error is None
    assert datos["schema"] == SCHEMA_GEMINIASSIST
    assert datos["registros"][0]["clase_registro"] == "ANEXO"
    assert datos["registros"][0]["anexo"]["tipo_codigo"] == "REEMPLAZO_COMPONENTES"
