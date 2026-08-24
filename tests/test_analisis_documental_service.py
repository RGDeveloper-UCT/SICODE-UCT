from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfWriter

from app.services.analisis_documental_inteligencia import calcular_calidad_global, fusionar_reglas_e_ia
from app.services.analisis_documental_service import analizar_pdf_temporal, extraer_metadatos


def test_extrae_anexo_sp_y_rango_de_folios():
    texto = """
    UNIDAD DE CONTROL TELEMÁTICO
    SP-011
    ANEXO No. 4 - INFORME DE INSTALACIÓN
    RC: 202624183
    PROVIDENCIA 5908-2026
    FECHA 14/08/2026
    FOLIOS 145 AL 167
    """

    datos, confianzas, advertencias = extraer_metadatos(texto, paginas_pdf=23, tipo_objetivo="ANEXO")

    assert datos["tipo_registro"] == "ANEXO"
    assert datos["no_sp"] == "11"
    assert datos["numero_anexo"] == "4"
    assert datos["folio_inicio"] == 145
    assert datos["folio_fin"] == 167
    assert datos["total_folios"] == 23
    assert datos["folios"] == "23"
    assert confianzas["no_sp"] >= 0.9
    assert confianzas["folio_inicio"] >= 0.9
    assert not any("No se detectó foliación" in mensaje for mensaje in advertencias)


def test_no_confunde_paginas_pdf_con_folios():
    texto = """
    UNIDAD DE CONTROL TELEMÁTICO
    SP 25
    ANEXO 2
    DOCUMENTACIÓN ADMINISTRATIVA
    """

    datos, _confianzas, advertencias = extraer_metadatos(texto, paginas_pdf=18, tipo_objetivo="ANEXO")

    assert datos["paginas_pdf"] == 18
    assert datos["total_folios"] is None
    assert datos["folios"] is None
    assert any("No se detectó foliación explícita" in mensaje for mensaje in advertencias)


def test_clasifica_desinstalacion_sin_forzar_tipo():
    texto = """
    SP: 104
    PROVIDENCIA 8120-2026
    RC 20260099
    DESINSTALACION DE DISPOSITIVO
    FOLIOS 51 A 55
    """

    datos, confianzas, _advertencias = extraer_metadatos(texto, paginas_pdf=5, tipo_objetivo="AUTO")

    assert datos["tipo_registro"] == "DESINSTALACION"
    assert datos["no_sp"] == "104"
    assert datos["total_folios"] == 5
    assert confianzas["tipo_registro"] >= 0.7


def test_ia_refuerza_campo_cuando_coincide_con_reglas():
    datos = {"tipo_registro": "ANEXO", "no_sp": "19", "numero_anexo": "8"}
    confianzas = {"tipo_registro": 1.0, "no_sp": 0.82, "numero_anexo": 0.90}
    ia = {
        "campos": {
            "no_sp": {"valor": "19", "confianza": 0.94},
            "numero_anexo": {"valor": "8", "confianza": 0.92},
        }
    }

    finales, conf_final, fuentes, explicaciones, advertencias = fusionar_reglas_e_ia(datos, confianzas, ia)

    assert finales["no_sp"] == "19"
    assert conf_final["no_sp"] >= 0.94
    assert "IA local" in fuentes["no_sp"]
    assert "coincidieron" in explicaciones["no_sp"]
    assert advertencias == []


def test_ia_no_reemplaza_lectura_deterministica_fuerte_si_difiere():
    datos = {"tipo_registro": "ANEXO", "no_sp": "19"}
    confianzas = {"tipo_registro": 1.0, "no_sp": 0.96}
    ia = {"campos": {"no_sp": {"valor": "119", "confianza": 0.95}}}

    finales, conf_final, fuentes, _explicaciones, advertencias = fusionar_reglas_e_ia(datos, confianzas, ia)

    assert finales["no_sp"] == "19"
    assert conf_final["no_sp"] < 0.96
    assert any("difiere" in fuente for fuente in fuentes["no_sp"])
    assert any("no sp" in mensaje.lower() for mensaje in advertencias)


def test_calidad_global_penaliza_campos_relevantes_ausentes():
    datos = {
        "tipo_registro": "ANEXO",
        "no_sp": "19",
        "fecha_recepcion": None,
        "rc": None,
        "providencia": None,
        "folios": None,
        "numero_anexo": "4",
        "titulo_anexo": None,
        "tipo_anexo": None,
        "folio_inicio": None,
        "folio_fin": None,
    }
    confianzas = {"tipo_registro": 1.0, "no_sp": 0.99, "numero_anexo": 0.98}

    calidad = calcular_calidad_global(datos, confianzas)

    assert 0 < calidad < 70


def test_elimina_pdf_temporal_antes_de_devolver_resultado(tmp_path):
    contenido = BytesIO()
    escritor = PdfWriter()
    escritor.add_blank_page(width=612, height=792)
    escritor.write(contenido)
    contenido.seek(0)

    archivo = SimpleNamespace(stream=contenido)
    resultado = analizar_pdf_temporal(
        archivo,
        tipo_objetivo="ANEXO",
        temp_dir=str(tmp_path),
        max_mb=2,
        max_paginas=5,
        ocr_habilitado=False,
        ia_habilitada=False,
    )

    assert resultado["paginas_pdf"] == 1
    assert list(tmp_path.glob("sicode_doc_*.pdf")) == []
    assert "texto" not in resultado
    assert "archivo" not in resultado
    assert "pipeline_diagnostico" in resultado
    assert resultado["ia_utilizada"] is False
