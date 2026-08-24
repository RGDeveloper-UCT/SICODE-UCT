from config import Config


def test_perfil_cpu_no_duplica_ocr_por_defecto():
    assert Config.DOCUMENT_ANALYSIS_OCR_SECOND_PASS is False


def test_contexto_ia_documental_tiene_limite_conservador():
    assert 2000 <= Config.DOCUMENT_ANALYSIS_AI_MAX_CHARS <= 12000
    assert Config.DOCUMENT_ANALYSIS_AI_TIMEOUT <= 75
