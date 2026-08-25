from collections import Counter

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.analisis_documental import AnalisisDocumental
from app.models.lote_documental import PatronAprendizajeDocumental, SegmentoDocumental
from app.services.analisis_documental_service import DocumentoInvalido, OCRNoDisponible
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente
from app.services.lote_documental_service import analizar_lote_temporal


importacion_documental_bp = Blueprint(
    "importacion_documental",
    __name__,
    url_prefix="/coordinacion/importacion-documental",
)

MAX_ARCHIVOS = 100


def _exigir_modificacion():
    if not current_user.puede_modificar:
        abort(403)


def _pesos_aprendidos():
    return {
        (item.tipo_documento, item.caracteristica): float(item.peso or 1.0)
        for item in PatronAprendizajeDocumental.query.all()
    }


def _tamano_archivo(archivo):
    pos = archivo.stream.tell()
    archivo.stream.seek(0, 2)
    tamano = archivo.stream.tell()
    archivo.stream.seek(pos)
    return tamano


def _crear_analisis_desde_resultado(resultado, nombre_archivo):
    conteo_tipos = Counter(doc["tipo"] for doc in resultado["documentos"])
    analisis = AnalisisDocumental(
        usuario_id=current_user.id,
        tipo_objetivo="LOTE",
        tipo_detectado="LOTE_DOCUMENTAL",
        estado="PENDIENTE_VALIDACION",
        paginas_pdf=resultado["paginas_pdf"],
        paginas_ocr=resultado["paginas_ocr"],
        metodo_extraccion="LOTE_OCR_IA" if resultado["ia_utilizada"] else "LOTE_OCR_REGLAS",
        datos_detectados={
            "modo": "IMPORTACION_MULTIPDF",
            "archivo_origen": nombre_archivo,
            "documentos_total": resultado["documentos_total"],
            "tipos_detectados": dict(conteo_tipos),
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
        datos = dict(doc["datos"])
        expediente, sp_normalizado = resolver_expediente(datos.get("no_sp"))
        if sp_normalizado:
            datos["no_sp"] = sp_normalizado
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


@importacion_documental_bp.route("/", methods=["GET"])
@login_required
def inicio():
    _exigir_modificacion()
    return render_template(
        "importacion_documental/inicio.html",
        max_archivos=MAX_ARCHIVOS,
        max_mb=current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40),
        max_paginas=current_app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200),
    )


@importacion_documental_bp.route("/analizar", methods=["POST"])
@login_required
def analizar():
    _exigir_modificacion()
    archivos = [a for a in request.files.getlist("archivos_pdf") if a and a.filename]
    if not archivos:
        flash("Seleccione uno o varios archivos PDF.", "danger")
        return redirect(url_for("importacion_documental.inicio"))
    if len(archivos) > MAX_ARCHIVOS:
        flash(f"Puede seleccionar como máximo {MAX_ARCHIVOS} PDF por importación.", "danger")
        return redirect(url_for("importacion_documental.inicio"))
    if any(not a.filename.lower().endswith(".pdf") for a in archivos):
        flash("Todos los archivos deben ser PDF.", "danger")
        return redirect(url_for("importacion_documental.inicio"))

    max_mb = current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40)
    total_bytes = sum(_tamano_archivo(a) for a in archivos)
    if total_bytes > max_mb * 1024 * 1024:
        flash(
            f"La selección pesa {total_bytes / 1024 / 1024:.1f} MB. El límite técnico actual por importación es {max_mb} MB.",
            "danger",
        )
        return redirect(url_for("importacion_documental.inicio"))

    analisis_creados = []
    fallidos = []
    paginas_total = 0
    documentos_total = 0
    pesos = _pesos_aprendidos()

    for archivo in archivos:
        try:
            resultado = analizar_lote_temporal(
                archivo,
                temp_dir=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"),
                max_mb=max_mb,
                max_paginas=current_app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200),
                ocr_habilitado=current_app.config.get("DOCUMENT_ANALYSIS_OCR_ENABLED", True),
                ocr_idioma=current_app.config.get("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa"),
                limpieza_minutos=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", 30),
                tesseract_cmd=current_app.config.get("DOCUMENT_ANALYSIS_TESSERACT_CMD"),
                ocr_segunda_pasada=current_app.config.get("DOCUMENT_ANALYSIS_OCR_SECOND_PASS", False),
                ia_habilitada=current_app.config.get("DOCUMENT_ANALYSIS_AI_ENABLED", True),
                ollama_url=current_app.config.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                ollama_model=current_app.config.get("DOCUMENT_ANALYSIS_AI_MODEL", current_app.config.get("OLLAMA_MODEL", "qwen3:1.7b")),
                ollama_timeout=current_app.config.get("DOCUMENT_ANALYSIS_AI_TIMEOUT", 75),
                pesos_aprendidos=pesos,
            )
            analisis = _crear_analisis_desde_resultado(resultado, archivo.filename)
            analisis_creados.append(analisis)
            paginas_total += int(resultado.get("paginas_pdf") or 0)
            documentos_total += int(resultado.get("documentos_total") or 0)
        except (DocumentoInvalido, OCRNoDisponible, RuntimeError) as exc:
            current_app.logger.warning("Importación documental rechazada (%s): %s", archivo.filename, exc)
            fallidos.append({"archivo": archivo.filename, "error": str(exc)})
        except Exception:
            current_app.logger.exception("Fallo inesperado procesando %s", archivo.filename)
            fallidos.append({"archivo": archivo.filename, "error": "No fue posible analizar este archivo."})

    if not analisis_creados:
        db.session.rollback()
        flash("No fue posible analizar ninguno de los PDF seleccionados.", "danger")
        return render_template(
            "importacion_documental/resumen.html",
            analisis=[], fallidos=fallidos, paginas_total=0, documentos_total=0,
        )

    registrar_bitacora(
        accion="IMPORTAR_DOCUMENTACION_MULTIPDF",
        modulo="Coordinación",
        descripcion=(
            f"Importación documental: {len(analisis_creados)} PDF procesados, {paginas_total} páginas y "
            f"{documentos_total} piezas propuestas para rectificación humana. Los PDF temporales fueron eliminados."
        ),
        usuario_id=current_user.id,
        entidad="AnalisisDocumental",
        datos_posteriores={
            "pdf_procesados": len(analisis_creados),
            "pdf_fallidos": len(fallidos),
            "paginas": paginas_total,
            "documentos": documentos_total,
            "archivo_temporal_eliminado": True,
        },
        commit=False,
    )
    db.session.commit()

    return render_template(
        "importacion_documental/resumen.html",
        analisis=analisis_creados,
        fallidos=fallidos,
        paginas_total=paginas_total,
        documentos_total=documentos_total,
    )
