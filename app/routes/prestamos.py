from datetime import date, datetime
from io import BytesIO
import re
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_

from app import db
from app.forms.prestamo_form import DevolucionForm, PrestamoForm, TrasladoVirtualForm
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.traslado_virtual import TrasladoVirtualExpediente
from app.services.alertas_service import detectar_prestamos_vencidos
from app.services.bitacora_service import registrar_bitacora
from app.services.sp_service import normalizar_sp


prestamos_bp = Blueprint("prestamos", __name__)


def generar_numero_control(expediente):
    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PRE-{no_sp_limpio}-{marca_tiempo}"


def generar_numero_constancia_virtual(expediente):
    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"TVE-{no_sp_limpio}-{marca_tiempo}"


def _normalizar_enlace_virtual(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    if not re.match(r"^https?://", texto, flags=re.IGNORECASE):
        texto = f"https://{texto}"
    analizado = urlparse(texto)
    if analizado.scheme.lower() not in {"http", "https"} or not analizado.netloc:
        return None
    return texto


def _ids_prestamos_activos():
    return db.session.query(PrestamoExpediente.expediente_id).filter(
        PrestamoExpediente.estado == "En préstamo",
        PrestamoExpediente.activo.is_(True),
    )


def _consulta_expedientes_panel(busqueda="", filtro_estado=""):
    """Consulta maestra: todos los SP, con préstamo físico y traslado virtual relacionados."""
    consulta = Expediente.query
    ids_activos = _ids_prestamos_activos()

    if busqueda:
        filtro = f"%{busqueda}%"
        ids_por_prestamo = db.session.query(PrestamoExpediente.expediente_id).filter(
            or_(
                PrestamoExpediente.numero_control.ilike(filtro),
                PrestamoExpediente.solicitante.ilike(filtro),
                PrestamoExpediente.persona_entrega.ilike(filtro),
                PrestamoExpediente.persona_recibe.ilike(filtro),
            )
        )
        ids_por_virtual = db.session.query(TrasladoVirtualExpediente.expediente_id).filter(
            or_(
                TrasladoVirtualExpediente.numero_constancia.ilike(filtro),
                TrasladoVirtualExpediente.destinatario.ilike(filtro),
                TrasladoVirtualExpediente.dependencia_destino.ilike(filtro),
                TrasladoVirtualExpediente.plataforma.ilike(filtro),
                TrasladoVirtualExpediente.enlace_corto.ilike(filtro),
                TrasladoVirtualExpediente.asunto.ilike(filtro),
            )
        )
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
                Expediente.nombres.ilike(filtro),
                Expediente.apellidos.ilike(filtro),
                Expediente.id.in_(ids_por_prestamo),
                Expediente.id.in_(ids_por_virtual),
            )
        )

    if filtro_estado == "Disponibles":
        consulta = consulta.filter(
            Expediente.activo.is_(True),
            Expediente.expediente_fisico_registrado.is_(True),
            ~Expediente.id.in_(ids_activos),
        )
    elif filtro_estado == "En préstamo":
        consulta = consulta.filter(Expediente.id.in_(ids_activos))
    elif filtro_estado == "Devuelto":
        ids_devueltos = db.session.query(PrestamoExpediente.expediente_id).filter(
            PrestamoExpediente.estado == "Devuelto"
        )
        consulta = consulta.filter(
            Expediente.id.in_(ids_devueltos),
            ~Expediente.id.in_(ids_activos),
        )
    elif filtro_estado == "Vencidos":
        ids_vencidos = db.session.query(PrestamoExpediente.expediente_id).filter(
            PrestamoExpediente.estado == "En préstamo",
            PrestamoExpediente.activo.is_(True),
            PrestamoExpediente.fecha_estimada_devolucion.isnot(None),
            PrestamoExpediente.fecha_estimada_devolucion < date.today(),
        )
        consulta = consulta.filter(Expediente.id.in_(ids_vencidos))
    elif filtro_estado == "Sin préstamo":
        ids_con_historial = db.session.query(PrestamoExpediente.expediente_id)
        consulta = consulta.filter(~Expediente.id.in_(ids_con_historial))
    elif filtro_estado == "Traslado virtual":
        ids_virtuales = db.session.query(TrasladoVirtualExpediente.expediente_id)
        consulta = consulta.filter(Expediente.id.in_(ids_virtuales))

    return consulta


def _clave_orden_sp(expediente):
    clave = normalizar_sp(expediente.no_sp)
    if clave and clave.isdigit():
        return 0, int(clave)
    return 1, clave or ""


