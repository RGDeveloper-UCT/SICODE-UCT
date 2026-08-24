import math
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.analisis_documental import AnalisisDocumental
from app.models.coordinacion import (
    AnexoCoordinacion,
    MovimientoDispositivo,
    PagoCoordinacion,
    RegistroCoordinacion,
    ReporteMonitoreo,
)
from app.models.documento_expediente import DocumentoExpediente
from app.models.lote_documental import (
    AprendizajeDocumental,
    PatronAprendizajeDocumental,
    SegmentoDocumental,
)
from app.services.analisis_documental_service import DocumentoInvalido, OCRNoDisponible, TIPOS_ANEXO, TIPOS_EVENTO
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import determinar_estado, resolver_expediente
from app.services.lote_documental_service import (
    TIPOS_DOCUMENTO_LOTE,
    TIPOS_OPERATIVOS,
    analizar_lote_temporal,
)


lote_documental_bp = Blueprint(
    "lote_documental",
    __name__,
    url_prefix="/coordinacion/analisis-documental/lotes",
)

CAMPOS_RETROALIMENTACION = (
    "no_sp", "rc", "providencia", "fecha_recepcion", "folios", "folio_inicio", "folio_fin",
    "numero_anexo", "titulo_anexo", "tipo_anexo", "boleta", "total", "numero_documento",
)


def _exigir_modificacion():
    if not current_user.puede_modificar:
        abort(403)


def _limpiar(valor, maximo=None):
    texto = str(valor or "").strip()
    if not texto:
        return None
    return texto[:maximo] if maximo else texto


def _entero(valor):
    texto = _limpiar(valor)
    if texto is None:
        return None
    return int(texto)


def _fecha(valor):
    texto = _limpiar(valor)
    return date.fromisoformat(texto) if texto else None


def _lote_visible(analisis_id):
    analisis = AnalisisDocumental.query.get_or_404(analisis_id)
    if current_user.rol != "administrador" and analisis.usuario_id != current_user.id:
        abort(403)
    if not analisis.segmentos:
        abort(404)
    return analisis


def _segmento_visible(analisis, segmento_id):
    segmento = SegmentoDocumental.query.filter_by(id=segmento_id, analisis_id=analisis.id).first_or_404()
    return segmento


def _pesos_aprendidos():
    return {
        (item.tipo_documento, item.caracteristica): float(item.peso or 1.0)
        for item in PatronAprendizajeDocumental.query.all()
    }


def _resumen_aprendizaje():
    perfiles = AprendizajeDocumental.query.order_by(AprendizajeDocumental.muestras_confirmadas.desc()).all()
    total_muestras = sum(int(p.muestras_confirmadas or 0) for p in perfiles)
    if total_muestras:
        nivel = int(round(sum((p.nivel_aprendizaje or 0) * p.muestras_confirmadas for p in perfiles) / total_muestras))
        aciertos = sum(int(p.clasificaciones_correctas or 0) for p in perfiles)
        precision = int(round(aciertos / total_muestras * 100))
    else:
        nivel = precision = 0
    return {
        "nivel": max(0, min(100, nivel)),
        "muestras": total_muestras,
        "precision_clasificacion": max(0, min(100, precision)),
        "tipos_aprendidos": sum(1 for p in perfiles if p.muestras_confirmadas),
        "perfiles": perfiles[:8],
    }


def _recalcular_nivel(perfil):
    muestras = max(0, int(perfil.muestras_confirmadas or 0))
    total_clas = max(1, int(perfil.clasificaciones_correctas or 0) + int(perfil.reclasificaciones or 0))
    total_campos = max(1, int(perfil.campos_confirmados or 0) + int(perfil.campos_corregidos or 0))
    precision_clas = int(perfil.clasificaciones_correctas or 0) / total_clas
    precision_campos = int(perfil.campos_confirmados or 0) / total_campos
    madurez = 1.0 - math.exp(-muestras / 28.0)
    fiabilidad = 0.55 * precision_clas + 0.45 * precision_campos
    perfil.nivel_aprendizaje = int(round(100 * madurez * (0.70 + 0.30 * fiabilidad)))


