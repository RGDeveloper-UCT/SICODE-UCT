from types import SimpleNamespace

from flask import current_app

from app import db
from app.models.bitacora import Bitacora
from app.models.lote_documental import SegmentoDocumental
from app.services.cerebro_sicode_service import retroalimentar_segmento


def _dict_seguro(valor):
    """Devuelve solo diccionarios JSON válidos; cualquier otra forma se ignora."""
    return dict(valor) if isinstance(valor, dict) else {}


def _caracteristicas_seguras(valor):
    """Conserva únicamente claves internas de clasificación predefinibles."""
    if not isinstance(valor, (list, tuple, set)):
        return []

    salida = []
    for item in valor:
        if not isinstance(item, str):
            continue
        clave = item.strip().lower()
        if clave.startswith("kw_") and 3 < len(clave) <= 80:
            salida.append(clave)
    return list(dict.fromkeys(salida))


def _es_muestra_sicode_ia(segmento):
    """Reconoce muestras nuevas e históricas de SICODE.IA.

    Versiones previas dependían exclusivamente de datos_detectados['modo']; algunos
    análisis antiguos solo conservaron metodo_extraccion. Aceptar ambas señales
    permite recuperar retroalimentación válida sin tocar contenido documental.
    """
    analisis = getattr(segmento, "analisis", None)
    if analisis is None:
        return False

    meta = _dict_seguro(getattr(analisis, "datos_detectados", None))
    modo = str(meta.get("modo") or "").strip().upper()
    metodo = str(getattr(analisis, "metodo_extraccion", "") or "").strip().upper()
    tipo = str(getattr(analisis, "tipo_detectado", "") or "").strip().upper()

    return modo == "SICODE_IA" or metodo == "SICODE_IA" or tipo == "LOTE_DOCUMENTAL"


def _marca_aprendizaje(segmento_id):
    return Bitacora.query.filter_by(
        accion="CEREBRO_SICODE_APRENDIZAJE",
        entidad="SegmentoDocumental",
        entidad_id=str(segmento_id),
    ).first()


def incorporar_segmento_verificado(segmento, usuario_id=None, commit=True):
    """Incorpora una verificación humana una sola vez al aprendizaje de NEXO.

    Devuelve True cuando la muestra se incorporó y False cuando no era elegible o
    ya había sido aprendida. Solo utiliza metadatos seguros y características kw_*.
    """
    if segmento is None:
        return False
    if segmento.estado not in {"VERIFICADO_HUMANO", "CONFIRMADO"}:
        return False
    if not segmento.datos_confirmados:
        return False
    if not _es_muestra_sicode_ia(segmento):
        return False
    if _marca_aprendizaje(segmento.id):
        return False

    datos = _dict_seguro(segmento.datos_confirmados)
    if not datos:
        return False

    tipo = str(
        datos.get("tipo_documento_lote")
        or segmento.tipo_confirmado
        or segmento.tipo_detectado
        or "OTRO"
    ).strip().upper()

    muestra_segura = SimpleNamespace(
        tipo_detectado=str(segmento.tipo_detectado or "OTRO").strip().upper(),
        datos_detectados=_dict_seguro(segmento.datos_detectados),
        caracteristicas_clasificacion=_caracteristicas_seguras(
            segmento.caracteristicas_clasificacion
        ),
    )
    retroalimentar_segmento(muestra_segura, tipo, datos)

    db.session.add(Bitacora(
        usuario_id=usuario_id,
        expediente_id=segmento.expediente_id,
        accion="CEREBRO_SICODE_APRENDIZAJE",
        modulo="SICODE.IA",
        descripcion=(
            f"El cerebro incorporó la verificación humana del segmento "
            f"{segmento.id} como {tipo}."
        ),
        entidad="SegmentoDocumental",
        entidad_id=str(segmento.id),
        datos_posteriores={
            "tipo_detectado": segmento.tipo_detectado,
            "tipo_confirmado": tipo,
            "caracteristicas": _caracteristicas_seguras(segmento.caracteristicas_clasificacion),
            "solo_metadatos": True,
            "pdf_almacenado": False,
        },
        motivo="Retroalimentación de clasificación y extracción validada por usuario",
    ))

    if commit:
        db.session.commit()
    return True


def estado_cola_aprendizaje():
    """Resume el flujo de verificación -> aprendizaje sin exponer documentos."""
    verificadas = (
        SegmentoDocumental.query
        .filter(SegmentoDocumental.estado.in_(["VERIFICADO_HUMANO", "CONFIRMADO"]))
        .filter(SegmentoDocumental.datos_confirmados.isnot(None))
        .count()
    )
    pendientes_validacion = SegmentoDocumental.query.filter_by(estado="PENDIENTE_VALIDACION").count()
    aprendidas = Bitacora.query.filter_by(
        accion="CEREBRO_SICODE_APRENDIZAJE",
        entidad="SegmentoDocumental",
    ).count()

    return {
        "segmentos_verificados": int(verificadas or 0),
        "segmentos_aprendidos": int(aprendidas or 0),
        "pendientes_aprendizaje": max(0, int(verificadas or 0) - int(aprendidas or 0)),
        "pendientes_validacion_humana": int(pendientes_validacion or 0),
    }


def absorber_verificaciones_pendientes(usuario_id=None):
    """Incorpora una sola vez cada verificación humana realizada en SICODE.IA.

    Una muestra antigua o malformada no debe bloquear el aprendizaje de las demás.
    NEXO trabaja con una vista sanitizada de los metadatos y confirma cada muestra
    individualmente para conservar el progreso aunque otra muestra sea inválida.
    """
    segmentos = (
        SegmentoDocumental.query
        .filter(SegmentoDocumental.estado.in_(["VERIFICADO_HUMANO", "CONFIRMADO"]))
        .filter(SegmentoDocumental.datos_confirmados.isnot(None))
        .order_by(SegmentoDocumental.id.asc())
        .limit(2000)
        .all()
    )

    aprendidas = 0
    omitidas = 0

    for segmento in segmentos:
        try:
            if incorporar_segmento_verificado(segmento, usuario_id=usuario_id, commit=True):
                aprendidas += 1
        except Exception as exc:  # pragma: no cover - depende de datos históricos reales
            db.session.rollback()
            omitidas += 1
            current_app.logger.exception(
                "NEXO omitió la muestra %s durante aprendizaje (%s)",
                getattr(segmento, "id", "sin-id"),
                exc.__class__.__name__,
            )
            continue

    if omitidas:
        current_app.logger.warning(
            "NEXO finalizó aprendizaje con %s muestra(s) omitida(s) y %s aprendida(s)",
            omitidas,
            aprendidas,
        )

    return aprendidas
