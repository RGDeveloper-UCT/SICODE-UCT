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
from app.models.expediente import Expediente
from app.services.analisis_documental_service import (
    DocumentoInvalido,
    OCRNoDisponible,
    TIPOS_ANEXO,
    TIPOS_EVENTO,
    TIPOS_REGISTRO_ADMITIDOS,
    analizar_pdf_temporal,
)
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import determinar_estado, resolver_expediente


analisis_documental_bp = Blueprint(
    "analisis_documental",
    __name__,
    url_prefix="/coordinacion/analisis-documental",
)

TIPOS_CONFIRMABLES = {"ANEXO", "INSTALACION", "DESINSTALACION", "PAGO", "MONITOREO"}


def _exigir_modificacion():
    if not current_user.puede_modificar:
        abort(403)


def _limpiar(valor, maximo=None):
    texto = str(valor or "").strip()
    if not texto:
        return None
    return texto[:maximo] if maximo else texto


def _fecha(valor):
    texto = _limpiar(valor)
    if not texto:
        return None
    return date.fromisoformat(texto)


def _entero(valor):
    texto = _limpiar(valor)
    if texto is None:
        return None
    return int(texto)


def _analisis_visible(analisis_id):
    analisis = AnalisisDocumental.query.get_or_404(analisis_id)
    if current_user.rol != "administrador" and analisis.usuario_id != current_user.id:
        abort(403)
    return analisis


def _resolver_sp(no_sp):
    expediente, no_sp_normalizado = resolver_expediente(no_sp)
    return expediente, no_sp_normalizado


def _discrepancias_bd(datos, expediente):
    discrepancias = []
    if datos.get("no_sp") and expediente is None:
        discrepancias.append(
            f"El SP {datos['no_sp']} fue detectado en el PDF, pero no existe como expediente activo en SICODE."
        )
    if not expediente:
        return discrepancias

    total_folios = datos.get("total_folios")
    if total_folios and expediente.folios_rectificados is not None and total_folios != expediente.folios_rectificados:
        discrepancias.append(
            f"El documento analizado contiene {total_folios} folio(s) detectados; la rectificación maestra del SP registra "
            f"{expediente.folios_rectificados}. Esto no se modificará automáticamente."
        )

    numero_anexo = _limpiar(datos.get("numero_anexo"), 50)
    if numero_anexo:
        detalle = next(
            (
                item
                for item in expediente.anexos_rectificados_activos
                if str(item.numero_anexo or "").strip().upper() == numero_anexo.upper()
            ),
            None,
        )
        if detalle and datos.get("folios") and detalle.folios:
            if str(detalle.folios).strip() != str(datos["folios"]).strip():
                discrepancias.append(
                    f"El Anexo {numero_anexo} ya está descrito en la rectificación con folios “{detalle.folios}”; "
                    f"el análisis propone “{datos['folios']}”. Revise antes de confirmar."
                )

    return discrepancias


def _datos_formulario(analisis):
    datos = dict(analisis.datos_detectados or {})
    if request.method != "POST":
        return datos
    claves = (
        "tipo_registro",
        "no_sp",
        "rc",
        "providencia",
        "fecha_recepcion",
        "persona_entrega",
        "folios",
        "folio_inicio",
        "folio_fin",
        "numero_anexo",
        "titulo_anexo",
        "tipo_anexo",
        "boleta",
        "total",
        "periodo_texto",
        "numero_reporte",
        "tipo_evento",
        "tipo_documento",
        "descripcion",
        "observaciones",
    )
    for clave in claves:
        datos[clave] = request.form.get(clave, "")
    return datos


