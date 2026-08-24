from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.traslado_virtual import TrasladoVirtualExpediente
from app.services.bitacora_service import registrar_bitacora


rectificaciones_bp = Blueprint("rectificaciones", __name__)

TIPOS_ANEXO = [
    "REEMPLAZO",
    "MOVILIZACION",
    "AMPLIACION ZONA",
    "EXONERACION",
    "PRORROGA",
    "ZONA DE INCLUSION",
    "CARGADOR",
    "CORREA",
    "CARGADOR Y CORREA",
    "DCT, CARGADOR, CORREA",
    "2 CARGADORES Y CORREA",
    "DOS CARGADORES",
    "CAMBIO JUZGADO",
    "OTRO",
]
MAX_ANEXOS_RECTIFICADOS = 200


def _limpiar(valor, maximo=None):
    texto = str(valor or "").strip()
    if not texto:
        return None
    return texto[:maximo] if maximo else texto


def _fecha_desde_texto(valor):
    texto = _limpiar(valor)
    if not texto:
        return None
    return date.fromisoformat(texto)


def _serializar_anexo(anexo):
    return {
        "numero_anexo": anexo.numero_anexo or "",
        "titulo": anexo.titulo or "",
        "tipo_anexo": anexo.tipo_anexo or "",
        "fecha_recepcion": anexo.fecha_recepcion.isoformat() if anexo.fecha_recepcion else "",
        "persona_entrega": anexo.persona_entrega or "",
        "rc": anexo.rc or "",
        "providencia": anexo.providencia or "",
        "folios": anexo.folios or "",
        "escaneado": bool(anexo.escaneado),
        "fecha_escaneado": anexo.fecha_escaneado.isoformat() if anexo.fecha_escaneado else "",
        "observaciones": anexo.observaciones or "",
    }


def _anexo_enviado(indice):
    prefijo = f"anexo_{indice}_"
    bruto = {
        "numero_anexo": request.form.get(prefijo + "numero_anexo", ""),
        "titulo": request.form.get(prefijo + "titulo", ""),
        "tipo_anexo": request.form.get(prefijo + "tipo_anexo", ""),
        "fecha_recepcion": request.form.get(prefijo + "fecha_recepcion", ""),
        "persona_entrega": request.form.get(prefijo + "persona_entrega", ""),
        "rc": request.form.get(prefijo + "rc", ""),
        "providencia": request.form.get(prefijo + "providencia", ""),
        "folios": request.form.get(prefijo + "folios", ""),
        "escaneado": request.form.get(prefijo + "escaneado") == "1",
        "fecha_escaneado": request.form.get(prefijo + "fecha_escaneado", ""),
        "observaciones": request.form.get(prefijo + "observaciones", ""),
    }
    tiene_detalle = bruto["escaneado"] or any(
        str(bruto[clave] or "").strip()
        for clave in (
            "numero_anexo",
            "titulo",
            "tipo_anexo",
            "fecha_recepcion",
            "persona_entrega",
            "rc",
            "providencia",
            "folios",
            "fecha_escaneado",
            "observaciones",
        )
    )
    return bruto, tiene_detalle


def _construir_anexo(indice, expediente_id, errores):
    bruto, tiene_detalle = _anexo_enviado(indice)
    if not tiene_detalle:
        return None, bruto

    titulo = _limpiar(bruto["titulo"], 180)
    if not titulo:
        errores.append(f"Anexo {indice}: escriba un título si desea describir este anexo.")

    tipo_anexo = _limpiar(bruto["tipo_anexo"], 120)
    if tipo_anexo and tipo_anexo not in TIPOS_ANEXO:
        errores.append(f"Anexo {indice}: seleccione un tipo de anexo válido.")

    try:
        fecha_recepcion = _fecha_desde_texto(bruto["fecha_recepcion"])
    except ValueError:
        fecha_recepcion = None
        errores.append(f"Anexo {indice}: la fecha recibida no es válida.")

    try:
        fecha_escaneado = _fecha_desde_texto(bruto["fecha_escaneado"])
    except ValueError:
        fecha_escaneado = None
        errores.append(f"Anexo {indice}: la fecha de escaneo no es válida.")

    if bruto["escaneado"] and not fecha_escaneado:
        errores.append(f"Anexo {indice}: indique la fecha de escaneo cuando marque Escaneado.")

    if errores and not titulo:
        return None, bruto

    anexo = AnexoRectificado(
        expediente_id=expediente_id,
        numero_anexo=_limpiar(bruto["numero_anexo"], 50) or str(indice),
        titulo=titulo or f"Anexo {indice}",
        tipo_anexo=tipo_anexo,
        fecha_recepcion=fecha_recepcion,
        persona_entrega=_limpiar(bruto["persona_entrega"], 180),
        rc=_limpiar(bruto["rc"], 80),
        providencia=_limpiar(bruto["providencia"], 120),
        folios=_limpiar(bruto["folios"], 80),
        escaneado=bruto["escaneado"],
        fecha_escaneado=fecha_escaneado,
        observaciones=_limpiar(bruto["observaciones"]),
        creado_por_id=current_user.id,
        activo=True,
    )
    return anexo, bruto


