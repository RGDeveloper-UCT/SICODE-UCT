from app import db
from app.models.bitacora import Bitacora
from app.models.lote_documental import SegmentoDocumental
from app.services.cerebro_sicode_service import retroalimentar_segmento


def absorber_verificaciones_pendientes(usuario_id=None):
    """Incorpora una sola vez cada verificación humana realizada en SICODE.IA."""
    segmentos = (
        SegmentoDocumental.query
        .filter(SegmentoDocumental.estado.in_(["VERIFICADO_HUMANO", "CONFIRMADO"]))
        .filter(SegmentoDocumental.datos_confirmados.isnot(None))
        .order_by(SegmentoDocumental.id.asc())
        .limit(1000)
        .all()
    )
    aprendidas = 0
    for segmento in segmentos:
        meta_analisis = dict((segmento.analisis.datos_detectados if segmento.analisis else {}) or {})
        if meta_analisis.get("modo") != "SICODE_IA":
            continue

        marca = Bitacora.query.filter_by(
            accion="CEREBRO_SICODE_APRENDIZAJE",
            entidad="SegmentoDocumental",
            entidad_id=str(segmento.id),
        ).first()
        if marca:
            continue

        datos = dict(segmento.datos_confirmados or {})
        tipo = str(datos.get("tipo_documento_lote") or segmento.tipo_confirmado or segmento.tipo_detectado or "OTRO").upper()
        retroalimentar_segmento(segmento, tipo, datos)
        db.session.add(Bitacora(
            usuario_id=usuario_id,
            expediente_id=segmento.expediente_id,
            accion="CEREBRO_SICODE_APRENDIZAJE",
            modulo="SICODE.IA",
            descripcion=f"El cerebro incorporó la verificación humana del segmento {segmento.id} como {tipo}.",
            entidad="SegmentoDocumental",
            entidad_id=str(segmento.id),
            datos_posteriores={
                "tipo_detectado": segmento.tipo_detectado,
                "tipo_confirmado": tipo,
                "solo_metadatos": True,
                "pdf_almacenado": False,
            },
            motivo="Retroalimentación de clasificación y extracción validada por usuario",
        ))
        aprendidas += 1

    if aprendidas:
        db.session.commit()
    return aprendidas
