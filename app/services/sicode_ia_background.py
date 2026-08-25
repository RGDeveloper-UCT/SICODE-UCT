import re
import shutil
from collections import Counter
from pathlib import Path

from rq import get_current_job

from app import create_app, db
from app.models.analisis_documental import AnalisisDocumental
from app.models.lote_documental import PatronAprendizajeDocumental, SegmentoDocumental
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente
from app.services.lote_documental_service import analizar_lote_temporal


def _orientacion_desde_contexto(contexto):
    texto = str(contexto or "").strip()
    resultado = {"contexto_usuario": texto[:1000]}
    m_anexo = re.search(r"\banexo\s*(?:n[úu]mero|no\.?|#)?\s*(\d+)\b", texto, re.IGNORECASE)
    if m_anexo:
        resultado["numero_anexo"] = m_anexo.group(1)
    candidatos_sp = re.findall(r"\b(?:sp\s*)?(\d{2,4})\b", texto, re.IGNORECASE)
    if candidatos_sp:
        resultado["no_sp"] = candidatos_sp[-1]
    return resultado


def _aplicar_orientacion(datos, orientacion):
    datos = dict(datos or {})
    if orientacion.get("no_sp"):
        _, normalizado = resolver_expediente(orientacion["no_sp"])
        datos["no_sp"] = normalizado or orientacion["no_sp"]
    if orientacion.get("numero_anexo"):
        datos["numero_anexo"] = orientacion["numero_anexo"]
    datos["contexto_usuario"] = orientacion.get("contexto_usuario")
    return datos


def _pesos_aprendidos():
    return {
        (p.tipo_documento, p.caracteristica): float(p.peso or 1.0)
        for p in PatronAprendizajeDocumental.query.all()
    }


def _crear_analisis(resultado, nombre_archivo, lote_token, orientacion, usuario_id):
    conteo = Counter(d["tipo"] for d in resultado["documentos"])
    analisis = AnalisisDocumental(
        usuario_id=usuario_id,
        tipo_objetivo="LOTE",
        tipo_detectado="LOTE_DOCUMENTAL",
        estado="PENDIENTE_VALIDACION",
        paginas_pdf=resultado["paginas_pdf"],
        paginas_ocr=resultado["paginas_ocr"],
        metodo_extraccion="SICODE_IA_ASYNC",
        datos_detectados={
            "modo": "SICODE_IA",
            "lote_token": lote_token,
            "archivo_origen": nombre_archivo,
            "contexto_usuario": orientacion.get("contexto_usuario"),
            "orientacion": orientacion,
            "documentos_total": resultado["documentos_total"],
            "tipos_detectados": dict(conteo),
            "procesamiento_fondo": True,
        },
        confianzas={},
        discrepancias=[],
        calidad_global=resultado["calidad_global"],
        pipeline_diagnostico={"etapas": resultado["pipeline"]},
        fuentes_campos={},
        explicaciones_campos={},
        ia_utilizada=resultado["ia_utilizada"],
        ia_modelo=resultado["ia_modelo"],
        duracion_ms=resultado["duracion_ms"],
    )
    db.session.add(analisis)
    db.session.flush()

    for orden, doc in enumerate(resultado["documentos"], start=1):
        datos = _aplicar_orientacion(doc["datos"], orientacion)
        expediente, normalizado = resolver_expediente(datos.get("no_sp"))
        if normalizado:
            datos["no_sp"] = normalizado
        db.session.add(SegmentoDocumental(
            analisis_id=analisis.id,
            expediente_id=expediente.id if expediente else None,
            orden=orden,
            pagina_inicio=doc["pagina_inicio"],
            pagina_fin=doc["pagina_fin"],
            tipo_detectado=doc["tipo"],
            estado="PENDIENTE_VALIDACION",
            calidad_global=doc["calidad_global"],
            datos_detectados=datos,
            confianzas=doc["confianzas"],
            fuentes_campos=doc["fuentes_campos"],
            discrepancias=doc["discrepancias"],
            caracteristicas_clasificacion=doc["caracteristicas"],
            ia_utilizada=doc["ia_utilizada"],
            ia_modelo=resultado["ia_modelo"] if doc["ia_utilizada"] else None,
        ))
    return analisis