def _actualizar_aprendizaje(segmento, tipo_confirmado, datos_confirmados):
    tipo_confirmado = str(tipo_confirmado or "OTRO").upper()
    perfil = AprendizajeDocumental.query.filter_by(tipo_documento=tipo_confirmado).first()
    if not perfil:
        perfil = AprendizajeDocumental(tipo_documento=tipo_confirmado)
        db.session.add(perfil)

    perfil.muestras_confirmadas = int(perfil.muestras_confirmadas or 0) + 1
    if segmento.tipo_detectado == tipo_confirmado:
        perfil.clasificaciones_correctas = int(perfil.clasificaciones_correctas or 0) + 1
    else:
        perfil.reclasificaciones = int(perfil.reclasificaciones or 0) + 1

    detectados = dict(segmento.datos_detectados or {})
    for campo in CAMPOS_RETROALIMENTACION:
        confirmado = datos_confirmados.get(campo)
        detectado = detectados.get(campo)
        if confirmado in (None, "") and detectado in (None, ""):
            continue
        if str(confirmado or "").strip().upper() == str(detectado or "").strip().upper():
            perfil.campos_confirmados = int(perfil.campos_confirmados or 0) + 1
        else:
            perfil.campos_corregidos = int(perfil.campos_corregidos or 0) + 1

    caracteristicas = list(segmento.caracteristicas_clasificacion or [])
    for caracteristica in caracteristicas:
        patron_correcto = PatronAprendizajeDocumental.query.filter_by(
            tipo_documento=tipo_confirmado,
            caracteristica=caracteristica,
        ).first()
        if not patron_correcto:
            patron_correcto = PatronAprendizajeDocumental(
                tipo_documento=tipo_confirmado,
                caracteristica=caracteristica,
            )
            db.session.add(patron_correcto)
        patron_correcto.aciertos = int(patron_correcto.aciertos or 0) + 1
        patron_correcto.peso = max(0.50, min(2.25, (patron_correcto.aciertos + 1) / (patron_correcto.errores + 1)))

        if segmento.tipo_detectado != tipo_confirmado:
            patron_errado = PatronAprendizajeDocumental.query.filter_by(
                tipo_documento=segmento.tipo_detectado,
                caracteristica=caracteristica,
            ).first()
            if not patron_errado:
                patron_errado = PatronAprendizajeDocumental(
                    tipo_documento=segmento.tipo_detectado,
                    caracteristica=caracteristica,
                )
                db.session.add(patron_errado)
            patron_errado.errores = int(patron_errado.errores or 0) + 1
            patron_errado.peso = max(0.50, min(2.25, (patron_errado.aciertos + 1) / (patron_errado.errores + 1)))

    _recalcular_nivel(perfil)


def _actualizar_estado_lote(analisis):
    estados = [seg.estado for seg in analisis.segmentos]
    if estados and all(e in {"CONFIRMADO", "DESCARTADO"} for e in estados):
        analisis.estado = "CONFIRMADO" if any(e == "CONFIRMADO" for e in estados) else "DESCARTADO"
        if analisis.estado == "CONFIRMADO":
            analisis.confirmado_en = datetime.utcnow()
    elif any(e == "CONFIRMADO" for e in estados):
        analisis.estado = "VALIDACION_PARCIAL"
    else:
        analisis.estado = "PENDIENTE_VALIDACION"


def _datos_formulario(segmento):
    datos = dict(segmento.datos_detectados or {})
    claves = (
        "tipo_documento_lote", "no_sp", "rc", "providencia", "fecha_recepcion", "folios",
        "folio_inicio", "folio_fin", "numero_anexo", "titulo_anexo", "tipo_anexo", "boleta", "total",
        "periodo_texto", "numero_reporte", "tipo_evento", "tipo_documento", "descripcion", "numero_documento",
        "nombre_documento", "observaciones",
    )
    for clave in claves:
        if clave in request.form:
            datos[clave] = request.form.get(clave, "")
    return datos


def _resolver_sp(no_sp):
    expediente, normalizado = resolver_expediente(no_sp)
    return expediente, normalizado


