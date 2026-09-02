from copy import deepcopy

from app.services.analisis_documental_service import TIPOS_ANEXO, TIPOS_EVENTO
from app.services.cerebro_sicode_absorber import estado_cola_aprendizaje
from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE
from app.services.nexo_catalogo_service import evaluar_valor_catalogo, enriquecer_analisis_catalogos
from app.services.nexo_export_service import construir_exportacion_nexo as construir_exportacion_base


VERSION_EXPORTACION_NEXO_SEGURA = 3


def _evaluar_evidencia_valores(evidencia, catalogo):
    valores = dict((evidencia or {}).get("valores") or {})
    salida = []
    for valor, frecuencia in valores.items():
        salida.append(evaluar_valor_catalogo(valor, catalogo, frecuencia=frecuencia))
    return salida


def _sanitizar_hallazgo_historico(item):
    item = deepcopy(item or {})
    descripcion = str(item.get("descripcion") or "")
    evidencia = dict(item.get("evidencia") or {})

    if "Nuevos nombres de evento/reporte" in descripcion:
        item["descripcion"] = (
            "Hallazgo histórico de catálogo de eventos reanalizado por NEXO V2. "
            "Los textos libres potenciales se omiten de esta memoria portable."
        )
        item["evidencia"] = {
            "evaluaciones": _evaluar_evidencia_valores(evidencia, TIPOS_EVENTO),
            "reanalizado_por": "NEXO_V2",
        }
    elif "Tipos de anexo fuera del catálogo" in descripcion:
        item["descripcion"] = "Hallazgo histórico de catálogo de anexos reanalizado por NEXO V2."
        item["evidencia"] = {
            "evaluaciones": _evaluar_evidencia_valores(evidencia, TIPOS_ANEXO),
            "reanalizado_por": "NEXO_V2",
        }
    elif "Tipos documentales no reconocidos por SICODE.IA" in descripcion:
        item["descripcion"] = "Hallazgo histórico de tipos documentales reanalizado por NEXO V2."
        item["evidencia"] = {
            "evaluaciones": _evaluar_evidencia_valores(evidencia, TIPOS_DOCUMENTO_LOTE),
            "reanalizado_por": "NEXO_V2",
        }

    return item


def construir_exportacion_nexo(usuario_id=None):
    """Construye la memoria NEXO v3 reforzando diagnóstico y privacidad.

    Parte del exportador compatible existente, enriquece el análisis actual y
    reanaliza hallazgos históricos de catálogos para no repetir texto libre que
    pudo haberse introducido accidentalmente en campos estructurados.
    """
    paquete = construir_exportacion_base(usuario_id=usuario_id)
    paquete["version_formato"] = VERSION_EXPORTACION_NEXO_SEGURA
    paquete["motor_nexo"] = {
        "version": "2",
        "modo": "aprendizaje supervisado y normalización explicable",
        "decision_automatica_sobre_expedientes": False,
    }

    try:
        paquete["analisis_actual"] = enriquecer_analisis_catalogos(
            paquete.get("analisis_actual") or {}
        )
    except Exception:
        # El exportador base ya tiene su propio diagnóstico resiliente. Esta capa
        # no debe invalidar una exportación que todavía puede resultar útil.
        pass

    try:
        paquete["cola_aprendizaje"] = estado_cola_aprendizaje()
    except Exception:
        paquete["cola_aprendizaje"] = {
            "segmentos_verificados": 0,
            "segmentos_aprendidos": 0,
            "pendientes_aprendizaje": 0,
            "pendientes_validacion_humana": 0,
            "estado": "no_disponible",
        }

    historicos = list(paquete.get("hallazgos_historicos") or [])
    paquete["hallazgos_historicos"] = [
        _sanitizar_hallazgo_historico(item)
        for item in historicos
    ]

    privacidad = dict(paquete.get("privacidad") or {})
    excluido = list(privacidad.get("contenido_excluido") or [])
    extra = "texto libre probable introducido accidentalmente en campos de catálogo"
    if extra not in excluido:
        excluido.append(extra)
    privacidad["contenido_excluido"] = excluido
    privacidad["hallazgos_catalogo_reanalizados"] = True
    paquete["privacidad"] = privacidad

    resumen = dict(paquete.get("resumen_exportacion") or {})
    resumen["version_motor_nexo"] = 2
    resumen["cola_aprendizaje_incluida"] = True
    resumen["normalizacion_explicable"] = True
    paquete["resumen_exportacion"] = resumen
    return paquete