def _construir_filas_panel(expedientes):
    ids = [expediente.id for expediente in expedientes]
    prestamos = []
    virtuales = []
    if ids:
        prestamos = (
            PrestamoExpediente.query
            .filter(PrestamoExpediente.expediente_id.in_(ids))
            .order_by(PrestamoExpediente.fecha_prestamo.desc(), PrestamoExpediente.id.desc())
            .all()
        )
        virtuales = (
            TrasladoVirtualExpediente.query
            .filter(TrasladoVirtualExpediente.expediente_id.in_(ids))
            .order_by(TrasladoVirtualExpediente.creado_en.desc(), TrasladoVirtualExpediente.id.desc())
            .all()
        )

    ultimo_por_expediente = {}
    activo_por_expediente = {}
    ultimo_virtual_por_expediente = {}
    for prestamo in prestamos:
        ultimo_por_expediente.setdefault(prestamo.expediente_id, prestamo)
        if (
            prestamo.estado == "En préstamo"
            and prestamo.activo
            and prestamo.expediente_id not in activo_por_expediente
        ):
            activo_por_expediente[prestamo.expediente_id] = prestamo
    for traslado in virtuales:
        ultimo_virtual_por_expediente.setdefault(traslado.expediente_id, traslado)

    filas = []
    hoy = date.today()
    for expediente in sorted(expedientes, key=_clave_orden_sp):
        prestamo_activo = activo_por_expediente.get(expediente.id)
        ultimo_prestamo = ultimo_por_expediente.get(expediente.id)
        ultimo_virtual = ultimo_virtual_por_expediente.get(expediente.id)

        if prestamo_activo and prestamo_activo.fecha_estimada_devolucion and prestamo_activo.fecha_estimada_devolucion < hoy:
            estado_prestamo = "Vencido"
        elif prestamo_activo:
            estado_prestamo = "En préstamo"
        elif ultimo_prestamo and ultimo_prestamo.estado == "Devuelto":
            estado_prestamo = "Devuelto"
        else:
            estado_prestamo = "Sin préstamo"

        puede_prestar = bool(
            expediente.activo
            and expediente.expediente_fisico_registrado
            and prestamo_activo is None
        )
        puede_traslado_virtual = bool(expediente.activo)

        if not expediente.activo:
            motivo_bloqueo = "SP inactivo"
        elif not expediente.expediente_fisico_registrado:
            motivo_bloqueo = "Sin expediente físico"
        elif prestamo_activo:
            motivo_bloqueo = "Préstamo activo"
        else:
            motivo_bloqueo = None

        filas.append({
            "expediente": expediente,
            "prestamo_activo": prestamo_activo,
            "ultimo_prestamo": ultimo_prestamo,
            "ultimo_virtual": ultimo_virtual,
            "estado_prestamo": estado_prestamo,
            "puede_prestar": puede_prestar,
            "puede_traslado_virtual": puede_traslado_virtual,
            "motivo_bloqueo": motivo_bloqueo,
        })
    return filas


@prestamos_bp.route("/prestamos")
@login_required
def listado():
    alertas_generadas = detectar_prestamos_vencidos(usuario_id=current_user.id)
    if alertas_generadas:
        registrar_bitacora(
            accion="GENERAR_ALERTA_PRESTAMO_VENCIDO",
            modulo="Alertas",
            descripcion=(
                f"Se generaron {len(alertas_generadas)} alerta(s) automática(s) "
                "por préstamo vencido desde el módulo de préstamos."
            ),
            usuario_id=current_user.id,
        )

    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()
    estados = [
        "Disponibles",
        "En préstamo",
        "Devuelto",
        "Vencidos",
        "Sin préstamo",
        "Traslado virtual",
    ]

    expedientes = _consulta_expedientes_panel(busqueda, filtro_estado).all()
    filas = _construir_filas_panel(expedientes)

    total_sp = Expediente.query.count()
    ids_activos = _ids_prestamos_activos()
    total_en_prestamo = Expediente.query.filter(Expediente.id.in_(ids_activos)).count()
    total_disponibles = Expediente.query.filter(
        Expediente.activo.is_(True),
        Expediente.expediente_fisico_registrado.is_(True),
        ~Expediente.id.in_(ids_activos),
    ).count()
    total_virtuales = TrasladoVirtualExpediente.query.count()

    return render_template(
        "prestamos/listado.html",
        filas=filas,
        busqueda=busqueda,
        filtro_estado=filtro_estado,
        estados=estados,
        total_sp=total_sp,
        total_en_prestamo=total_en_prestamo,
        total_disponibles=total_disponibles,
        total_virtuales=total_virtuales,
    )