def _crear_indice(expediente, tipo, datos, inicio, fin):
    if not expediente or inicio is None or fin is None:
        return None, "No se agregó al índice documental porque falta SP o rango de folios confirmado."
    solapado = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=True)
        .filter(DocumentoExpediente.folio_inicio <= fin, DocumentoExpediente.folio_fin >= inicio)
        .first()
    )
    if solapado:
        return None, f"El rango {inicio}-{fin} se cruza con {solapado.nombre_documento}; no se agregó automáticamente al índice."

    if tipo == "ANEXO":
        numero = _limpiar(datos.get("numero_anexo"), 50)
        titulo = _limpiar(datos.get("titulo_anexo"), 180) or "Anexo"
        nombre = f"Anexo {numero} - {titulo}" if numero else titulo
    elif tipo == "DPI":
        nombre = "DPI identificado (datos personales no almacenados)"
    else:
        nombre = _limpiar(datos.get("nombre_documento"), 180)
        if not nombre:
            numero = _limpiar(datos.get("numero_documento"), 100)
            nombre = f"{tipo} {numero}" if numero else tipo.title()

    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=nombre[:180],
        tipo_documento=tipo.title()[:80],
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision="Pendiente de revisión",
        es_anexo=(tipo == "ANEXO"),
        observaciones="Clasificado desde lote documental; PDF temporal eliminado tras el análisis.",
        activo=True,
    )
    db.session.add(documento)
    db.session.flush()
    return documento, None


def _crear_operativo(tipo, expediente, no_sp, datos, fecha_recepcion, total, documento_indice=None):
    campos_clave = [no_sp, fecha_recepcion]
    if tipo == "ANEXO":
        campos_clave += [datos.get("rc"), datos.get("providencia"), datos.get("tipo_anexo")]
    elif tipo in {"INSTALACION", "DESINSTALACION"}:
        campos_clave += [datos.get("rc"), datos.get("providencia")]
    elif tipo == "PAGO":
        campos_clave += [datos.get("providencia"), datos.get("boleta"), datos.get("total")]
    elif tipo == "MONITOREO":
        campos_clave += [datos.get("rc"), datos.get("providencia"), datos.get("numero_reporte"), datos.get("tipo_evento")]

    registro = RegistroCoordinacion(
        tipo=tipo,
        expediente_id=expediente.id if expediente else None,
        no_sp_referencia=no_sp,
        rc=_limpiar(datos.get("rc"), 80),
        providencia=_limpiar(datos.get("providencia"), 120),
        fecha_recepcion=fecha_recepcion,
        persona_entrega=None,
        folios_recepcion=_limpiar(datos.get("folios"), 80),
        usuario_id=current_user.id,
        usuario_origen=current_user.nombre,
        estado=determinar_estado(expediente, no_sp, campos_clave=campos_clave),
        observaciones=_limpiar(datos.get("observaciones")),
        origen_registro="ANALISIS_LOTE_PDF",
    )
    db.session.add(registro)
    db.session.flush()

    if tipo == "ANEXO":
        db.session.add(AnexoCoordinacion(
            registro_id=registro.id,
            documento_expediente_id=documento_indice.id if documento_indice else None,
            tipo_anexo=_limpiar(datos.get("tipo_anexo"), 120),
            titulo=_limpiar(datos.get("titulo_anexo"), 180),
            folios=_limpiar(datos.get("folios"), 80),
            escaneado=True,
            fecha_escaneado=date.today(),
            numero_anexo=_limpiar(datos.get("numero_anexo"), 50),
        ))
    elif tipo in {"INSTALACION", "DESINSTALACION"}:
        db.session.add(MovimientoDispositivo(
            registro_id=registro.id,
            movimiento=tipo,
            descripcion=_limpiar(datos.get("descripcion"), 180) or "EXPEDIENTE",
            folios=_limpiar(datos.get("folios"), 80),
        ))
    elif tipo == "PAGO":
        db.session.add(PagoCoordinacion(
            registro_id=registro.id,
            folios=_limpiar(datos.get("folios"), 80),
            periodo_texto=_limpiar(datos.get("periodo_texto"), 120),
            boleta=_limpiar(datos.get("boleta"), 120),
            total=total,
        ))
    elif tipo == "MONITOREO":
        db.session.add(ReporteMonitoreo(
            registro_id=registro.id,
            tipo_documento=_limpiar(datos.get("tipo_documento"), 80) or "PROVIDENCIA",
            numero_reporte=_limpiar(datos.get("numero_reporte"), 120),
            tipo_evento=_limpiar(datos.get("tipo_evento"), 180),
        ))
    return registro


