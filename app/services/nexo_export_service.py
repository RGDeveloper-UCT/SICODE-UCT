from collections import Counter
from datetime import datetime

from app import db
from app.models.bitacora import Bitacora
from app.models.lote_documental import AprendizajeDocumental, PatronAprendizajeDocumental
from app.services.analisis_documental_service import TIPOS_ANEXO, TIPOS_EVENTO
from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes
from app.services.cerebro_sicode_schema import inventariar_esquema_sicode
from app.services.cerebro_sicode_service import (
    CAMPOS_SEGUROS_APRENDIZAJE,
    analizar_sicode,
    guardar_hallazgos,
)
from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE


FORMATO_EXPORTACION_NEXO = "SICODE-NEXO-APRENDIZAJE"
VERSION_EXPORTACION_NEXO = 2


def _iso(valor):
    return valor.isoformat(timespec="seconds") + "Z" if valor else None


def _analisis_vacio():
    return {
        "aprendizaje": {
            "nivel": 0,
            "muestras": 0,
            "precision": 0,
            "tipos_aprendidos": 0,
        },
        "totales": {
            "expedientes": 0,
            "documentos_indice": 0,
            "registros_coordinacion": 0,
            "muestras_ia": 0,
            "objetos_estudiados": 0,
        },
        "hallazgos": [],
        "hallazgos_total": 0,
        "estado": "degradado",
        "analizado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _ejecutar_seccion(nombre, funcion, fallback, errores):
    """Aísla fallos para que una sección no invalide toda la exportación."""
    try:
        return funcion(), None
    except Exception as exc:  # pragma: no cover - depende del motor/driver en producción
        try:
            db.session.rollback()
        except Exception:
            pass
        error = {"etapa": nombre, "tipo": exc.__class__.__name__}
        errores.append(error)
        return fallback, error


def _perfiles_aprendidos():
    perfiles = AprendizajeDocumental.query.order_by(AprendizajeDocumental.tipo_documento.asc()).all()
    return [
        {
            "tipo_documento": perfil.tipo_documento,
            "muestras_confirmadas": int(perfil.muestras_confirmadas or 0),
            "clasificaciones_correctas": int(perfil.clasificaciones_correctas or 0),
            "reclasificaciones": int(perfil.reclasificaciones or 0),
            "campos_confirmados": int(perfil.campos_confirmados or 0),
            "campos_corregidos": int(perfil.campos_corregidos or 0),
            "nivel_aprendizaje": int(perfil.nivel_aprendizaje or 0),
            "actualizado_en": _iso(perfil.actualizado_en),
        }
        for perfil in perfiles
    ]


def _patrones_aprendidos():
    patrones = (
        PatronAprendizajeDocumental.query
        .order_by(
            PatronAprendizajeDocumental.tipo_documento.asc(),
            PatronAprendizajeDocumental.caracteristica.asc(),
        )
        .all()
    )
    return [
        {
            "tipo_documento": patron.tipo_documento,
            "caracteristica": patron.caracteristica,
            "aciertos": int(patron.aciertos or 0),
            "errores": int(patron.errores or 0),
            "peso": round(float(patron.peso or 1.0), 4),
            "actualizado_en": _iso(patron.actualizado_en),
        }
        for patron in patrones
    ]


def _resumen_eventos_aprendizaje():
    eventos = (
        Bitacora.query
        .filter_by(accion="CEREBRO_SICODE_APRENDIZAJE", entidad="SegmentoDocumental")
        .order_by(Bitacora.id.asc())
        .all()
    )
    por_tipo = Counter()
    for evento in eventos:
        datos = dict(evento.datos_posteriores or {})
        tipo = str(datos.get("tipo_confirmado") or "SIN_TIPO").upper()
        por_tipo[tipo] += 1
    return {
        "total": len(eventos),
        "por_tipo_documental": dict(sorted(por_tipo.items())),
    }


def _hallazgos_historicos():
    eventos = (
        Bitacora.query
        .filter_by(accion="CEREBRO_SICODE_HALLAZGO", entidad="CerebroSicode")
        .order_by(Bitacora.id.asc())
        .all()
    )
    salida = []
    for evento in eventos:
        datos = dict(evento.datos_posteriores or {})
        salida.append({
            "firma": evento.entidad_id,
            "detectado_en": _iso(evento.creado_en),
            "descripcion": evento.descripcion,
            "categoria": datos.get("categoria"),
            "prioridad": datos.get("prioridad"),
            "recomendacion": datos.get("recomendacion"),
            "evidencia": datos.get("evidencia") or {},
        })
    return salida


def _historial_esquema():
    eventos = (
        Bitacora.query
        .filter_by(accion="CEREBRO_SICODE_ESQUEMA", entidad="CerebroSicode")
        .order_by(Bitacora.id.asc())
        .all()
    )
    salida = []
    for evento in eventos:
        datos = dict(evento.datos_posteriores or {})
        salida.append({
            "firma_esquema": datos.get("firma_esquema") or evento.entidad_id,
            "tablas_total": int(datos.get("tablas_total") or 0),
            "columnas_total": int(datos.get("columnas_total") or 0),
            "tablas": datos.get("tablas") or [],
            "cambio_detectado": bool(datos.get("cambio_detectado")),
            "inventariado_en": datos.get("inventariado_en") or _iso(evento.creado_en),
        })
    return salida


def construir_exportacion_nexo(usuario_id=None):
    """Construye una memoria técnica portable y resiliente de NEXO.

    Cada sección se exporta de forma independiente. Si una consulta falla, NEXO
    conserva las demás secciones, hace rollback de la sesión y deja únicamente el
    nombre de la etapa y el tipo de excepción en el diagnóstico. Nunca incluye el
    mensaje SQL, rutas, credenciales ni datos documentales individuales.
    """
    errores = []

    retroalimentaciones_nuevas, _ = _ejecutar_seccion(
        "aprendizaje_pendiente",
        lambda: absorber_verificaciones_pendientes(usuario_id=usuario_id),
        0,
        errores,
    )
    esquema_actual, _ = _ejecutar_seccion(
        "inventario_esquema",
        lambda: inventariar_esquema_sicode(usuario_id=usuario_id),
        {
            "firma": None,
            "tablas_total": 0,
            "columnas_total": 0,
            "cambio_detectado": False,
            "primera_lectura": False,
        },
        errores,
    )
    analisis_actual, error_analisis = _ejecutar_seccion(
        "analisis_sicode",
        analizar_sicode,
        _analisis_vacio(),
        errores,
    )

    hallazgos_guardados_nuevos = 0
    if error_analisis is None:
        hallazgos_guardados_nuevos, _ = _ejecutar_seccion(
            "guardar_hallazgos",
            lambda: guardar_hallazgos(analisis_actual, usuario_id=usuario_id),
            0,
            errores,
        )

    perfiles, _ = _ejecutar_seccion("perfiles_aprendidos", _perfiles_aprendidos, [], errores)
    patrones, _ = _ejecutar_seccion("patrones_aprendidos", _patrones_aprendidos, [], errores)
    hallazgos_historicos, _ = _ejecutar_seccion(
        "hallazgos_historicos", _hallazgos_historicos, [], errores
    )
    historial_esquema, _ = _ejecutar_seccion("historial_esquema", _historial_esquema, [], errores)
    eventos_aprendizaje, _ = _ejecutar_seccion(
        "eventos_aprendizaje",
        _resumen_eventos_aprendizaje,
        {"total": 0, "por_tipo_documental": {}},
        errores,
    )

    degradado = bool(errores)
    etapas_con_error = [item["etapa"] for item in errores]

    return {
        "formato": FORMATO_EXPORTACION_NEXO,
        "version_formato": VERSION_EXPORTACION_NEXO,
        "generado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "estado_exportacion": "parcial" if degradado else "completa",
        "proposito": (
            "Memoria técnica portable de SICODE NEXO para revisión humana, QA y planificación de mejoras."
        ),
        "privacidad": {
            "solo_metadatos_tecnicos_y_agregados": True,
            "contenido_excluido": [
                "PDF e imágenes",
                "texto OCR completo",
                "datos detectados o confirmados de segmentos individuales",
                "nombres, CUI, direcciones y otros datos personales de DPI",
                "contenido individual de expedientes",
                "credenciales, tokens o secretos",
                "direcciones IP y user-agent",
            ],
        },
        "diagnostico_exportacion": {
            "degradado": degradado,
            "etapas_con_error": etapas_con_error,
            "errores": errores,
            "mensaje": (
                "La exportación contiene información parcial; las etapas indicadas no estuvieron disponibles."
                if degradado
                else "Todas las secciones de la memoria NEXO se exportaron correctamente."
            ),
        },
        "refresco_previo": {
            "retroalimentaciones_nuevas": int(retroalimentaciones_nuevas or 0),
            "hallazgos_guardados_nuevos": int(hallazgos_guardados_nuevos or 0),
        },
        "analisis_actual": analisis_actual,
        "esquema_actual": esquema_actual,
        "aprendizaje": {
            "campos_seguros_observados": list(CAMPOS_SEGUROS_APRENDIZAJE),
            "perfiles_documentales": perfiles,
            "patrones_clasificacion": patrones,
            "eventos_aprendizaje": eventos_aprendizaje,
        },
        "hallazgos_historicos": hallazgos_historicos,
        "historial_esquema": historial_esquema,
        "contexto_clasificador": {
            "tipos_documentales_conocidos": list(TIPOS_DOCUMENTO_LOTE),
            "tipos_evento_conocidos": list(TIPOS_EVENTO),
            "tipos_anexo_conocidos": list(TIPOS_ANEXO),
        },
        "resumen_exportacion": {
            "perfiles_documentales": len(perfiles),
            "patrones_clasificacion": len(patrones),
            "hallazgos_historicos": len(hallazgos_historicos),
            "inventarios_esquema": len(historial_esquema),
            "eventos_aprendizaje": int(eventos_aprendizaje.get("total") or 0),
            "secciones_con_error": len(errores),
        },
    }