def _validar_confirmacion(datos):
    errores = []
    tipo = str(datos.get("tipo_registro") or "").upper()
    if tipo not in TIPOS_CONFIRMABLES:
        errores.append("Seleccione el tipo de registro que corresponde al documento.")

    no_sp = _limpiar(datos.get("no_sp"), 50)
    if not no_sp:
        errores.append("Confirme el No. de SP antes de registrar la información.")

    try:
        fecha_recepcion = _fecha(datos.get("fecha_recepcion"))
    except ValueError:
        fecha_recepcion = None
        errores.append("La fecha recibida no es válida.")

    folio_inicio = folio_fin = None
    try:
        folio_inicio = _entero(datos.get("folio_inicio"))
        folio_fin = _entero(datos.get("folio_fin"))
    except ValueError:
        errores.append("Los folios inicial y final deben ser números enteros.")
    if (folio_inicio is None) != (folio_fin is None):
        errores.append("Para crear el índice documental indique tanto folio inicial como folio final.")
    if folio_inicio is not None and (folio_inicio < 1 or folio_fin < folio_inicio):
        errores.append("El rango de folios no es válido.")

    if tipo == "ANEXO" and not _limpiar(datos.get("titulo_anexo"), 180):
        errores.append("Confirme un título para el anexo.")

    total = None
    if tipo == "PAGO" and _limpiar(datos.get("total")):
        try:
            total = Decimal(str(datos.get("total")).replace(",", "."))
        except (InvalidOperation, ValueError):
            errores.append("El total del pago no tiene un formato numérico válido.")

    return {
        "errores": errores,
        "tipo": tipo,
        "no_sp": no_sp,
        "fecha_recepcion": fecha_recepcion,
        "folio_inicio": folio_inicio,
        "folio_fin": folio_fin,
        "total": total,
    }


def _crear_indice_anexo(expediente, datos, validacion):
    if request.form.get("crear_indice") != "1" or expediente is None:
        return None, None

    inicio, fin = validacion["folio_inicio"], validacion["folio_fin"]
    if inicio is None or fin is None:
        return None, "No se creó índice documental porque no hay un rango de folios confirmado."

    solapado = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=True)
        .filter(DocumentoExpediente.folio_inicio <= fin, DocumentoExpediente.folio_fin >= inicio)
        .first()
    )
    if solapado:
        return None, (
            f"No se incorporó automáticamente al índice porque el rango {inicio}-{fin} se cruza con "
            f"“{solapado.nombre_documento}” ({solapado.folio_inicio}-{solapado.folio_fin})."
        )

    titulo = _limpiar(datos.get("titulo_anexo"), 180) or "Anexo"
    numero = _limpiar(datos.get("numero_anexo"), 50)
    nombre = f"Anexo {numero} - {titulo}" if numero else titulo
    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=nombre[:180],
        tipo_documento="Anexo",
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision="Pendiente de revisión",
        es_anexo=True,
        observaciones="Incorporado desde Análisis documental asistido; validado por usuario.",
        activo=True,
    )
    db.session.add(documento)
    db.session.flush()
    return documento, None