@lote_documental_bp.route("/analizar", methods=["POST"])
@login_required
def analizar():
    _exigir_modificacion()
    archivo = request.files.get("archivo_pdf")
    if not archivo or not archivo.filename:
        flash("Seleccione un PDF para analizar como lote documental.", "danger")
        return redirect(url_for("analisis_documental.inicio"))
    if not archivo.filename.lower().endswith(".pdf"):
        flash("Solo se permiten archivos PDF.", "danger")
        return redirect(url_for("analisis_documental.inicio"))

    try:
        resultado = analizar_lote_temporal(
            archivo,
            temp_dir=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"),
            max_mb=current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40),
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
            pesos_aprendidos=_pesos_aprendidos(),
        )
    except (DocumentoInvalido, OCRNoDisponible, RuntimeError) as exc:
        current_app.logger.warning("Lote documental rechazado: %s", exc)
        flash(str(exc), "danger")
        return redirect(url_for("analisis_documental.inicio"))
    except Exception:
        current_app.logger.exception("Fallo inesperado durante separación de lote documental")
        flash("No fue posible separar el lote. El PDF temporal fue descartado.", "danger")
        return redirect(url_for("analisis_documental.inicio"))

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
            "modo": "LOTE",
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
        expediente, sp_normalizado = _resolver_sp(datos.get("no_sp"))
        if sp_normalizado:
            datos["no_sp"] = sp_normalizado
        segmento = SegmentoDocumental(
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
        )
        db.session.add(segmento)

    registrar_bitacora(
        accion="SEPARAR_LOTE_DOCUMENTAL",
        modulo="Coordinación",
        descripcion=(
            f"Lote documental No. {analisis.id}: {resultado['paginas_pdf']} página(s), "
            f"{resultado['documentos_total']} documento(s) detectados. PDF y OCR temporal eliminados."
        ),
        usuario_id=current_user.id,
        entidad="AnalisisDocumental",
        entidad_id=analisis.id,
        datos_posteriores={
            "documentos_detectados": resultado["documentos_total"],
            "paginas": resultado["paginas_pdf"],
            "tipos": dict(conteo_tipos),
            "ia_utilizada": resultado["ia_utilizada"],
            "archivo_temporal_eliminado": True,
        },
        commit=False,
    )
    db.session.commit()
    return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id))


@lote_documental_bp.route("/<int:analisis_id>")
@login_required
def resultado(analisis_id):
    _exigir_modificacion()
    analisis = _lote_visible(analisis_id)
    return render_template(
        "analisis_documental/lote_resultado.html",
        analisis=analisis,
        segmentos=analisis.segmentos,
        tipos_documento=TIPOS_DOCUMENTO_LOTE,
        tipos_anexo=TIPOS_ANEXO,
        tipos_evento=TIPOS_EVENTO,
        aprendizaje=_resumen_aprendizaje(),
    )


@lote_documental_bp.route("/<int:analisis_id>/segmentos/<int:segmento_id>/descartar", methods=["POST"])
@login_required
def descartar_segmento(analisis_id, segmento_id):
    _exigir_modificacion()
    analisis = _lote_visible(analisis_id)
    segmento = _segmento_visible(analisis, segmento_id)
    if not segmento.pendiente:
        flash("Ese documento ya fue procesado.", "warning")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id))
    segmento.estado = "DESCARTADO"
    _actualizar_estado_lote(analisis)
    db.session.commit()
    flash(f"Documento {segmento.orden} descartado; no creó ningún registro.", "success")
    return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id))


