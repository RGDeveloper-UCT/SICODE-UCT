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


def absorber_verificaciones_pendientes(usuario_id=None, max_examinadas=1000, lote=100):
    """Aprende pendientes por clave creciente, con cursor de continuación persistente.

    Antes se inspeccionaban siempre los primeros 1.000 documentos ya aprendidos.
    El cursor evita que muestras malformadas antiguas impidan aprender las nuevas.
    El estado se conserva en bitácora sin almacenar texto OCR ni datos personales.
    """
    from sqlalchemy import cast
    from app.models.analisis_documental import AnalisisDocumental

    max_examinadas = max(1, min(int(max_examinadas), 5000))
    lote = max(1, min(int(lote), 200))
    anterior = (Bitacora.query.filter_by(
        accion="NEXO_APRENDIZAJE_CURSOR", entidad="CerebroSicode"
    ).order_by(Bitacora.id.desc()).first())
    cursor = int((anterior.datos_posteriores or {}).get("cursor", 0)) if anterior else 0
    aprendidas = omitidas = examinadas = 0
    ultimo_id = cursor

    # La búsqueda descarta registros ya incorporados al perfil de aprendizaje.
    # Dejar el filtro por modo SICODE_IA en SQL evita gastar el cupo en lotes ajenos.
    procesado = db.session.query(Bitacora.id).filter(
        Bitacora.accion == "CEREBRO_SICODE_APRENDIZAJE",
        Bitacora.entidad == "SegmentoDocumental",
        Bitacora.entidad_id == cast(SegmentoDocumental.id, db.String),
    ).exists()
    base = (
        SegmentoDocumental.query.join(AnalisisDocumental, SegmentoDocumental.analisis_id == AnalisisDocumental.id)
        .filter(SegmentoDocumental.estado.in_(["VERIFICADO_HUMANO", "CONFIRMADO"]))
        .filter(SegmentoDocumental.datos_confirmados.isnot(None))
        .filter(AnalisisDocumental.datos_detectados["modo"].as_string() == "SICODE_IA")
        .filter(~procesado)
    )

    while examinadas < max_examinadas:
        segmentos = (
            base.filter(SegmentoDocumental.id > ultimo_id)
            .order_by(SegmentoDocumental.id.asc())
            .limit(min(lote, max_examinadas - examinadas))
            .all()
        )
        if not segmentos:
            # Al alcanzar el final se reinicia el cursor; así los históricos
            # inválidos también podrán reintentarse sin bloquear al resto.
            ultimo_id = 0
            break
        for segmento in segmentos:
            ultimo_id = segmento.id
            examinadas += 1
            try:
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
                    descripcion=f"Aprendizaje agregado de la verificación {segmento.id}.",
                    entidad="SegmentoDocumental",
                    entidad_id=str(segmento.id),
                    datos_posteriores={
                        "tipo_detectado": segmento.tipo_detectado,
                        "tipo_confirmado": tipo,
                        "solo_metadatos": True,
                        "pdf_almacenado": False,
                    },
                    motivo="Retroalimentación humana validada",
                ))
                db.session.commit()
                aprendidas += 1
            except Exception as exc:  # pragma: no cover - datos históricos
                db.session.rollback()
                omitidas += 1
                current_app.logger.exception(
                    "NEXO omitió la muestra %s durante aprendizaje (%s)",
                    segmento.id, exc.__class__.__name__,
                )
    if examinadas:
        db.session.add(Bitacora(
            usuario_id=usuario_id,
            accion="NEXO_APRENDIZAJE_CURSOR", modulo="NEXO",
            entidad="CerebroSicode",
            descripcion="Punto de continuación de aprendizaje documental.",
            datos_posteriores={
                "cursor": ultimo_id, "examinadas": examinadas,
                "aprendidas": aprendidas, "omitidas": omitidas,
            },
            motivo="Control automático de lotes de aprendizaje",
        ))
        db.session.commit()
    if omitidas:
        current_app.logger.warning(
            "NEXO: %s muestra(s) omitida(s), %s incorporada(s), %s inspeccionada(s)",
            omitidas, aprendidas, examinadas,
        )
    return aprendidas