@prestamos_bp.route("/expedientes/<int:expediente_id>/prestamos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("No se puede prestar un SP inactivo.", "danger")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    if not expediente.expediente_fisico_registrado:
        flash(
            "No se puede generar un préstamo porque este SP todavía no tiene expediente físico registrado.",
            "warning",
        )
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    prestamo_abierto = (
        PrestamoExpediente.query
        .filter_by(expediente_id=expediente.id, estado="En préstamo", activo=True)
        .first()
    )
    if prestamo_abierto:
        flash("Este expediente ya tiene un préstamo activo.", "warning")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    form = PrestamoForm()
    if form.validate_on_submit():
        prestamo = PrestamoExpediente(
            expediente_id=expediente.id,
            numero_control=generar_numero_control(expediente),
            solicitante=form.solicitante.data.strip(),
            persona_entrega=form.persona_entrega.data.strip(),
            persona_recibe=form.persona_recibe.data.strip(),
            fecha_estimada_devolucion=form.fecha_estimada_devolucion.data,
            estado="En préstamo",
            observaciones=form.observaciones.data,
            activo=True,
        )
        expediente.estado_administrativo = "En préstamo"
        db.session.add(prestamo)
        db.session.commit()

        registrar_bitacora(
            accion="REGISTRAR_PRESTAMO",
            modulo="Préstamos",
            descripcion=(
                f"Se registró préstamo del expediente No. de SP {expediente.no_sp}. "
                f"Número de control: {prestamo.numero_control}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )
        flash("Préstamo registrado correctamente.", "success")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    return render_template("prestamos/formulario.html", form=form, expediente=expediente)


@prestamos_bp.route("/expedientes/<int:expediente_id>/traslado-virtual/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_traslado_virtual(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    if not expediente.activo:
        flash("No se puede registrar un traslado virtual para un SP inactivo.", "danger")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    form = TrasladoVirtualForm()
    if form.validate_on_submit():
        enlace = _normalizar_enlace_virtual(form.enlace_corto.data)
        if not enlace:
            flash("El enlace debe ser una dirección web válida (http o https).", "danger")
            return render_template(
                "prestamos/traslado_virtual_formulario.html",
                form=form,
                expediente=expediente,
            )

        traslado = TrasladoVirtualExpediente(
            expediente_id=expediente.id,
            usuario_id=current_user.id,
            numero_constancia=generar_numero_constancia_virtual(expediente),
            destinatario=form.destinatario.data.strip(),
            dependencia_destino=(form.dependencia_destino.data or "").strip() or None,
            plataforma=form.plataforma.data,
            enlace_corto=enlace,
            asunto=form.asunto.data.strip(),
            observaciones=form.observaciones.data,
            creado_en=datetime.utcnow(),
        )
        db.session.add(traslado)
        db.session.commit()

        registrar_bitacora(
            accion="REGISTRAR_TRASLADO_VIRTUAL",
            modulo="Préstamos",
            descripcion=(
                f"Se registró constancia de traslado virtual del SP {expediente.no_sp} "
                f"a {traslado.destinatario} mediante {traslado.plataforma}. "
                f"Constancia: {traslado.numero_constancia}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="TrasladoVirtualExpediente",
            entidad_id=traslado.id,
            datos_posteriores={
                "numero_constancia": traslado.numero_constancia,
                "destinatario": traslado.destinatario,
                "dependencia_destino": traslado.dependencia_destino,
                "plataforma": traslado.plataforma,
                "enlace_corto": traslado.enlace_corto,
                "asunto": traslado.asunto,
            },
        )
        return redirect(url_for("prestamos.constancia_virtual_pdf", traslado_id=traslado.id))

    return render_template(
        "prestamos/traslado_virtual_formulario.html",
        form=form,
        expediente=expediente,
    )


@prestamos_bp.route("/prestamos/traslado-virtual/<int:traslado_id>/constancia/pdf")
@login_required
def constancia_virtual_pdf(traslado_id):
    traslado = TrasladoVirtualExpediente.query.get_or_404(traslado_id)
    expediente = traslado.expediente

    def valor_pdf(valor):
        if valor is None or valor == "":
            return "Sin dato"
        return escape(str(valor))

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
            "del expediente identificado a continuación. Esta constancia registra el envío y "
            "sus metadatos de control; no requiere firma y no sustituye un acuse de recepción del destinatario.",
            estilos["Normal"],
        ),
        Spacer(1, 18),
    ]

    datos = [
        ["Campo", "Información registrada"],
        ["No. de constancia", valor_pdf(traslado.numero_constancia)],
        ["Fecha y hora del traslado", traslado.creado_en.strftime("%d/%m/%Y %H:%M:%S")],
        ["No. SP", valor_pdf(expediente.no_sp)],
        ["Código SICODE", valor_pdf(expediente.codigo_interno)],
        ["Nombre de referencia", valor_pdf(expediente.nombre_referencia)],
        ["Persona destinataria", valor_pdf(traslado.destinatario)],
        ["Institución / dependencia / área", valor_pdf(traslado.dependencia_destino)],
        ["Plataforma utilizada", valor_pdf(traslado.plataforma)],
        ["Enlace de acceso registrado", valor_pdf(traslado.enlace_corto)],
        ["Motivo o asunto", valor_pdf(traslado.asunto)],
        ["Registrado por", valor_pdf(traslado.usuario.nombre if traslado.usuario else None)],
    ]
    tabla = Table(datos, colWidths=[2.25 * inch, 4.75 * inch])
    tabla.setStyle(TableStyle([
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
    elementos.extend([
        tabla,
        Spacer(1, 18),
        Paragraph("Observaciones", estilos["Heading3"]),
        Paragraph(valor_pdf(traslado.observaciones), estilos["Normal"]),
        Spacer(1, 18),
        Paragraph(
            "SICODE-UCT registra esta constancia y el enlace utilizado como metadatos de control. "
            "El sistema no almacena una copia completa del expediente trasladado. Documento sin firma.",
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
            f"correspondiente al SP {expediente.no_sp}."
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


@prestamos_bp.route("/prestamos/<int:prestamo_id>/devolver", methods=["GET", "POST"])
@login_required
def devolver(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    expediente = prestamo.expediente

    if prestamo.estado == "Devuelto":
        flash("Este préstamo ya fue devuelto.", "warning")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    form = DevolucionForm()
    if form.validate_on_submit():
        prestamo.estado = "Devuelto"
        prestamo.fecha_real_devolucion = datetime.utcnow()
        prestamo.persona_devuelve = form.persona_devuelve.data.strip()
        prestamo.persona_recibe_devolucion = form.persona_recibe_devolucion.data.strip()
        prestamo.observaciones_devolucion = form.observaciones_devolucion.data
        expediente.estado_administrativo = "Devuelto"
        db.session.commit()

        registrar_bitacora(
            accion="REGISTRAR_DEVOLUCION",
            modulo="Préstamos",
            descripcion=(
                f"Se registró devolución del expediente No. de SP {expediente.no_sp}. "
                f"Número de control: {prestamo.numero_control}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )
        flash("Devolución registrada correctamente.", "success")
        return redirect(url_for("prestamos.listado", q=expediente.no_sp))

    return render_template(
        "prestamos/devolver.html",
        form=form,
        prestamo=prestamo,
        expediente=expediente,
    )


@prestamos_bp.route("/prestamos/<int:prestamo_id>/comprobante/pdf")
@login_required
def comprobante_pdf(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    expediente = prestamo.expediente

    def valor_pdf(valor):
        if valor is None or valor == "":
            return "Sin dato"
        return escape(str(valor))

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
            "Este comprobante no contiene documentos sensibles ni copias completas del expediente físico.",
            estilos["Normal"],
        ),
        Spacer(1, 18),
    ]

    datos_control = [
        ["Campo", "Valor"],
        ["Número de control", valor_pdf(prestamo.numero_control)],
        ["Estado del préstamo", valor_pdf(prestamo.estado)],
        ["Fecha de préstamo", prestamo.fecha_prestamo.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_prestamo else "Sin dato"],
        ["Fecha estimada de devolución", prestamo.fecha_estimada_devolucion.strftime("%d/%m/%Y") if prestamo.fecha_estimada_devolucion else "Sin dato"],
        ["Fecha real de devolución", prestamo.fecha_real_devolucion.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_real_devolucion else "Pendiente"],
    ]
    datos_expediente = [
        ["Campo", "Valor"],
        ["Código interno", valor_pdf(expediente.codigo_interno)],
        ["No. de SP", valor_pdf(expediente.no_sp)],
        ["Nombre referencia", valor_pdf(expediente.nombre_referencia)],
        ["Estado administrativo actual", valor_pdf(expediente.estado_administrativo)],
        ["Estado físico/documental", valor_pdf(expediente.estado_fisico_documental)],
    ]
    datos_personas = [
        ["Campo", "Valor"],
        ["Solicitante", valor_pdf(prestamo.solicitante)],
        ["Persona que entrega", valor_pdf(prestamo.persona_entrega)],
        ["Persona que recibe", valor_pdf(prestamo.persona_recibe)],
        ["Persona que devuelve", valor_pdf(prestamo.persona_devuelve)],
        ["Persona que recibe devolución", valor_pdf(prestamo.persona_recibe_devolucion)],
    ]

    def tabla(datos):
        resultado = Table(datos, colWidths=[2.5 * inch, 4.5 * inch])
        resultado.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))
        return resultado

    for titulo, datos in (
        ("Datos de control", datos_control),
        ("Datos del expediente", datos_expediente),
        ("Personas relacionadas", datos_personas),
    ):
        elementos.append(Paragraph(titulo, estilos["Heading3"]))
        elementos.append(tabla(datos))
        elementos.append(Spacer(1, 18))

    elementos.extend([
        Paragraph("Observaciones del préstamo", estilos["Heading3"]),
        Paragraph(valor_pdf(prestamo.observaciones), estilos["Normal"]),
        Spacer(1, 12),
        Paragraph("Observaciones de devolución", estilos["Heading3"]),
        Paragraph(valor_pdf(prestamo.observaciones_devolucion), estilos["Normal"]),
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
            f"del expediente No. de SP {expediente.no_sp}."
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


@prestamos_bp.route("/prestamos/exportar/excel")
@login_required
def exportar_excel():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()
    expedientes = _consulta_expedientes_panel(busqueda, filtro_estado).all()
    filas = _construir_filas_panel(expedientes)

    wb = Workbook()
    ws = wb.active
    ws.title = "Control de prestamos"
    encabezados = [
        "No. SP",
        "Código interno",
        "Nombre",
        "Expediente físico",
        "Estado préstamo físico",
        "Número control físico actual/último",
        "Solicitante físico",
        "Fecha préstamo físico",
        "Fecha estimada devolución",
        "Fecha real devolución",
        "Disponibilidad",
        "Última constancia virtual",
        "Destinatario virtual",
        "Dependencia destino virtual",
        "Plataforma virtual",
        "Fecha traslado virtual",
        "Enlace virtual",
    ]
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for fila in filas:
        expediente = fila["expediente"]
        movimiento = fila["prestamo_activo"] or fila["ultimo_prestamo"]
        virtual = fila["ultimo_virtual"]
        ws.append([
            expediente.no_sp,
            expediente.codigo_interno,
            expediente.nombre_referencia or "",
            "Sí" if expediente.expediente_fisico_registrado else "No",
            fila["estado_prestamo"],
            movimiento.numero_control if movimiento else "",
            movimiento.solicitante if movimiento else "",
            movimiento.fecha_prestamo.strftime("%d/%m/%Y %H:%M") if movimiento and movimiento.fecha_prestamo else "",
            movimiento.fecha_estimada_devolucion.strftime("%d/%m/%Y") if movimiento and movimiento.fecha_estimada_devolucion else "",
            movimiento.fecha_real_devolucion.strftime("%d/%m/%Y %H:%M") if movimiento and movimiento.fecha_real_devolucion else "",
            expediente.disponibilidad,
            virtual.numero_constancia if virtual else "",
            virtual.destinatario if virtual else "",
            virtual.dependencia_destino if virtual else "",
            virtual.plataforma if virtual else "",
            virtual.creado_en.strftime("%d/%m/%Y %H:%M:%S") if virtual else "",
            virtual.enlace_corto if virtual else "",
        ])

    anchos = {
        "A": 14, "B": 22, "C": 32, "D": 18, "E": 20, "F": 32, "G": 28,
        "H": 22, "I": 24, "J": 24, "K": 22, "L": 34, "M": 28, "N": 30,
        "O": 20, "P": 24, "Q": 45,
    }
    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    registrar_bitacora(
        accion="EXPORTAR_PRESTAMOS_EXCEL",
        modulo="Reportes",
        descripcion=f"Se exportó el panel maestro de préstamos y traslados virtuales. SP exportados: {len(filas)}.",
        usuario_id=current_user.id,
    )

    archivo_excel = BytesIO()
    wb.save(archivo_excel)
    archivo_excel.seek(0)
    return send_file(
        archivo_excel,
        as_attachment=True,
        download_name="control_prestamos_y_traslados_virtuales_sicode_uct.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@prestamos_bp.route("/prestamos/<int:prestamo_id>")
@login_required
def detalle(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    return render_template(
        "prestamos/detalle.html",
        prestamo=prestamo,
        expediente=prestamo.expediente,
    )
