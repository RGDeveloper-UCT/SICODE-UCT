import re
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.analisis_documental import AnalisisDocumental
from app.models.coordinacion import AnexoCoordinacion, MovimientoDispositivo, PagoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.models.documento_expediente import DocumentoExpediente
from app.models.lote_documental import PatronAprendizajeDocumental, SegmentoDocumental
from app.services.analisis_documental_service import DocumentoInvalido, OCRNoDisponible
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import determinar_estado, resolver_expediente
from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE, TIPOS_OPERATIVOS, analizar_lote_temporal

sicode_ia_bp = Blueprint("sicode_ia", __name__, url_prefix="/coordinacion/analisis-documental/ia")
MAX_ARCHIVOS = 100


def _exigir_modificacion():
    """Compatibilidad histórica: SICODE.IA está disponible a todo usuario autenticado."""
    if not current_user.is_authenticated:
        abort(401)


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


def _tamano_archivo(archivo):
    pos = archivo.stream.tell()
    archivo.stream.seek(0, 2)
    tamano = archivo.stream.tell()
    archivo.stream.seek(pos)
    return tamano


def _pesos_aprendidos():
    return {(p.tipo_documento, p.caracteristica): float(p.peso or 1.0) for p in PatronAprendizajeDocumental.query.all()}


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


def _crear_analisis(resultado, nombre_archivo, lote_token, orientacion):
    conteo = Counter(d["tipo"] for d in resultado["documentos"])
    analisis = AnalisisDocumental(
        usuario_id=current_user.id,
        tipo_objetivo="LOTE",
        tipo_detectado="LOTE_DOCUMENTAL",
        estado="PENDIENTE_VALIDACION",
        paginas_pdf=resultado["paginas_pdf"],
        paginas_ocr=resultado["paginas_ocr"],
        metodo_extraccion="SICODE_IA",
        datos_detectados={
            "modo": "SICODE_IA",
            "lote_token": lote_token,
            "archivo_origen": nombre_archivo,
            "contexto_usuario": orientacion.get("contexto_usuario"),
            "orientacion": orientacion,
            "documentos_total": resultado["documentos_total"],
            "tipos_detectados": dict(conteo),
        },
        confianzas={}, discrepancias=[], calidad_global=resultado["calidad_global"],
        pipeline_diagnostico={"etapas": resultado["pipeline"]}, fuentes_campos={}, explicaciones_campos={},
        ia_utilizada=resultado["ia_utilizada"], ia_modelo=resultado["ia_modelo"], duracion_ms=resultado["duracion_ms"],
    )
    db.session.add(analisis)
    db.session.flush()
    for orden, doc in enumerate(resultado["documentos"], start=1):
        datos = _aplicar_orientacion(doc["datos"], orientacion)
        expediente, normalizado = resolver_expediente(datos.get("no_sp"))
        if normalizado:
            datos["no_sp"] = normalizado
        db.session.add(SegmentoDocumental(
            analisis_id=analisis.id, expediente_id=expediente.id if expediente else None, orden=orden,
            pagina_inicio=doc["pagina_inicio"], pagina_fin=doc["pagina_fin"], tipo_detectado=doc["tipo"],
            estado="PENDIENTE_VALIDACION", calidad_global=doc["calidad_global"], datos_detectados=datos,
            confianzas=doc["confianzas"], fuentes_campos=doc["fuentes_campos"], discrepancias=doc["discrepancias"],
            caracteristicas_clasificacion=doc["caracteristicas"], ia_utilizada=doc["ia_utilizada"],
            ia_modelo=resultado["ia_modelo"] if doc["ia_utilizada"] else None,
        ))
    return analisis


def _analisis_lote(token):
    consulta = AnalisisDocumental.query.filter(AnalisisDocumental.tipo_detectado == "LOTE_DOCUMENTAL").order_by(AnalisisDocumental.id.asc()).all()
    salida = []
    for a in consulta:
        meta = dict(a.datos_detectados or {})
        if meta.get("modo") == "SICODE_IA" and meta.get("lote_token") == token:
            if current_user.rol == "administrador" or a.usuario_id == current_user.id:
                salida.append(a)
    if not salida:
        abort(404)
    return salida


def _segmentos_lote(analisis):
    return [s for a in analisis for s in a.segmentos]


@sicode_ia_bp.route("/", methods=["GET"])
@login_required
def inicio():
    _exigir_modificacion()
    return render_template("analisis_documental/sicode_ia_inicio.html", max_archivos=MAX_ARCHIVOS,
                           max_mb=current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40),
                           max_paginas=current_app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200))


