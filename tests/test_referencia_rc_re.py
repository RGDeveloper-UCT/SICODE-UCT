from app.services.referencia_rc_re import detectar_referencia_rc_re


def test_detecta_rc_como_referencia_independiente():
    dato = detectar_referencia_rc_re("SP 21\nRC No. UCT-CCT-1860-2026\nPROVIDENCIA UCT-CCT-L-200")
    assert dato["tipo"] == "RC"
    assert dato["valor"] == "UCT-CCT-1860-2026"
    assert dato["confianza"] >= 0.90


def test_detecta_re_como_referencia_independiente():
    dato = detectar_referencia_rc_re("SP 21\nR.E. No. UCT-CCT-1901-2026\nACTA 12")
    assert dato["tipo"] == "RE"
    assert dato["valor"] == "UCT-CCT-1901-2026"
    assert dato["confianza"] >= 0.90


def test_re_no_se_confunde_con_reporte_o_resolucion():
    dato = detectar_referencia_rc_re("REPORTE DE EVENTO 2026-44\nRESOLUCION 123-2026\nSP 21")
    assert dato["tipo"] is None
    assert dato["valor"] is None


def test_si_hay_rc_y_re_marca_revision_ambigua():
    dato = detectar_referencia_rc_re("RC UCT-CCT-100-2026\nRE UCT-CCT-101-2026")
    assert dato["tipo"] == "RC"
    assert dato["ambigua"] is True
    assert dato["confianza"] <= 0.86
