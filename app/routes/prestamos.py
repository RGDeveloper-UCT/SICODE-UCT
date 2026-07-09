from xml.sax.saxutils import escape
from io import BytesIO
from datetime import datetime
import re

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


from app import db
from app.forms.prestamo_form import PrestamoForm, DevolucionForm
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.services.bitacora_service import registrar_bitacora

prestamos_bp = Blueprint("prestamos", __name__)

def generar_numero_control(expediente):
    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PRE-{no_sp_limpio}-{marca_tiempo}"

@prestamos_bp.route("/prestamos")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()

    consulta = PrestamoExpediente.query.join(Expediente)

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                PrestamoExpediente.numero_control.ilike(filtro),
                PrestamoExpediente.solicitante.ilike(filtro),
                PrestamoExpediente.persona_entrega.ilike(filtro),
                PrestamoExpediente.persona_recibe.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
            )
        )

    if filtro_estado:
        consulta = consulta.filter(PrestamoExpediente.estado == filtro_estado)

    prestamos = consulta.order_by(PrestamoExpediente.fecha_prestamo.desc()).limit(150).all()

    estados = ["En préstamo", "Devuelto"]

    return render_template(
        "prestamos/listado.html",
        prestamos=prestamos,
        busqueda=busqueda,
        filtro_estado=filtro_estado,
        estados=estados,
    )

@prestamos_bp.route("/expedientes/<int:expediente_id>/prestamos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("No se puede prestar un expediente inactivo.", "danger")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    prestamo_abierto = (
        PrestamoExpediente.query
        .filter_by(expediente_id=expediente.id, estado="En préstamo")
        .first()
    )

    if prestamo_abierto:
        flash("Este expediente ya tiene un préstamo activo.", "warning")
        return redirect(url_for("prestamos.listado"))

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
        return redirect(url_for("prestamos.listado"))

    return render_template(
        "prestamos/formulario.html",
        form=form,
        expediente=expediente,
    )

@prestamos_bp.route("/prestamos/<int:prestamo_id>/devolver", methods=["GET", "POST"])
@login_required
def devolver(prestamo_id):
    prestamo = PrestamoExpediente.query.get_or_404(prestamo_id)
    expediente = prestamo.expediente

    if prestamo.estado == "Devuelto":
        flash("Este préstamo ya fue devuelto.", "warning")
        return redirect(url_for("prestamos.listado"))

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
        return redirect(url_for("prestamos.listado"))

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
    elementos = []

    elementos.append(Paragraph("SICODE-UCT", estilos["Title"]))
    elementos.append(Paragraph("Comprobante de préstamo / devolución de expediente", estilos["Heading2"]))
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph(
        "Documento administrativo de control de movimiento físico de expediente. "
        "Este comprobante no contiene documentos sensibles ni copias completas del expediente físico.",
        estilos["Normal"],
    ))

    elementos.append(Spacer(1, 18))

    datos_control = [
        ["Campo", "Valor"],
        ["Número de control", valor_pdf(prestamo.numero_control)],
        ["Estado del préstamo", valor_pdf(prestamo.estado)],
        ["Fecha de préstamo", prestamo.fecha_prestamo.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_prestamo else "Sin dato"],
        [
            "Fecha estimada de devolución",
            prestamo.fecha_estimada_devolucion.strftime("%d/%m/%Y") if prestamo.fecha_estimada_devolucion else "Sin dato",
        ],
        [
            "Fecha real de devolución",
            prestamo.fecha_real_devolucion.strftime("%d/%m/%Y %H:%M") if prestamo.fecha_real_devolucion else "Pendiente",
        ],
    ]

    tabla_control = Table(datos_control, colWidths=[2.5 * inch, 4.5 * inch])
    tabla_control.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(Paragraph("Datos de control", estilos["Heading3"]))
    elementos.append(tabla_control)
    elementos.append(Spacer(1, 18))

    datos_expediente = [
        ["Campo", "Valor"],
        ["Código interno", valor_pdf(expediente.codigo_interno)],
        ["No. de SP", valor_pdf(expediente.no_sp)],
        ["Nombre referencia", valor_pdf(expediente.nombre_referencia)],
        ["Estado administrativo actual", valor_pdf(expediente.estado_administrativo)],
        ["Estado físico/documental", valor_pdf(expediente.estado_fisico_documental)],
    ]

    tabla_expediente = Table(datos_expediente, colWidths=[2.5 * inch, 4.5 * inch])
    tabla_expediente.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(Paragraph("Datos del expediente", estilos["Heading3"]))
    elementos.append(tabla_expediente)
    elementos.append(Spacer(1, 18))

    datos_personas = [
        ["Campo", "Valor"],
        ["Solicitante", valor_pdf(prestamo.solicitante)],
        ["Persona que entrega", valor_pdf(prestamo.persona_entrega)],
        ["Persona que recibe", valor_pdf(prestamo.persona_recibe)],
        ["Persona que devuelve", valor_pdf(prestamo.persona_devuelve)],
        ["Persona que recibe devolución", valor_pdf(prestamo.persona_recibe_devolucion)],
    ]

    tabla_personas = Table(datos_personas, colWidths=[2.5 * inch, 4.5 * inch])
    tabla_personas.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(Paragraph("Personas relacionadas", estilos["Heading3"]))
    elementos.append(tabla_personas)
    elementos.append(Spacer(1, 18))

    elementos.append(Paragraph("Observaciones del préstamo", estilos["Heading3"]))
    elementos.append(Paragraph(valor_pdf(prestamo.observaciones), estilos["Normal"]))
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("Observaciones de devolución", estilos["Heading3"]))
    elementos.append(Paragraph(valor_pdf(prestamo.observaciones_devolucion), estilos["Normal"]))
    elementos.append(Spacer(1, 24))

    firmas = [
        ["Entrega", "Recibe", "Devuelve", "Recibe devolución"],
        ["", "", "", ""],
        ["__________________", "__________________", "__________________", "__________________"],
    ]

    tabla_firmas = Table(firmas, colWidths=[1.7 * inch, 1.7 * inch, 1.7 * inch, 1.7 * inch])
    tabla_firmas.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TOPPADDING", (0, 1), (-1, 1), 24),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 24),
    ]))

    elementos.append(Paragraph("Control de firmas", estilos["Heading3"]))
    elementos.append(tabla_firmas)
    elementos.append(Spacer(1, 18))

    elementos.append(Paragraph(
        "Generado desde SICODE-UCT para control interno institucional.",
        estilos["Italic"],
    ))

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