@sicode_ia_bp.route("/analizar", methods=["POST"])
@login_required
def analizar():
    _exigir_modificacion()
    contexto = _limpiar(request.form.get("contexto_usuario"), 1000)
    if not contexto:
        flash("Describa brevemente qué documentación va a cargar para orientar SICODE.IA.", "danger")
        return redirect(url_for("sicode_ia.inicio"))
    archivos = [a for a in request.files.getlist("archivos_pdf") if a and a.filename]
    if not archivos or len(archivos) > MAX_ARCHIVOS:
        flash(f"Seleccione entre 1 y {MAX_ARCHIVOS} archivos PDF.", "danger")
        return redirect(url_for("sicode_ia.inicio"))
    if any(not a.filename.lower().endswith(".pdf") for a in archivos):
        flash("Todos los archivos deben ser PDF.", "danger")
        return redirect(url_for("sicode_ia.inicio"))
    max_mb = current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40)
    total = sum(_tamano_archivo(a) for a in archivos)
    if total > max_mb * 1024 * 1024:
        flash(f"La selección pesa {total/1024/1024:.1f} MB; el límite actual es {max_mb} MB.", "danger")
        return redirect(url_for("sicode_ia.inicio"))

    token = uuid.uuid4().hex
    orientacion = _orientacion_desde_contexto(contexto)
    creados, fallidos = [], []
    for archivo in archivos:
        try:
            resultado = analizar_lote_temporal(
                archivo, temp_dir=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"), max_mb=max_mb,
                max_paginas=current_app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200),
                ocr_habilitado=current_app.config.get("DOCUMENT_ANALYSIS_OCR_ENABLED", True),
                ocr_idioma=current_app.config.get("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa"),
                limpieza_minutos=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", 30),
                tesseract_cmd=current_app.config.get("DOCUMENT_ANALYSIS_TESSERACT_CMD"),
                ocr_segunda_pasada=current_app.config.get("DOCUMENT_ANALYSIS_OCR_SECOND_PASS", False),
                ia_habilitada=current_app.config.get("DOCUMENT_ANALYSIS_AI_ENABLED", True),
                ollama_url=current_app.config.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                ollama_model=current_app.config.get("DOCUMENT_ANALYSIS_AI_MODEL", current_app.config.get("OLLAMA_MODEL", "qwen3:1.7b")),
                ollama_timeout=current_app.config.get("DOCUMENT_ANALYSIS_AI_TIMEOUT", 75), pesos_aprendidos=_pesos_aprendidos())
            creados.append(_crear_analisis(resultado, archivo.filename, token, orientacion))
        except (DocumentoInvalido, OCRNoDisponible, RuntimeError) as exc:
            fallidos.append(f"{archivo.filename}: {exc}")
        except Exception:
            current_app.logger.exception("SICODE.IA no pudo procesar %s", archivo.filename)
            fallidos.append(f"{archivo.filename}: error inesperado")
    if not creados:
        db.session.rollback()
        for e in fallidos:
            flash(e, "danger")
        return redirect(url_for("sicode_ia.inicio"))
    registrar_bitacora(accion="SICODE_IA_ANALISIS_GUIADO", modulo="Coordinación",
        descripcion=f"SICODE.IA procesó {len(creados)} PDF con contexto guiado y dejó la carga pendiente de doble verificación humana.",
        usuario_id=current_user.id, entidad="AnalisisDocumental", datos_posteriores={"lote_token": token, "contexto": contexto, "fallidos": fallidos}, commit=False)
    db.session.commit()
    for e in fallidos:
        flash(e, "warning")
    return redirect(url_for("sicode_ia.revision", token=token))


@sicode_ia_bp.route("/revision/<token>")
@login_required
def revision(token):
    _exigir_modificacion()
    analisis = _analisis_lote(token)
    segmentos = _segmentos_lote(analisis)
    verificados = sum(1 for s in segmentos if s.estado == "VERIFICADO_HUMANO")
    cargados = sum(1 for s in segmentos if s.estado == "CONFIRMADO")
    return render_template("analisis_documental/sicode_ia_revision.html", analisis=analisis, segmentos=segmentos,
                           token=token, verificados=verificados, cargados=cargados, total=len(segmentos),
                           tipos_documento=TIPOS_DOCUMENTO_LOTE)


@sicode_ia_bp.route("/revision/<token>/segmento/<int:segmento_id>/verificar", methods=["POST"])
@login_required
def verificar_segmento(token, segmento_id):
    _exigir_modificacion()
    analisis = _analisis_lote(token)
    ids = {s.id for s in _segmentos_lote(analisis)}
    if segmento_id not in ids:
        abort(404)
    s = SegmentoDocumental.query.get_or_404(segmento_id)
    if s.estado == "CONFIRMADO":
        flash("Este documento ya fue cargado definitivamente.", "warning")
        return redirect(url_for("sicode_ia.revision", token=token, _anchor=f"doc-{s.id}"))
    datos = dict(s.datos_detectados or {})
    for clave in ("tipo_documento_lote","no_sp","folio_inicio","folio_fin","numero_anexo","titulo_anexo","tipo_anexo","rc","providencia","numero_documento","nombre_documento","fecha_recepcion","folios","boleta","total","periodo_texto","numero_reporte","tipo_evento","tipo_documento","descripcion","observaciones"):
        if clave in request.form:
            datos[clave] = request.form.get(clave, "")
    tipo = str(datos.get("tipo_documento_lote") or s.tipo_detectado or "OTRO").upper()
    if tipo not in TIPOS_DOCUMENTO_LOTE:
        flash("Seleccione un tipo documental válido.", "danger")
        return redirect(url_for("sicode_ia.revision", token=token, _anchor=f"doc-{s.id}"))
    try:
        inicio, fin = _entero(datos.get("folio_inicio")), _entero(datos.get("folio_fin"))
    except ValueError:
        flash("Los folios deben ser enteros.", "danger")
        return redirect(url_for("sicode_ia.revision", token=token, _anchor=f"doc-{s.id}"))
    if (inicio is None) != (fin is None) or (inicio is not None and (inicio < 1 or fin < inicio)):
        flash("El rango de folios no es válido.", "danger")
        return redirect(url_for("sicode_ia.revision", token=token, _anchor=f"doc-{s.id}"))
    datos["tipo_documento_lote"], datos["folio_inicio"], datos["folio_fin"] = tipo, inicio, fin
    s.tipo_confirmado = tipo
    s.datos_confirmados = datos
    s.estado = "VERIFICADO_HUMANO"
    s.confirmado_en = datetime.utcnow()
    db.session.commit()
    flash("Verificación Humana Correcta registrada. Aún no se cargó información definitiva.", "success")
    return redirect(url_for("sicode_ia.revision", token=token, _anchor=f"doc-{s.id}"))


def _crear_indice(expediente, tipo, datos, inicio, fin):
    if not expediente or inicio is None or fin is None:
        return None
    solapado = DocumentoExpediente.query.filter_by(expediente_id=expediente.id, activo=True).filter(DocumentoExpediente.folio_inicio <= fin, DocumentoExpediente.folio_fin >= inicio).first()
    if solapado:
        return None
    numero = _limpiar(datos.get("numero_anexo"), 50)
    titulo = _limpiar(datos.get("titulo_anexo"), 180)
    nombre = (f"Anexo {numero} - {titulo}" if tipo == "ANEXO" and numero else (titulo if tipo == "ANEXO" and titulo else (_limpiar(datos.get("nombre_documento"),180) or _limpiar(datos.get("numero_documento"),120) or tipo.title())))
    doc = DocumentoExpediente(expediente_id=expediente.id, nombre_documento=nombre[:180], tipo_documento=tipo.title()[:80], folio_inicio=inicio, folio_fin=fin, total_folios=fin-inicio+1, estado_revision="Pendiente de revisión", es_anexo=(tipo=="ANEXO"), observaciones="Carga definitiva desde SICODE.IA tras doble verificación humana.", activo=True)
    db.session.add(doc); db.session.flush(); return doc


def _crear_operativo(tipo, expediente, no_sp, datos, fecha_recepcion, documento_indice):
    if tipo not in TIPOS_OPERATIVOS:
        return None
    total = None
    if tipo == "PAGO" and _limpiar(datos.get("total")):
        try: total = Decimal(str(datos.get("total")).replace(",", "."))
        except (InvalidOperation, ValueError): total = None
    campos = [no_sp, fecha_recepcion]
    registro = RegistroCoordinacion(tipo=tipo, expediente_id=expediente.id if expediente else None, no_sp_referencia=no_sp,
        rc=_limpiar(datos.get("rc"),80), providencia=_limpiar(datos.get("providencia"),120), fecha_recepcion=fecha_recepcion,
        persona_entrega=None, folios_recepcion=_limpiar(datos.get("folios"),80), usuario_id=current_user.id,
        usuario_origen=current_user.nombre, estado=determinar_estado(expediente, no_sp, campos_clave=campos),
        observaciones=_limpiar(datos.get("observaciones")), origen_registro="SICODE_IA_DOBLE_VERIFICACION")
    db.session.add(registro); db.session.flush()
    if tipo == "ANEXO": db.session.add(AnexoCoordinacion(registro_id=registro.id, documento_expediente_id=documento_indice.id if documento_indice else None, tipo_anexo=_limpiar(datos.get("tipo_anexo"),120), titulo=_limpiar(datos.get("titulo_anexo"),180), folios=_limpiar(datos.get("folios"),80), escaneado=True, fecha_escaneado=date.today(), numero_anexo=_limpiar(datos.get("numero_anexo"),50)))
    elif tipo in {"INSTALACION","DESINSTALACION"}: db.session.add(MovimientoDispositivo(registro_id=registro.id, movimiento=tipo, descripcion=_limpiar(datos.get("descripcion"),180) or "EXPEDIENTE", folios=_limpiar(datos.get("folios"),80)))
    elif tipo == "PAGO": db.session.add(PagoCoordinacion(registro_id=registro.id, folios=_limpiar(datos.get("folios"),80), periodo_texto=_limpiar(datos.get("periodo_texto"),120), boleta=_limpiar(datos.get("boleta"),120), total=total))
    elif tipo == "MONITOREO": db.session.add(ReporteMonitoreo(registro_id=registro.id, tipo_documento=_limpiar(datos.get("tipo_documento"),80) or "PROVIDENCIA", numero_reporte=_limpiar(datos.get("numero_reporte"),120), tipo_evento=_limpiar(datos.get("tipo_evento"),180)))
    return registro


@sicode_ia_bp.route("/revision/<token>/cargar", methods=["POST"])
@login_required
def cargar(token):
    _exigir_modificacion()
    analisis = _analisis_lote(token)
    segmentos = _segmentos_lote(analisis)
    pendientes = [s for s in segmentos if s.estado not in {"VERIFICADO_HUMANO", "CONFIRMADO"}]
    if pendientes:
        flash(f"Faltan {len(pendientes)} documento(s) por marcar como Verificación Humana Correcta.", "danger")
        return redirect(url_for("sicode_ia.revision", token=token))
    nuevos = [s for s in segmentos if s.estado == "VERIFICADO_HUMANO"]
    if not nuevos:
        flash("Este lote ya fue cargado o no tiene documentos pendientes de carga.", "warning")
        return redirect(url_for("sicode_ia.revision", token=token))
    for s in nuevos:
        datos = dict(s.datos_confirmados or {})
        tipo = str(datos.get("tipo_documento_lote") or s.tipo_confirmado or "OTRO").upper()
        expediente, no_sp = resolver_expediente(datos.get("no_sp"))
        try: fecha_recepcion = _fecha(datos.get("fecha_recepcion"))
        except ValueError: fecha_recepcion = None
        inicio, fin = datos.get("folio_inicio"), datos.get("folio_fin")
        documento = _crear_indice(expediente, tipo, datos, inicio, fin)
        registro = _crear_operativo(tipo, expediente, no_sp, datos, fecha_recepcion, documento)
        s.expediente_id = expediente.id if expediente else None
        s.documento_expediente_id = documento.id if documento else None
        s.registro_id = registro.id if registro else None
        s.estado = "CONFIRMADO"
        s.confirmado_en = datetime.utcnow()
    for a in analisis:
        if all(s.estado == "CONFIRMADO" for s in a.segmentos):
            a.estado = "CONFIRMADO"; a.confirmado_en = datetime.utcnow()
    registrar_bitacora(accion="SICODE_IA_CARGA_VERIFICACION_HUMANA_CORRECTA", modulo="Coordinación",
        descripcion=f"Carga de Verificación Humana Correcta realizada para {len(nuevos)} documento(s) del lote {token[:8]}.",
        usuario_id=current_user.id, entidad="AnalisisDocumental", datos_posteriores={"lote_token":token,"documentos_cargados":len(nuevos),"doble_verificacion":True}, commit=False)
    db.session.commit()
    flash("Carga de Verificación Humana Correcta realizada. La información validada ya fue registrada en SICODE.", "success")
    return redirect(url_for("sicode_ia.revision", token=token))