def _valores_iniciales(expediente):
    folios = expediente.folios_rectificados
    if folios is None and expediente.total_folios_activos:
        folios = expediente.total_folios_activos

    anexos = expediente.anexos_rectificados
    if anexos is None:
        anexos_indice = len([doc for doc in expediente.documentos_activos if doc.es_anexo])
        anexos = anexos_indice if anexos_indice > 0 else ""

    detalles = [
        _serializar_anexo(anexo)
        for anexo in sorted(expediente.anexos_rectificados_activos, key=lambda item: item.id)
    ]
    return folios or "", anexos, detalles


@rectificaciones_bp.route("/expedientes/<int:expediente_id>/rectificar", methods=["GET", "POST"])
@login_required
def rectificar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not current_user.puede_modificar:
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    folios_inicial, anexos_inicial, detalles_iniciales = _valores_iniciales(expediente)

    if request.method == "POST":
        folios_texto = _limpiar(request.form.get("folios_rectificados"))
        anexos_texto = _limpiar(request.form.get("anexos_rectificados"))
        errores = []

        try:
            folios = int(folios_texto) if folios_texto is not None else None
        except ValueError:
            folios = None
        if folios is None or folios < 1:
            errores.append("Indique el total de folios rectificados con un número mayor que cero.")

        try:
            total_anexos = int(anexos_texto) if anexos_texto is not None else None
        except ValueError:
            total_anexos = None
        if total_anexos is None or total_anexos < 0:
            errores.append("Indique el total de anexos. Si no existen anexos, escriba 0.")
        elif total_anexos > MAX_ANEXOS_RECTIFICADOS:
            errores.append(f"El máximo permitido en una rectificación es {MAX_ANEXOS_RECTIFICADOS} anexos.")

        anexos_nuevos = []
        detalles_enviados = []
        if total_anexos is not None and 0 <= total_anexos <= MAX_ANEXOS_RECTIFICADOS:
            for indice in range(1, total_anexos + 1):
                anexo, bruto = _construir_anexo(indice, expediente.id, errores)
                detalles_enviados.append(bruto)
                if anexo is not None:
                    anexos_nuevos.append(anexo)

        if errores:
            for mensaje in dict.fromkeys(errores):
                flash(mensaje, "danger")
            return render_template(
                "expedientes/rectificar.html",
                expediente=expediente,
                folios_inicial=request.form.get("folios_rectificados", ""),
                anexos_inicial=request.form.get("anexos_rectificados", ""),
                detalles_iniciales=detalles_enviados,
                tipos_anexo=TIPOS_ANEXO,
                max_anexos=MAX_ANEXOS_RECTIFICADOS,
            )

        anteriores = {
            "folios_rectificados": expediente.folios_rectificados,
            "anexos_rectificados": expediente.anexos_rectificados,
            "estado_fisico_documental": expediente.estado_fisico_documental,
            "anexos_descritos": len(expediente.anexos_rectificados_activos),
        }

        for anexo_anterior in expediente.anexos_rectificados_activos:
            anexo_anterior.activo = False

        expediente.folios_rectificados = folios
        expediente.anexos_rectificados = total_anexos
        expediente.rectificado_en = datetime.utcnow()
        expediente.rectificado_por_id = current_user.id
        if expediente.estado_fisico_documental == "Pendiente de verificación":
            expediente.estado_fisico_documental = "Verificado"

        for anexo in anexos_nuevos:
            db.session.add(anexo)

        registrar_bitacora(
            accion="RECTIFICAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=(
                f"Se rectificó el SP {expediente.no_sp}: {folios} folios y "
                f"{total_anexos} anexos; {len(anexos_nuevos)} anexo(s) descrito(s)."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="Expediente",
            entidad_id=expediente.id,
            datos_anteriores=anteriores,
            datos_posteriores={
                "folios_rectificados": folios,
                "anexos_rectificados": total_anexos,
                "estado_fisico_documental": expediente.estado_fisico_documental,
                "anexos_descritos": len(anexos_nuevos),
            },
            commit=False,
        )
        db.session.commit()

        flash(
            f"SP {expediente.no_sp} rectificado: {folios} folios y {total_anexos} anexos.",
            "success",
        )
        return redirect(url_for("expedientes.listado", q=expediente.no_sp))

    return render_template(
        "expedientes/rectificar.html",
        expediente=expediente,
        folios_inicial=folios_inicial,
        anexos_inicial=anexos_inicial,
        detalles_iniciales=detalles_iniciales,
        tipos_anexo=TIPOS_ANEXO,
        max_anexos=MAX_ANEXOS_RECTIFICADOS,
    )


