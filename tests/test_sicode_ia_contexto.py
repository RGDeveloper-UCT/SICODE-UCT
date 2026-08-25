from app.services.sicode_ia_contexto import analizar_contexto_usuario, analizar_nombre_pdf, aplicar_contexto_y_nombre


def test_contexto_anexo_sp():
    dato = analizar_contexto_usuario("Voy a subir únicamente el Anexo 1 del SP 359")
    assert dato["no_sp"] == "359"
    assert dato["numero_anexo"] == "1"
    assert dato["alcance"] == "ANEXO"


def test_nombre_rango_acta():
    dato = analizar_nombre_pdf("13-14 Acta de reemplazo certificada.pdf")
    assert dato["folio_inicio"] == 13
    assert dato["folio_fin"] == 14
    assert dato["total_folios"] == 2
    assert dato["tipo_documento_lote"] == "ACTA"


def test_nombre_itr_conserva_catalogo_actual():
    dato = analizar_nombre_pdf("2-3 ITR 66-2026.pdf")
    assert dato["folio_inicio"] == 2
    assert dato["folio_fin"] == 3
    assert dato["tipo_documento_lote"] == "INFORME"
    assert dato["numero_documento"] == "66-2026"
    assert "ITR 66-2026" in dato["nombre_documento"]


def test_nombre_providencia_un_folio():
    dato = analizar_nombre_pdf("4-Providencia.pdf")
    assert dato["folio_inicio"] == 4
    assert dato["folio_fin"] == 4
    assert dato["tipo_documento_lote"] == "PROVIDENCIA"


def test_contexto_nombre_tienen_prioridad_sobre_ocr():
    analisis = {
        "paginas_pdf": 2,
        "paginas_ocr": 2,
        "calidad_global": 40,
        "documentos_total": 2,
        "ia_utilizada": True,
        "ia_modelo": "qwen3:0.6b",
        "pipeline": [],
        "documentos": [
            {"tipo": "OTRO", "pagina_inicio": 1, "pagina_fin": 1, "datos": {}, "confianzas": {}, "fuentes_campos": {}, "discrepancias": [], "caracteristicas": [], "calidad_global": 35, "ia_utilizada": True},
            {"tipo": "PROVIDENCIA", "pagina_inicio": 2, "pagina_fin": 2, "datos": {}, "confianzas": {}, "fuentes_campos": {}, "discrepancias": [], "caracteristicas": [], "calidad_global": 42, "ia_utilizada": True},
        ],
    }
    salida = aplicar_contexto_y_nombre(analisis, "13-14 Acta de reemplazo certificada.pdf", "Anexo 3 del SP 21")
    assert salida["documentos_total"] == 1
    d = salida["documentos"][0]
    assert d["tipo"] == "ACTA"
    assert d["datos"]["no_sp"] == "21"
    assert d["datos"]["numero_anexo"] == "3"
    assert d["datos"]["folio_inicio"] == 13
    assert d["datos"]["folio_fin"] == 14
    assert d["fuentes_campos"]["folio_inicio"] == ["Nombre del PDF"]
