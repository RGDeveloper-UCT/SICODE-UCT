from app.services.analisis_documental_service import TIPOS_EVENTO
from app.services.nexo_autocorreccion_service import (
    es_correccion_ortografica_segura,
    proponer_correcciones_valores,
)


def test_prohibido_asercarse_se_autocorrige_al_95_visible():
    propuestas = proponer_correcciones_valores(["Prohibido Asercarse"] * 3, TIPOS_EVENTO)
    assert len(propuestas) == 1
    propuesta = propuestas[0]
    assert propuesta["canonico"] == "Prohibido acercarse"
    assert propuesta["clasificacion"] == "variante_ortografica"
    assert propuesta["confianza_visible"] >= 95


def test_alias_de_90_no_se_autocorrige():
    propuestas = proponer_correcciones_valores(["ALERTA DE CORREA APERTURA"], TIPOS_EVENTO)
    assert propuestas == []


def test_equivalencia_de_tilde_y_mayuscula_es_100_segura():
    propuestas = proponer_correcciones_valores(["Salida de zona de inclusion"], TIPOS_EVENTO)
    assert len(propuestas) == 1
    assert propuestas[0]["canonico"] == "Salida de zona de inclusión"
    assert propuestas[0]["similitud"] == 100.0


def test_numeros_distintos_bloquean_autocorreccion():
    evaluacion = {
        "valor": "Bateria baja 12%",
        "clasificacion": "variante_ortografica",
        "canonico": "Batería baja 30%",
        "similitud": 99.0,
    }
    assert es_correccion_ortografica_segura(evaluacion) is False


def test_numeros_iguales_permiten_autocorreccion():
    evaluacion = {
        "valor": "Bateria baja 30",
        "clasificacion": "variante_ortografica",
        "canonico": "Batería baja 30%",
        "similitud": 99.0,
    }
    assert es_correccion_ortografica_segura(evaluacion) is True
