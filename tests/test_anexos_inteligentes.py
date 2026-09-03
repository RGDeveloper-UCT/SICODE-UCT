from app import create_app
from app.services.catalogo_anexos_service import (
    CATEGORIAS_ANEXOS,
    COMPONENTES_REEMPLAZO,
    catalogo_plano,
    normalizar,
)


def test_catalogo_cubre_tipos_operativos_principales():
    catalogo = catalogo_plano()
    esperados = {
        "REPORTE_MONITOREO",
        "ANALISIS_RIESGO",
        "NOTIFICACION_MOVILIZACION",
        "NOTIFICACION_EXONERACION_PAGO",
        "NOTIFICACION_CAMBIO_RESIDENCIA",
        "NOTIFICACION_CAMBIO_ZONAS",
        "NOTIFICACION_CAMBIO_JUZGADO",
        "SOLICITUD_INFORME_COMPORTAMIENTO",
        "REPORTE_SALIDA_ZONA_INCLUSION",
        "REPORTE_PROHIBIDO_ACERCARSE",
        "REPORTE_INCUMPLIMIENTO",
        "REPORTE_PROXIMIDAD",
        "REPORTE_ZONA_EXCLUSION",
        "REPORTE_APERTURA_CORREA",
        "REPORTE_BATERIA_BAJA_30",
        "REPORTE_BATERIA_BAJA_12",
        "NO_COMUNICACION",
        "PROGRAMACION_AUDIENCIA",
        "PRORROGA_DISPOSITIVO",
        "AMPLIACION_ZONA_INCLUSION",
        "REEMPLAZO_COMPONENTES",
        "OTRO_ANEXO",
    }
    assert esperados <= set(catalogo)


def test_reemplazos_se_modelan_como_componentes_y_no_combinaciones():
    catalogo = catalogo_plano()
    assert catalogo["REEMPLAZO_COMPONENTES"]["modo"] == "componentes"
    etiquetas = {etiqueta for _codigo, etiqueta in COMPONENTES_REEMPLAZO}
    assert {"DCT", "Correa", "Cargador", "Base de cargador", "Cargador inalámbrico"} <= etiquetas
    assert not any("DCT_Y_CORREA" in codigo for codigo in catalogo)


def test_normalizacion_permite_comparar_denominaciones_nexo():
    assert normalizar("ANÁLISIS DE RIESGO") == "ANALISIS DE RIESGO"
    assert normalizar("Notificación de movilización") == "NOTIFICACION DE MOVILIZACION"


def test_categorias_tienen_codigos_unicos_y_tipos_no_repetidos():
    codigos_categoria = [categoria["codigo"] for categoria in CATEGORIAS_ANEXOS]
    assert len(codigos_categoria) == len(set(codigos_categoria))
    codigos_tipo = [codigo for categoria in CATEGORIAS_ANEXOS for codigo, _titulo, _modo in categoria["tipos"]]
    assert len(codigos_tipo) == len(set(codigos_tipo))


def test_blueprint_anexos_inteligentes_esta_registrado():
    app = create_app()
    reglas = {regla.endpoint: regla.rule for regla in app.url_map.iter_rules()}
    assert reglas["anexos_inteligentes.nuevo"] == "/coordinacion/anexos/nuevo"
    assert reglas["anexos_inteligentes.guardar"] == "/coordinacion/anexos/guardar"
