import json

from app import create_app
from app.routes.admin_anexos_asistidos import SCHEMA_ASISTIDO, _payload_desde_texto


def test_rutas_carga_asistida_quedan_registradas_en_admin():
    app = create_app()
    reglas = {regla.endpoint: regla.rule for regla in app.url_map.iter_rules()}

    assert reglas["admin.anexos_asistidos"] == "/admin/anexos-asistidos"
    assert reglas["admin.validar_anexos_asistidos"] == "/admin/anexos-asistidos/validar"
    assert reglas["admin.registrar_anexos_asistidos"] == "/admin/anexos-asistidos/registrar"


def test_payload_asistido_exige_schema_lote_y_registros():
    payload = {
        "schema": SCHEMA_ASISTIDO,
        "lote": "07092026",
        "registros": [
            {
                "no_sp": "202",
                "tipo_codigo": "REEMPLAZO_COMPONENTES",
                "componentes": ["DCT", "CORREA"],
            }
        ],
    }

    datos, error = _payload_desde_texto(json.dumps(payload))
    assert error is None
    assert datos["lote"] == "07092026"

    _datos, error = _payload_desde_texto(json.dumps({"schema": "otro", "lote": "X", "registros": [{}]}))
    assert error is not None

    _datos, error = _payload_desde_texto("no-es-json")
    assert error is not None
