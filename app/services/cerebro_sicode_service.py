import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime

from app import db
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.lote_documental import AprendizajeDocumental, PatronAprendizajeDocumental, SegmentoDocumental
from app.services.analisis_documental_service import TIPOS_ANEXO, TIPOS_EVENTO
from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE


CAMPOS_SEGUROS_APRENDIZAJE = (
    "tipo_documento_lote",
    "no_sp",
    "rc",
    "providencia",
    "fecha_recepcion",
    "folios",
    "folio_inicio",
    "folio_fin",
    "numero_anexo",
    "titulo_anexo",
    "tipo_anexo",
    "boleta",
    "total",
    "numero_documento",
    "numero_reporte",
    "tipo_evento",
    "tipo_documento",
    "nombre_documento",
)


def _normalizar(valor):
    texto = str(valor or "").strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _mismo(a, b):
    return _normalizar(a) == _normalizar(b)


def _recalcular_nivel(perfil):
    muestras = max(0, int(perfil.muestras_confirmadas or 0))
    total_clas = max(1, int(perfil.clasificaciones_correctas or 0) + int(perfil.reclasificaciones or 0))
    total_campos = max(1, int(perfil.campos_confirmados or 0) + int(perfil.campos_corregidos or 0))
    precision_clas = int(perfil.clasificaciones_correctas or 0) / total_clas
    precision_campos = int(perfil.campos_confirmados or 0) / total_campos
    madurez = 1.0 - math.exp(-muestras / 28.0)
    fiabilidad = 0.55 * precision_clas + 0.45 * precision_campos
    perfil.nivel_aprendizaje = int(round(100 * madurez * (0.70 + 0.30 * fiabilidad)))


def retroalimentar_segmento(segmento, tipo_confirmado, datos_confirmados):
    """Aprende únicamente de metadatos validados por una persona.

    Nunca almacena OCR, imágenes, PDF ni datos personales extraídos del documento.
    """
    tipo_confirmado = str(tipo_confirmado or "OTRO").upper()
    perfil = AprendizajeDocumental.query.filter_by(tipo_documento=tipo_confirmado).first()
    if not perfil:
        perfil = AprendizajeDocumental(tipo_documento=tipo_confirmado)
        db.session.add(perfil)

    perfil.muestras_confirmadas = int(perfil.muestras_confirmadas or 0) + 1
    if str(segmento.tipo_detectado or "OTRO").upper() == tipo_confirmado:
        perfil.clasificaciones_correctas = int(perfil.clasificaciones_correctas or 0) + 1
    else:
        perfil.reclasificaciones = int(perfil.reclasificaciones or 0) + 1

    detectados = dict(segmento.datos_detectados or {})
    for campo in CAMPOS_SEGUROS_APRENDIZAJE:
        detectado = detectados.get(campo)
        confirmado = datos_confirmados.get(campo)
        if detectado in (None, "") and confirmado in (None, ""):
            continue
        if _mismo(detectado, confirmado):
            perfil.campos_confirmados = int(perfil.campos_confirmados or 0) + 1
        else:
            perfil.campos_corregidos = int(perfil.campos_corregidos or 0) + 1

    for caracteristica in list(segmento.caracteristicas_clasificacion or []):
        correcto = PatronAprendizajeDocumental.query.filter_by(
            tipo_documento=tipo_confirmado,
            caracteristica=caracteristica,
        ).first()
        if not correcto:
            correcto = PatronAprendizajeDocumental(tipo_documento=tipo_confirmado, caracteristica=caracteristica)
            db.session.add(correcto)
        correcto.aciertos = int(correcto.aciertos or 0) + 1
        correcto.peso = max(0.50, min(2.25, (correcto.aciertos + 1) / (correcto.errores + 1)))

        detectado_tipo = str(segmento.tipo_detectado or "OTRO").upper()
        if detectado_tipo != tipo_confirmado:
            errado = PatronAprendizajeDocumental.query.filter_by(
                tipo_documento=detectado_tipo,
                caracteristica=caracteristica,
            ).first()
            if not errado:
                errado = PatronAprendizajeDocumental(tipo_documento=detectado_tipo, caracteristica=caracteristica)
                db.session.add(errado)
            errado.errores = int(errado.errores or 0) + 1
            errado.peso = max(0.50, min(2.25, (errado.aciertos + 1) / (errado.errores + 1)))

    _recalcular_nivel(perfil)


def _nuevo_hallazgo(categoria, titulo, detalle, recomendacion, prioridad="media", evidencia=None):
    base = f"{categoria}|{titulo}|{detalle}|{recomendacion}"
    firma = hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    return {
        "firma": firma,
        "categoria": categoria,
        "titulo": titulo,
        "detalle": detalle,
        "recomendacion": recomendacion,
        "prioridad": prioridad,
        "evidencia": evidencia or {},
    }


