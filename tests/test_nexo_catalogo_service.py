from app.services.nexo_catalogo_service import evaluar_valor_catalogo
from app.services.nexo_export_seguro_service import _evaluar_contextual


EVENTOS = (
    "Prohibido acercarse",
    "Salida de zona de inclusión",
    "Salida",
    "Apertura",
    "Victim Proximity",
    "Seguimiento de proximidad",
    "Batería baja 30%",
    "Batería baja 12%",
    "No comunicación",
    "Ingreso prevención",
)

ANEXOS = (
    "REEMPLAZO",
    "MOVILIZACION",
    "AMPLIACION ZONA",
    "EXONERACION",
    "PRORROGA",
    "ZONA DE INCLUSION",
    "CARGADOR",
    "CORREA",
    "CAMBIO JUZGADO",
)

DOCUMENTOS = (
    "PAGO",
    "PROVIDENCIA",
    "ANEXO",
    "IFT",
    "ACTA",
    "DPI",
    "INSTALACION",
    "DESINSTALACION",
    "MONITOREO",
    "OFICIO",
    "INFORME",
    "RESOLUCION",
    "FORMULARIO",
    "OTRO",
)


def test_detecta_variante_ortografica_sin_crear_categoria():
    resultado = evaluar_valor_catalogo("Prohibido Asercarse", EVENTOS, frecuencia=15)
    assert resultado["clasificacion"] in {"variante_ortografica", "alias_probable"}
    assert resultado["canonico"] == "Prohibido acercarse"
    assert resultado["accion"] in {"normalizar_a_canonico", "revisar_alias"}


def test_detecta_alias_probable():
    resultado = evaluar_valor_catalogo("Victim Proximity GPS", EVENTOS, frecuencia=5)
    assert resultado["clasificacion"] in {"variante_ortografica", "alias_probable"}
    assert resultado["canonico"] == "Victim Proximity"


def test_no_aplica_no_se_promueve_a_categoria():
    resultado = evaluar_valor_catalogo("No aplica", EVENTOS, frecuencia=3)
    assert resultado["clasificacion"] == "valor_especial"
    assert resultado["accion"] == "no_promover_catalogo"


def test_texto_libre_se_omite_por_privacidad():
    resultado = evaluar_valor_catalogo(
        "SE DEVOLVIERON AL RESPONSABLE PORQUE LOS DOCUMENTOS NO TENIAN FIRMA",
        EVENTOS,
        frecuencia=2,
    )
    assert resultado["clasificacion"] == "texto_libre_probable"
    assert resultado["valor"] == "[texto libre omitido]"
    assert resultado["contenido_omitido_privacidad"] is True
    assert len(resultado["huella"]) == 16


def test_valor_recurrente_distinto_pasa_a_revision_institucional():
    resultado = evaluar_valor_catalogo("Evento institucional completamente nuevo", EVENTOS, frecuencia=8)
    assert resultado["clasificacion"] in {
        "candidato_nueva_categoria",
        "alias_probable",
        "variante_ortografica",
    }
    if resultado["clasificacion"] == "candidato_nueva_categoria":
        assert resultado["accion"] == "validar_categoria_institucional"


def test_reporte_monitoreo_en_anexos_se_marca_como_posible_campo_incorrecto():
    resultado = _evaluar_contextual(
        "REPORTE DE MONITOREO",
        41,
        ANEXOS,
        catalogos_alternos=[("tipos documentales", DOCUMENTOS)],
    )
    assert resultado["clasificacion"] == "posible_campo_incorrecto"
    assert resultado["catalogo_probable"] == "tipos documentales"
    assert resultado["canonico_alternativo"] == "MONITOREO"
    assert resultado["accion"] == "revisar_campo_origen"
