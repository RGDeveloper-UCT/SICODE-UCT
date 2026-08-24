from app.services.lote_documental_service import (
    _fusionar_clasificaciones,
    _fusionar_datos_segmento,
    _segmentar_paginas,
    clasificar_pagina,
)


def _pagina(numero, texto, tipo, confianza=0.90, inicio=False, caracteristicas=None):
    return {
        "pagina": numero,
        "texto": texto,
        "origen": "OCR",
        "confianza_ocr": 90,
        "tipo": tipo,
        "confianza_tipo": confianza,
        "fuente_tipo": "Reglas UCT",
        "nuevo_documento": inicio,
        "caracteristicas": caracteristicas or [],
    }


def test_clasifica_tipos_documentales_clave():
    casos = [
        ("PROVIDENCIA No. 123-2026 Unidad de Control Telemático", "PROVIDENCIA"),
        ("BOLETA DE DEPOSITO PAGO TOTAL Q 450.00", "PAGO"),
        ("ACTA NUMERO 12-2026", "ACTA"),
        ("DOCUMENTO PERSONAL DE IDENTIFICACION RENAP REPUBLICA DE GUATEMALA", "DPI"),
        ("INFORME IFT I.F.T. seguimiento técnico", "IFT"),
        ("ANEXO No. 4 PRORROGA", "ANEXO"),
    ]
    for texto, esperado in casos:
        resultado = clasificar_pagina(texto)
        assert resultado["tipo"] == esperado
        assert resultado["confianza"] >= 0.55


def test_segmenta_documentos_y_conserva_paginas_continuacion():
    paginas = [
        _pagina(1, "PROVIDENCIA", "PROVIDENCIA", inicio=True),
        _pagina(2, "continuación de providencia", "OTRO", confianza=0.35),
        _pagina(3, "ANEXO No. 1", "ANEXO", inicio=True),
        _pagina(4, "contenido del anexo", "ANEXO", confianza=0.82),
        _pagina(5, "ACTA NUMERO 3", "ACTA", inicio=True),
    ]
    segmentos = _segmentar_paginas(paginas)
    assert len(segmentos) == 3
    assert segmentos[0]["tipo"] == "PROVIDENCIA"
    assert [p["pagina"] for p in segmentos[0]["paginas"]] == [1, 2]
    assert segmentos[1]["tipo"] == "ANEXO"
    assert [p["pagina"] for p in segmentos[1]["paginas"]] == [3, 4]
    assert segmentos[2]["tipo"] == "ACTA"


def test_fusion_reglas_ia_refuerza_coincidencia():
    paginas = [{"pagina": 1, "texto": "ACTA NUMERO 1", "origen": "OCR", "confianza_ocr": 88}]
    reglas = [{"tipo": "ACTA", "confianza": 0.78, "caracteristicas": ["kw_acta"], "inicio_fuerte": True}]
    ia = {1: {"tipo": "ACTA", "confianza": 0.90, "nuevo_documento": True}}
    fusion = _fusionar_clasificaciones(paginas, reglas, ia)
    assert fusion[0]["tipo"] == "ACTA"
    assert fusion[0]["confianza_tipo"] >= 0.94
    assert fusion[0]["fuente_tipo"] == "Reglas + IA"


def test_dpi_no_persiste_identidad_ni_identificadores():
    segmento = {
        "tipo": "DPI",
        "paginas": [
            _pagina(
                1,
                "DOCUMENTO PERSONAL DE IDENTIFICACION RENAP CUI 1234567890101 SP 99",
                "DPI",
                caracteristicas=["kw_dpi"],
            )
        ],
    }
    resultado = _fusionar_datos_segmento(segmento, 1, {})
    datos = resultado["datos"]
    assert resultado["tipo"] == "DPI"
    assert datos.get("no_sp") is None
    assert datos.get("rc") is None
    assert datos.get("providencia") is None
    assert datos.get("numero_documento") is None
    assert any("datos personales no se persisten" in aviso.lower() for aviso in resultado["discrepancias"])


def test_pesos_aprendidos_pueden_reforzar_tipo_sin_guardar_texto():
    pesos = {("ACTA", "kw_acta"): 2.0}
    resultado = clasificar_pagina("ACTA NUMERO 8-2026", pesos)
    assert resultado["tipo"] == "ACTA"
    assert "kw_acta" in resultado["caracteristicas"]
    assert resultado["confianza"] > 0.70