def _variantes_catalogo(valores, etiqueta):
    grupos = defaultdict(Counter)
    for valor in valores:
        if valor:
            grupos[_normalizar(valor)][str(valor).strip()] += 1
    hallazgos = []
    for normal, variantes in grupos.items():
        if normal and len(variantes) > 1:
            top = variantes.most_common(5)
            nombres = ", ".join(v for v, _ in top)
            hallazgos.append(_nuevo_hallazgo(
                "nomenclatura",
                f"Variantes de nombre en {etiqueta}",
                f"SICODE encontró varias formas para el mismo concepto: {nombres}.",
                "Definir un nombre canónico y convertir este campo en catálogo/autocompletado para evitar nuevas variantes.",
                "media",
                {"normalizado": normal, "variantes": dict(top)},
            ))
    return hallazgos


def _resumen_aprendizaje():
    perfiles = AprendizajeDocumental.query.all()
    muestras = sum(int(p.muestras_confirmadas or 0) for p in perfiles)
    correctas = sum(int(p.clasificaciones_correctas or 0) for p in perfiles)
    reclas = sum(int(p.reclasificaciones or 0) for p in perfiles)
    if muestras:
        nivel = int(round(sum((p.nivel_aprendizaje or 0) * (p.muestras_confirmadas or 0) for p in perfiles) / muestras))
        precision = int(round(correctas / max(correctas + reclas, 1) * 100))
    else:
        nivel = precision = 0
    return {
        "nivel": max(0, min(100, nivel)),
        "muestras": muestras,
        "precision": max(0, min(100, precision)),
        "tipos_aprendidos": sum(1 for p in perfiles if int(p.muestras_confirmadas or 0) > 0),
    }