@lote_documental_bp.route("/<int:analisis_id>/segmentos/<int:segmento_id>/confirmar", methods=["POST"])
@login_required
def confirmar_segmento(analisis_id, segmento_id):
    _exigir_modificacion()
    analisis = _lote_visible(analisis_id)
    segmento = _segmento_visible(analisis, segmento_id)
    if not segmento.pendiente:
        flash("Ese documento ya no está pendiente.", "warning")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id))

    datos = _datos_formulario(segmento)
    tipo = str(datos.get("tipo_documento_lote") or segmento.tipo_detectado or "OTRO").upper()
    if tipo not in TIPOS_DOCUMENTO_LOTE:
        flash("Seleccione un tipo documental válido.", "danger")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))

    no_sp = _limpiar(datos.get("no_sp"), 50)
    expediente, no_sp_normalizado = _resolver_sp(no_sp)
    if no_sp_normalizado:
        no_sp = no_sp_normalizado
        datos["no_sp"] = no_sp

    try:
        fecha_recepcion = _fecha(datos.get("fecha_recepcion"))
    except ValueError:
        flash("La fecha no tiene un formato válido.", "danger")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))

    try:
        inicio = _entero(datos.get("folio_inicio"))
        fin = _entero(datos.get("folio_fin"))
    except ValueError:
        flash("Los folios deben ser números enteros.", "danger")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))
    if (inicio is None) != (fin is None) or (inicio is not None and (inicio < 1 or fin < inicio)):
        flash("El rango de folios no es válido.", "danger")
        return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))

    total = None
    if tipo == "PAGO" and _limpiar(datos.get("total")):
        try:
            total = Decimal(str(datos.get("total")).replace(",", "."))
        except (InvalidOperation, ValueError):
            flash("El total del pago no es válido.", "danger")
            return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))

    documento_indice = None
    aviso_indice = None
    if request.form.get("crear_indice") == "1":
        documento_indice, aviso_indice = _crear_indice(expediente, tipo, datos, inicio, fin)

    registro = None
    if tipo in TIPOS_OPERATIVOS:
        if not no_sp:
            flash(f"Para crear el registro {tipo} debe confirmar el SP.", "danger")
            return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))
        registro = _crear_operativo(tipo, expediente, no_sp, datos, fecha_recepcion, total, documento_indice)

    datos_confirmados = {
        "tipo_documento_lote": tipo,
        "no_sp": no_sp,
        "rc": _limpiar(datos.get("rc"), 80),
        "providencia": _limpiar(datos.get("providencia"), 120),
        "fecha_recepcion": fecha_recepcion.isoformat() if fecha_recepcion else None,
        "folios": _limpiar(datos.get("folios"), 80),
        "folio_inicio": inicio,
        "folio_fin": fin,
        "numero_anexo": _limpiar(datos.get("numero_anexo"), 50),
        "titulo_anexo": _limpiar(datos.get("titulo_anexo"), 180),
        "tipo_anexo": _limpiar(datos.get("tipo_anexo"), 120),
        "boleta": _limpiar(datos.get("boleta"), 120),
        "total": str(total) if total is not None else _limpiar(datos.get("total"), 50),
        "periodo_texto": _limpiar(datos.get("periodo_texto"), 120),
        "numero_reporte": _limpiar(datos.get("numero_reporte"), 120),
        "tipo_evento": _limpiar(datos.get("tipo_evento"), 180),
        "tipo_documento": _limpiar(datos.get("tipo_documento"), 80),
        "numero_documento": _limpiar(datos.get("numero_documento"), 120),
        "nombre_documento": _limpiar(datos.get("nombre_documento"), 180),
        "observaciones": _limpiar(datos.get("observaciones")),
    }

    segmento.tipo_confirmado = tipo
    segmento.expediente_id = expediente.id if expediente else None
    segmento.estado = "CONFIRMADO"
    segmento.datos_confirmados = datos_confirmados
    segmento.registro_id = registro.id if registro else None
    segmento.documento_expediente_id = documento_indice.id if documento_indice else None
    segmento.confirmado_en = datetime.utcnow()
    _actualizar_aprendizaje(segmento, tipo, datos_confirmados)
    _actualizar_estado_lote(analisis)

    registrar_bitacora(
        accion="CONFIRMAR_DOCUMENTO_DE_LOTE",
        modulo="Coordinación",
        descripcion=(
            f"Documento {segmento.orden} del lote {analisis.id} confirmado como {tipo}; "
            f"páginas PDF {segmento.pagina_inicio}-{segmento.pagina_fin}."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id if expediente else None,
        entidad="SegmentoDocumental",
        entidad_id=segmento.id,
        datos_posteriores={
            "tipo_detectado": segmento.tipo_detectado,
            "tipo_confirmado": tipo,
            "registro_id": registro.id if registro else None,
            "documento_indice_id": documento_indice.id if documento_indice else None,
            "retroalimentacion_aprendizaje": True,
            "archivo_temporal_eliminado": True,
        },
        commit=False,
    )
    db.session.commit()

    if aviso_indice:
        flash(aviso_indice, "warning")
    if registro:
        flash(f"Documento {segmento.orden} confirmado como {tipo} y registrado automáticamente.", "success")
    elif documento_indice:
        flash(f"Documento {segmento.orden} confirmado y agregado al índice del expediente.", "success")
    else:
        flash(f"Documento {segmento.orden} confirmado. Sus metadatos quedan registrados en el lote; el PDF no se conserva.", "success")
    return redirect(url_for("lote_documental.resultado", analisis_id=analisis.id, _anchor=f"doc-{segmento.id}"))
