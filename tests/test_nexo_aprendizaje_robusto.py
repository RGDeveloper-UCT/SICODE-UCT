from app.services.cerebro_sicode_absorber import _caracteristicas_seguras, _dict_seguro


def test_nexo_ignora_json_historico_que_no_es_diccionario():
    assert _dict_seguro(None) == {}
    assert _dict_seguro([]) == {}
    assert _dict_seguro("texto-antiguo") == {}
    assert _dict_seguro({"modo": "SICODE_IA"}) == {"modo": "SICODE_IA"}


def test_nexo_conserva_solo_caracteristicas_internas_seguras():
    entrada = [
        "kw_providencia",
        {"clave": "kw_acta"},
        17,
        "texto libre",
        "KW_PAGO",
        "kw_providencia",
        None,
    ]

    assert _caracteristicas_seguras(entrada) == ["kw_providencia", "kw_pago"]
    assert _caracteristicas_seguras({"kw_acta": True}) == []
    assert _caracteristicas_seguras("kw_acta") == []