@analisis_documental_bp.route("/", methods=["GET", "POST"])
@login_required
def inicio():
    _exigir_modificacion()

    if request.method == "POST":
        archivo = request.files.get("archivo_pdf")
        tipo_objetivo = str(request.form.get("tipo_objetivo") or "AUTO").upper()
        if tipo_objetivo not in TIPOS_REGISTRO_ADMITIDOS:
            tipo_objetivo = "AUTO"

        if not archivo or not archivo.filename:
            flash("Seleccione un archivo PDF para analizar.", "danger")
            return redirect(url_for("analisis_documental.inicio"))
        if not archivo.filename.lower().endswith(".pdf"):
            flash("Solo se permiten archivos PDF.", "danger")
            return redirect(url_for("analisis_documental.inicio"))

        try:
            resultado = analizar_pdf_temporal(
                archivo,
                tipo_objetivo=tipo_objetivo,
                temp_dir=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"),
                max_mb=current_app.config.get("DOCUMENT_ANALYSIS_MAX_MB", 40),
                max_paginas=current_app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES", 200),
                ocr_habilitado=current_app.config.get("DOCUMENT_ANALYSIS_OCR_ENABLED", True),
                ocr_idioma=current_app.config.get("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa"),
                limpieza_minutos=current_app.config.get("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", 30),
            )
        except (DocumentoInvalido, OCRNoDisponible, RuntimeError) as exc:
            current_app.logger.warning("Análisis documental rechazado: %s", exc)
            flash(str(exc), "danger")
            return redirect(url_for("analisis_documental.inicio"))
        except Exception:
            current_app.logger.exception("Fallo inesperado durante análisis documental")
            flash("No fue posible analizar el PDF. El archivo temporal fue descartado.", "danger")
            return redirect(url_for("analisis_documental.inicio"))

        datos = resultado["datos"]
        expediente, no_sp_normalizado = _resolver_sp(datos.get("no_sp"))
        if no_sp_normalizado:
            datos["no_sp"] = no_sp_normalizado

        discrepancias = list(resultado["advertencias"])
        discrepancias.extend(_discrepancias_bd(datos, expediente))

        analisis = AnalisisDocumental(
            usuario_id=current_user.id,
            expediente_id=expediente.id if expediente else None,
            tipo_objetivo=tipo_objetivo,
            tipo_detectado=datos.get("tipo_registro") or "DOCUMENTO",
            estado="PENDIENTE_VALIDACION",
            paginas_pdf=resultado["paginas_pdf"],
            paginas_ocr=resultado["paginas_ocr"],
            metodo_extraccion=resultado["metodo_extraccion"],
            datos_detectados=datos,
            confianzas=resultado["confianzas"],
            discrepancias=discrepancias,
        )
        db.session.add(analisis)
        db.session.flush()
        registrar_bitacora(
            accion="ANALIZAR_DOCUMENTO_TEMPORAL",
            modulo="Coordinación",
            descripcion=(
                f"Análisis temporal No. {analisis.id}: {analisis.paginas_pdf} página(s), "
                f"tipo propuesto {analisis.tipo_detectado}, SP {datos.get('no_sp') or 'no detectado'}. "
                "El PDF y el texto de extracción no se conservaron."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id if expediente else None,
            entidad="AnalisisDocumental",
            entidad_id=analisis.id,
            datos_posteriores={
                "tipo_detectado": analisis.tipo_detectado,
                "paginas_pdf": analisis.paginas_pdf,
                "paginas_ocr": analisis.paginas_ocr,
                "metodo_extraccion": analisis.metodo_extraccion,
                "sp": datos.get("no_sp"),
                "archivo_temporal_eliminado": True,
            },
            commit=False,
        )
        db.session.commit()
        return redirect(url_for("analisis_documental.resultado", analisis_id=analisis.id))

    consulta = AnalisisDocumental.query
    if current_user.rol != "administrador":
        consulta = consulta.filter_by(usuario_id=current_user.id)
    recientes = consulta.order_by(AnalisisDocumental.creado_en.desc()).limit(25).all()
    return render_template(
        "analisis_documental/inicio.html",
        recientes=recientes,
        tipos_objetivo=("AUTO", "ANEXO", "INSTALACION", "DESINSTALACION", "PAGO", "MONITOREO"),
    )


@analisis_documental_bp.route("/<int:analisis_id>")
@login_required
def resultado(analisis_id):
    _exigir_modificacion()
    analisis = _analisis_visible(analisis_id)
    return render_template(
        "analisis_documental/resultado.html",
        analisis=analisis,
        datos=dict(analisis.datos_detectados or {}),
        tipos_anexo=TIPOS_ANEXO,
        tipos_evento=TIPOS_EVENTO,
        tipos_confirmables=sorted(TIPOS_CONFIRMABLES),
    )


@analisis_documental_bp.route("/<int:analisis_id>/descartar", methods=["POST"])
@login_required
def descartar(analisis_id):
    _exigir_modificacion()
    analisis = _analisis_visible(analisis_id)
    if analisis.estado == "CONFIRMADO":
        flash("Este análisis ya fue confirmado y no puede descartarse.", "warning")
        return redirect(url_for("analisis_documental.resultado", analisis_id=analisis.id))

    analisis.estado = "DESCARTADO"
    registrar_bitacora(
        accion="DESCARTAR_ANALISIS_DOCUMENTAL",
        modulo="Coordinación",
        descripcion=f"Se descartó la propuesta del análisis documental No. {analisis.id}.",
        usuario_id=current_user.id,
        expediente_id=analisis.expediente_id,
        entidad="AnalisisDocumental",
        entidad_id=analisis.id,
        commit=False,
    )
    db.session.commit()
    flash("La propuesta fue descartada. No se creó ningún registro operativo.", "success")
    return redirect(url_for("analisis_documental.inicio"))


@analisis_documental_bp.route("/<int:analisis_id>/confirmar", methods=["POST"])
@login_required
def confirmar(analisis_id):
    _exigir_modificacion()
    analisis = _analisis_visible(analisis_id)
    if not analisis.pendiente:
        flash("Este análisis ya no está pendiente de validación.", "warning")
        return redirect(url_for("analisis_documental.resultado", analisis_id=analisis.id))

    datos = _datos_formulario(analisis)
    validacion = _validar_confirmacion(datos)
    if validacion["errores"]:
        for error in validacion["errores"]:
            flash(error, "danger")
        return render_template(
            "analisis_documental/resultado.html",
            analisis=analisis,
            datos=datos,
            tipos_anexo=TIPOS_ANEXO,
            tipos_evento=TIPOS_EVENTO,
            tipos_confirmables=sorted(TIPOS_CONFIRMABLES),
        )

    tipo = validacion["tipo"]
    expediente, no_sp = _resolver_sp(validacion["no_sp"])
    campos_clave = [no_sp, validacion["fecha_recepcion"]]
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
        fecha_recepcion=validacion["fecha_recepcion"],
        persona_entrega=_limpiar(datos.get("persona_entrega"), 180),
        folios_recepcion=_limpiar(datos.get("folios"), 80),
        usuario_id=current_user.id,
        usuario_origen=current_user.nombre,
        estado=determinar_estado(expediente, no_sp, campos_clave=campos_clave),
        observaciones=_limpiar(datos.get("observaciones")),
        origen_registro="ANALISIS_PDF",
    )
    db.session.add(registro)
    db.session.flush()

    advertencia_indice = None
    if tipo == "ANEXO":
        documento_indice, advertencia_indice = _crear_indice_anexo(expediente, datos, validacion)
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
            total=validacion["total"],
        ))
    elif tipo == "MONITOREO":
        db.session.add(ReporteMonitoreo(
            registro_id=registro.id,
            tipo_documento=_limpiar(datos.get("tipo_documento"), 80) or "PROVIDENCIA",
            numero_reporte=_limpiar(datos.get("numero_reporte"), 120),
            tipo_evento=_limpiar(datos.get("tipo_evento"), 180),
        ))

    datos_confirmados = {
        "tipo_registro": tipo,
        "no_sp": no_sp,
        "rc": registro.rc,
        "providencia": registro.providencia,
        "fecha_recepcion": registro.fecha_recepcion.isoformat() if registro.fecha_recepcion else None,
        "persona_entrega": registro.persona_entrega,
        "folios": registro.folios_recepcion,
        "folio_inicio": validacion["folio_inicio"],
        "folio_fin": validacion["folio_fin"],
        "numero_anexo": _limpiar(datos.get("numero_anexo"), 50),
        "titulo_anexo": _limpiar(datos.get("titulo_anexo"), 180),
        "tipo_anexo": _limpiar(datos.get("tipo_anexo"), 120),
        "boleta": _limpiar(datos.get("boleta"), 120),
        "total": str(validacion["total"]) if validacion["total"] is not None else None,
        "periodo_texto": _limpiar(datos.get("periodo_texto"), 120),
        "numero_reporte": _limpiar(datos.get("numero_reporte"), 120),
        "tipo_evento": _limpiar(datos.get("tipo_evento"), 180),
        "tipo_documento": _limpiar(datos.get("tipo_documento"), 80),
        "descripcion": _limpiar(datos.get("descripcion"), 180),
    }

    analisis.estado = "CONFIRMADO"
    analisis.expediente_id = expediente.id if expediente else None
    analisis.registro_id = registro.id
    analisis.tipo_detectado = tipo
    analisis.datos_confirmados = datos_confirmados
    analisis.confirmado_en = datetime.utcnow()

    registrar_bitacora(
        accion=f"REGISTRAR_{tipo}_DESDE_ANALISIS_PDF",
        modulo="Coordinación",
        descripcion=(
            f"Se validó el análisis documental No. {analisis.id} y se creó el registro {registro.id} "
            f"de tipo {tipo} para SP {no_sp}."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id if expediente else None,
        entidad="RegistroCoordinacion",
        entidad_id=registro.id,
        datos_posteriores={
            "analisis_id": analisis.id,
            "tipo": tipo,
            "sp": no_sp,
            "estado": registro.estado,
            "archivo_temporal_eliminado": True,
        },
        commit=False,
    )
    db.session.commit()

    if advertencia_indice:
        flash(advertencia_indice, "warning")
    flash(
        f"Análisis validado. Se creó el registro {tipo} para el SP {no_sp}; el PDF no se conserva en SICODE.",
        "success",
    )
    return redirect(url_for("coordinacion.detalle", registro_id=registro.id))