def analizar_sicode():
    """Inspecciona metadatos y retroalimentación de todo SICODE.

    El objetivo es detectar necesidades de desarrollo, no tomar decisiones operativas
    ni modificar registros de expedientes de manera automática.
    """
    hallazgos = []
    aprendizaje = _resumen_aprendizaje()

    segmentos = (
        SegmentoDocumental.query
        .filter(SegmentoDocumental.datos_confirmados.isnot(None))
        .order_by(SegmentoDocumental.id.desc())
        .limit(500)
        .all()
    )
    correcciones = Counter()
    reclasificaciones = 0
    otros = 0
    for seg in segmentos:
        detectados = dict(seg.datos_detectados or {})
        confirmados = dict(seg.datos_confirmados or {})
        tipo_d = str(seg.tipo_detectado or detectados.get("tipo_documento_lote") or "OTRO").upper()
        tipo_c = str(seg.tipo_confirmado or confirmados.get("tipo_documento_lote") or tipo_d).upper()
        if tipo_d != tipo_c:
            reclasificaciones += 1
        if tipo_c == "OTRO":
            otros += 1
        for campo in CAMPOS_SEGUROS_APRENDIZAJE:
            a, b = detectados.get(campo), confirmados.get(campo)
            if (a not in (None, "") or b not in (None, "")) and not _mismo(a, b):
                correcciones[campo] += 1

    if len(segmentos) >= 8:
        tasa = reclasificaciones / len(segmentos)
        if tasa >= 0.15:
            hallazgos.append(_nuevo_hallazgo(
                "clasificacion",
                "Reclasificación humana frecuente",
                f"{reclasificaciones} de {len(segmentos)} documentos recientes cambiaron de categoría durante la revisión humana ({tasa:.0%}).",
                "Revisar palabras clave, ejemplos de entrenamiento y reglas de separación para los tipos con más correcciones.",
                "alta" if tasa >= 0.30 else "media",
                {"reclasificados": reclasificaciones, "muestras": len(segmentos)},
            ))
        if otros >= 3 and otros / len(segmentos) >= 0.05:
            hallazgos.append(_nuevo_hallazgo(
                "catalogo",
                "Documentos confirmados como OTRO",
                f"Hay {otros} documentos confirmados como OTRO en la muestra reciente.",
                "Revisar sus nombres administrativos confirmados para decidir si corresponde crear una nueva categoría documental.",
                "media",
                {"otros": otros, "muestras": len(segmentos)},
            ))

    for campo, cantidad in correcciones.most_common(6):
        if cantidad >= 3:
            hallazgos.append(_nuevo_hallazgo(
                "extraccion",
                f"Campo corregido repetidamente: {campo.replace('_', ' ')}",
                f"La verificación humana corrigió este campo {cantidad} veces en los análisis recientes.",
                "Agregar o ajustar reglas de extracción para este campo y usar las confirmaciones humanas como referencia segura.",
                "media",
                {"campo": campo, "correcciones": cantidad},
            ))

    eventos = [v for (v,) in db.session.query(ReporteMonitoreo.tipo_evento).filter(ReporteMonitoreo.tipo_evento.isnot(None)).all()]
    tipos_evento_conocidos = {_normalizar(v) for v in TIPOS_EVENTO}
    nuevos_eventos = Counter(v for v in eventos if _normalizar(v) not in tipos_evento_conocidos)
    if nuevos_eventos:
        top = nuevos_eventos.most_common(8)
        hallazgos.append(_nuevo_hallazgo(
            "catalogo",
            "Nuevos nombres de evento/reporte",
            "SICODE contiene nombres de evento que no están en el catálogo documental conocido: " + ", ".join(v for v, _ in top) + ".",
            "Revisar estos nombres y, si son oficiales, incorporarlos al catálogo de monitoreo y a las reglas de SICODE.IA.",
            "alta" if sum(nuevos_eventos.values()) >= 10 else "media",
            {"valores": dict(top)},
        ))
    hallazgos.extend(_variantes_catalogo(eventos, "eventos de monitoreo"))

    anexos = [v for (v,) in db.session.query(AnexoCoordinacion.tipo_anexo).filter(AnexoCoordinacion.tipo_anexo.isnot(None)).all()]
    tipos_anexo_conocidos = {_normalizar(v) for v in TIPOS_ANEXO}
    anexos_nuevos = Counter(v for v in anexos if _normalizar(v) not in tipos_anexo_conocidos)
    if anexos_nuevos:
        top = anexos_nuevos.most_common(8)
        hallazgos.append(_nuevo_hallazgo(
            "catalogo",
            "Tipos de anexo fuera del catálogo",
            "Se detectaron tipos de anexo usados en SICODE que no están en el catálogo actual: " + ", ".join(v for v, _ in top) + ".",
            "Validar cuáles son categorías institucionales nuevas y actualizar catálogo, formularios y clasificación documental.",
            "media",
            {"valores": dict(top)},
        ))
    hallazgos.extend(_variantes_catalogo(anexos, "tipos de anexo"))

    tipos_doc = [v for (v,) in db.session.query(DocumentoExpediente.tipo_documento).filter(DocumentoExpediente.tipo_documento.isnot(None)).all()]
    conocidos_doc = {_normalizar(v) for v in TIPOS_DOCUMENTO_LOTE}
    doc_nuevos = Counter(v for v in tipos_doc if _normalizar(v) not in conocidos_doc)
    if doc_nuevos:
        top = doc_nuevos.most_common(10)
        hallazgos.append(_nuevo_hallazgo(
            "catalogo",
            "Tipos documentales no reconocidos por SICODE.IA",
            "El índice documental contiene tipos que todavía no forman parte del clasificador principal: " + ", ".join(v for v, _ in top) + ".",
            "Revisar frecuencia y utilidad; promover a categoría los tipos recurrentes y añadir sus señales de reconocimiento.",
            "alta" if sum(doc_nuevos.values()) >= 15 else "media",
            {"valores": dict(top)},
        ))
    hallazgos.extend(_variantes_catalogo(tipos_doc, "tipos documentales"))

    registros_tipo = [v for (v,) in db.session.query(RegistroCoordinacion.tipo).filter(RegistroCoordinacion.tipo.isnot(None)).all()]
    hallazgos.extend(_variantes_catalogo(registros_tipo, "registros de Coordinación"))

    hallazgos = hallazgos[:16]
    prioridad_peso = {"alta": 3, "media": 2, "baja": 1}
    hallazgos.sort(key=lambda h: (-prioridad_peso.get(h["prioridad"], 0), h["categoria"], h["titulo"]))

    totales = {
        "expedientes": Expediente.query.count(),
        "documentos_indice": DocumentoExpediente.query.filter_by(activo=True).count(),
        "registros_coordinacion": RegistroCoordinacion.query.count(),
        "muestras_ia": SegmentoDocumental.query.count(),
    }
    totales["objetos_estudiados"] = sum(totales.values())

    return {
        "aprendizaje": aprendizaje,
        "totales": totales,
        "hallazgos": hallazgos,
        "hallazgos_total": len(hallazgos),
        "estado": "requiere_revision" if any(h["prioridad"] == "alta" for h in hallazgos) else ("observando" if hallazgos else "estable"),
        "analizado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def guardar_hallazgos(resultado, usuario_id=None):
    """Persiste hallazgos de desarrollo en Bitácora sin duplicar firmas existentes."""
    nuevos = 0
    for hallazgo in resultado.get("hallazgos", []):
        firma = hallazgo["firma"]
        existe = Bitacora.query.filter_by(
            accion="CEREBRO_SICODE_HALLAZGO",
            entidad="CerebroSicode",
            entidad_id=firma,
        ).first()
        if existe:
            continue
        db.session.add(Bitacora(
            usuario_id=usuario_id,
            accion="CEREBRO_SICODE_HALLAZGO",
            modulo="SICODE.IA",
            descripcion=f"{hallazgo['titulo']}: {hallazgo['detalle']}",
            entidad="CerebroSicode",
            entidad_id=firma,
            datos_posteriores={
                "categoria": hallazgo["categoria"],
                "prioridad": hallazgo["prioridad"],
                "recomendacion": hallazgo["recomendacion"],
                "evidencia": hallazgo.get("evidencia") or {},
            },
            motivo="Analizador interno de mejora continua de SICODE.IA",
        ))
        nuevos += 1
    if nuevos:
        db.session.commit()
    return nuevos