def _valor_pdf(valor):
    if valor is None or valor == "":
        return "Sin dato"
    return escape(str(valor))


def _fecha_rectificacion_pdf(expediente):
    if not expediente.rectificado_en:
        return "Sin dato"
    return expediente.rectificado_en.strftime("%d/%m/%Y %H:%M")


def _tabla_pdf(datos, anchos=(2.5 * inch, 4.5 * inch)):
    resultado = Table(datos, colWidths=list(anchos))
    resultado.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return resultado


def _bloqueo_pdf_si_falta_rectificacion(expediente):
    if expediente.rectificacion_completa:
        return None
    flash(
        f"Antes de generar la constancia del SP {expediente.no_sp} debe rectificar folios y anexos.",
        "warning",
    )
    return redirect(url_for("rectificaciones.rectificar", expediente_id=expediente.id))


@rectificaciones_bp.route("/rectificaciones/prestamos/<int:prestamo_id>/comprobante/pdf")
@login_required
def comprobante_prestamo_pdf(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    expediente = prestamo.expediente
    bloqueo = _bloqueo_pdf_si_falta_rectificacion(expediente)
    if bloqueo:
        return bloqueo

    archivo_pdf = BytesIO()
    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    estilos = getSampleStyleSheet()
    elementos = [
        Paragraph("SICODE-UCT", estilos["Title"]),
        Paragraph("Comprobante de préstamo / devolución de expediente", estilos["Heading2"]),
        Spacer(1, 12),
        Paragraph(
            "Documento administrativo de control de movimiento físico de expediente. "
            "Los conteos de folios y anexos corresponden a la última rectificación registrada en SICODE-UCT.",
            estilos["Normal"],
        ),
        Spacer(1, 18),
    ]

    datos_control = [
        ["Campo", "Valor"],
        ["Número de control", _valor_pdf(prestamo.numero_control)],
        ["Estado del préstamo", _valor_pdf(prestamo.estado)],
        ["Fecha de préstamo", prestamo.fecha_prestamo.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_prestamo else "Sin dato"],
        ["Fecha estimada de devolución", prestamo.fecha_estimada_devolucion.strftime("%d/%m/%Y") if prestamo.fecha_estimada_devolucion else "Sin dato"],
        ["Fecha real de devolución", prestamo.fecha_real_devolucion.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_real_devolucion else "Pendiente"],
    ]
    datos_expediente = [
        ["Campo", "Valor"],
        ["Código interno", _valor_pdf(expediente.codigo_interno)],
        ["No. de SP", _valor_pdf(expediente.no_sp)],
        ["Nombre referencia", _valor_pdf(expediente.nombre_referencia)],
        ["Folios rectificados", str(expediente.folios_rectificados)],
        ["Anexos rectificados", str(expediente.anexos_rectificados)],
        ["Anexos descritos en SICODE", str(len(expediente.anexos_rectificados_activos))],
        ["Fecha de rectificación", _fecha_rectificacion_pdf(expediente)],
        ["Rectificado por", _valor_pdf(expediente.rectificado_por.nombre if expediente.rectificado_por else None)],
        ["Estado administrativo actual", _valor_pdf(expediente.estado_administrativo)],
        ["Estado físico/documental", _valor_pdf(expediente.estado_fisico_documental)],
    ]
    datos_personas = [
        ["Campo", "Valor"],
        ["Solicitante", _valor_pdf(prestamo.solicitante)],
        ["Persona que entrega", _valor_pdf(prestamo.persona_entrega)],
        ["Persona que recibe", _valor_pdf(prestamo.persona_recibe)],
        ["Persona que devuelve", _valor_pdf(prestamo.persona_devuelve)],
        ["Persona que recibe devolución", _valor_pdf(prestamo.persona_recibe_devolucion)],
    ]

    for titulo, datos in (
        ("Datos de control", datos_control),
        ("Datos del expediente rectificado", datos_expediente),
        ("Personas relacionadas", datos_personas),
    ):
        elementos.append(Paragraph(titulo, estilos["Heading3"]))
        elementos.append(_tabla_pdf(datos))
        elementos.append(Spacer(1, 18))

    elementos.extend([
        Paragraph("Observaciones del préstamo", estilos["Heading3"]),
        Paragraph(_valor_pdf(prestamo.observaciones), estilos["Normal"]),
        Spacer(1, 12),
        Paragraph("Observaciones de devolución", estilos["Heading3"]),
        Paragraph(_valor_pdf(prestamo.observaciones_devolucion), estilos["Normal"]),
        Spacer(1, 24),
    ])

    firmas = [
        ["Entrega", "Recibe", "Devuelve", "Recibe devolución"],
        ["", "", "", ""],
        ["__________________", "__________________", "__________________", "__________________"],
    ]
    tabla_firmas = Table(firmas, colWidths=[1.7 * inch] * 4)
    tabla_firmas.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TOPPADDING", (0, 1), (-1, 1), 24),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 24),
    ]))
    elementos.extend([
        Paragraph("Control de firmas", estilos["Heading3"]),
        tabla_firmas,
        Spacer(1, 18),
        Paragraph("Generado desde SICODE-UCT para control interno institucional.", estilos["Italic"]),
    ])

    doc.build(elementos)
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_COMPROBANTE_PRESTAMO_PDF",
        modulo="Préstamos",
        descripcion=(
            f"Se generó comprobante PDF del préstamo {prestamo.numero_control} "
            f"del expediente No. de SP {expediente.no_sp}, con conteos rectificados."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    nombre_archivo = f"comprobante_{prestamo.numero_control}.pdf".replace(" ", "_").replace("/", "-")
    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )


@rectificaciones_bp.route("/rectificaciones/traslado-virtual/<int:traslado_id>/constancia/pdf")
@login_required
def constancia_virtual_pdf(traslado_id):
    traslado = TrasladoVirtualExpediente.query.get_or_404(traslado_id)
    expediente = traslado.expediente
    bloqueo = _bloqueo_pdf_si_falta_rectificacion(expediente)
    if bloqueo:
        return bloqueo

    archivo_pdf = BytesIO()
    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    )
    estilos = getSampleStyleSheet()
    elementos = [
        Paragraph("SICODE-UCT", estilos["Title"]),
        Paragraph("CONSTANCIA DE TRASLADO VIRTUAL DE EXPEDIENTE", estilos["Heading2"]),
        Spacer(1, 12),
        Paragraph(
            "Por medio de la presente se deja constancia administrativa del traslado virtual "
            "del expediente identificado a continuación. Los conteos de folios y anexos corresponden "
            "a la última rectificación registrada en SICODE-UCT. Documento sin firma.",
            estilos["Normal"],
        ),
        Spacer(1, 18),
    ]

    datos = [
        ["Campo", "Información registrada"],
        ["No. de constancia", _valor_pdf(traslado.numero_constancia)],
        ["Fecha y hora del traslado", traslado.creado_en.strftime("%d/%m/%Y %H:%M:%S")],
        ["No. SP", _valor_pdf(expediente.no_sp)],
        ["Código SICODE", _valor_pdf(expediente.codigo_interno)],
        ["Nombre de referencia", _valor_pdf(expediente.nombre_referencia)],
        ["Folios rectificados", str(expediente.folios_rectificados)],
        ["Anexos rectificados", str(expediente.anexos_rectificados)],
        ["Anexos descritos en SICODE", str(len(expediente.anexos_rectificados_activos))],
        ["Fecha de rectificación", _fecha_rectificacion_pdf(expediente)],
        ["Rectificado por", _valor_pdf(expediente.rectificado_por.nombre if expediente.rectificado_por else None)],
        ["Persona destinataria", _valor_pdf(traslado.destinatario)],
        ["Institución / dependencia / área", _valor_pdf(traslado.dependencia_destino)],
        ["Plataforma utilizada", _valor_pdf(traslado.plataforma)],
        ["Enlace de acceso registrado", _valor_pdf(traslado.enlace_corto)],
        ["Motivo o asunto", _valor_pdf(traslado.asunto)],
        ["Registrado por", _valor_pdf(traslado.usuario.nombre if traslado.usuario else None)],
    ]
    elementos.extend([
        _tabla_pdf(datos, anchos=(2.25 * inch, 4.75 * inch)),
        Spacer(1, 18),
        Paragraph("Observaciones", estilos["Heading3"]),
        Paragraph(_valor_pdf(traslado.observaciones), estilos["Normal"]),
        Spacer(1, 18),
        Paragraph(
            "SICODE-UCT registra esta constancia y el enlace utilizado como metadatos de control. "
            "El sistema no almacena una copia completa del expediente trasladado.",
            estilos["Italic"],
        ),
    ])

    doc.build(elementos)
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_CONSTANCIA_TRASLADO_VIRTUAL_PDF",
        modulo="Préstamos",
        descripcion=(
            f"Se generó PDF de la constancia {traslado.numero_constancia} "
            f"correspondiente al SP {expediente.no_sp}, con conteos rectificados."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="TrasladoVirtualExpediente",
        entidad_id=traslado.id,
    )

    nombre_archivo = f"constancia_traslado_virtual_SP_{expediente.no_sp}_{traslado.numero_constancia}.pdf"
    nombre_archivo = nombre_archivo.replace(" ", "_").replace("/", "-")
    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )
