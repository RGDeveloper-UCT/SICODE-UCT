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
        .limit(1000)
        .all()
    )

    aprendidas = 0
    omitidas = 0

    for segmento in segmentos:
        try:
            meta_analisis = _dict_seguro(
                segmento.analisis.datos_detectados if segmento.analisis else None
            )
            if meta_analisis.get("modo") != "SICODE_IA":
                continue

            marca = Bitacora.query.filter_by(
                accion="CEREBRO_SICODE_APRENDIZAJE",
                entidad="SegmentoDocumental",
                entidad_id=str(segmento.id),
            ).first()
            if marca:
                continue

            datos = _dict_seguro(segmento.datos_confirmados)
            if not datos:
                omitidas += 1
                continue

            tipo = str(
                datos.get("tipo_documento_lote")
                or segmento.tipo_confirmado
                or segmento.tipo_detectado
                or "OTRO"
            ).strip().upper()

            # retroalimentar_segmento solo necesita estos metadatos. Se utiliza un
            # proxy sanitizado para que NEXO no modifique el segmento original ni
            # dependa de formas JSON históricas inesperadas.
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
                    "solo_metadatos": True,
                    "pdf_almacenado": False,
                },
                motivo="Retroalimentación de clasificación y extracción validada por usuario",
            ))

            # Confirmación por muestra: si una muestra posterior falla, las ya
            # aprendidas permanecen guardadas y no se repite su procesamiento.
            db.session.commit()
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