def _progreso(fase, porcentaje, detalle=None, **extra):
    job = get_current_job()
    if not job:
        return
    job.meta.update({
        "fase": fase,
        "porcentaje": max(0, min(100, int(porcentaje))),
        "detalle": detalle or fase,
        **extra,
    })
    job.save_meta()


def procesar_lote_sicode_ia(rutas_archivos, nombres_archivos, contexto, lote_token, usuario_id):
    """Trabajo RQ. Procesa PDF fuera de Gunicorn y devuelve el token de revisión."""
    app = create_app()
    directorio_lote = Path(rutas_archivos[0]).parent if rutas_archivos else None
    try:
        with app.app_context():
            orientacion = _orientacion_desde_contexto(contexto)
            pesos = _pesos_aprendidos()
            creados = []
            fallidos = []
            total = max(1, len(rutas_archivos))
            _progreso("preparando", 2, "Preparando motor OCR e IA local", usuario_id=usuario_id, lote_token=lote_token)

            for indice, (ruta, nombre) in enumerate(zip(rutas_archivos, nombres_archivos), start=1):
                base = int(((indice - 1) / total) * 92)
                _progreso(
                    "analizando",
                    max(4, base),
                    f"Analizando {indice} de {total}: {nombre}",
                    archivo_actual=nombre,
                    archivo_indice=indice,
                    archivos_total=total,
                    usuario_id=usuario_id,
                    lote_token=lote_token,
                )
                try:
                    with open(ruta, "rb") as archivo:
                        resultado = analizar_lote_temporal(
                            archivo,
                            temp_dir=app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"),
                            max_mb=app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40),
                            max_paginas=app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200),
                            ocr_habilitado=app.config.get("DOCUMENT_ANALYSIS_OCR_ENABLED", True),
                            ocr_idioma=app.config.get("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa"),
                            limpieza_minutos=app.config.get("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", 30),
                            tesseract_cmd=app.config.get("DOCUMENT_ANALYSIS_TESSERACT_CMD"),
                            ocr_segunda_pasada=app.config.get("DOCUMENT_ANALYSIS_OCR_SECOND_PASS", False),
                            ia_habilitada=app.config.get("DOCUMENT_ANALYSIS_AI_ENABLED", True),
                            ollama_url=app.config.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                            ollama_model=app.config.get("DOCUMENT_ANALYSIS_AI_MODEL", app.config.get("OLLAMA_MODEL", "qwen3:1.7b")),
                            ollama_timeout=app.config.get("DOCUMENT_ANALYSIS_AI_TIMEOUT", 180),
                            pesos_aprendidos=pesos,
                        )
                    creados.append(_crear_analisis(resultado, nombre, lote_token, orientacion, usuario_id))
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    app.logger.exception("SICODE.IA background fallo en %s", nombre)
                    fallidos.append(f"{nombre}: {str(exc)[:180]}")

            if not creados:
                raise RuntimeError("No fue posible analizar ninguno de los PDF del lote.")

            registrar_bitacora(
                accion="SICODE_IA_ANALISIS_FONDO",
                modulo="Coordinación",
                descripcion=(
                    f"SICODE.IA finalizó en segundo plano {len(creados)} PDF; "
                    f"{len(fallidos)} archivo(s) presentaron incidencia."
                ),
                usuario_id=usuario_id,
                entidad="AnalisisDocumental",
                datos_posteriores={
                    "lote_token": lote_token,
                    "contexto": contexto,
                    "pdf_procesados": len(creados),
                    "fallidos": fallidos,
                    "procesamiento_fondo": True,
                },
                commit=False,
            )
            db.session.commit()
            _progreso(
                "terminado",
                100,
                "Análisis terminado. Listo para Verificación Humana.",
                usuario_id=usuario_id,
                lote_token=lote_token,
                fallidos=fallidos,
                revision_lista=True,
            )
            return {"lote_token": lote_token, "procesados": len(creados), "fallidos": fallidos}
    finally:
        if directorio_lote and directorio_lote.exists():
            shutil.rmtree(directorio_lote, ignore_errors=True)
