import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from datetime import date
from xml.sax.saxutils import escape
from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


from app import db
from app.forms.expediente_form import ExpedienteForm
from app.models.expediente import Expediente
from app.models.documento_expediente import DocumentoExpediente
from app.models.alerta import Alerta
from app.models.prestamo import PrestamoExpediente
from app.models.bitacora import Bitacora
from app.models.ubicacion import UbicacionFisica
from app.services.bitacora_service import registrar_bitacora
from app.services.alertas_service import crear_alerta_si_no_existe

expedientes_bp = Blueprint("expedientes", __name__)

@expedientes_bp.route("/expedientes")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_activo = request.args.get("activo", "").strip()
    filtro_estado_admin = request.args.get("estado_administrativo", "").strip()
    filtro_estado_fisico = request.args.get("estado_fisico_documental", "").strip()

    consulta = Expediente.query

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
            )
        )

    if filtro_activo == "si":
        consulta = consulta.filter(Expediente.activo == True)
    elif filtro_activo == "no":
        consulta = consulta.filter(Expediente.activo == False)

    if filtro_estado_admin:
        consulta = consulta.filter(Expediente.estado_administrativo == filtro_estado_admin)

    if filtro_estado_fisico:
        consulta = consulta.filter(Expediente.estado_fisico_documental == filtro_estado_fisico)

    expedientes = consulta.order_by(Expediente.creado_en.desc()).all()

    estados_administrativos = [
        "Activo",
        "En revisión",
        "En préstamo",
        "Devuelto",
        "Cerrado",
    ]

    estados_fisicos = [
        "Pendiente de verificación",
        "Verificado",
        "Con observaciones",
        "Incompleto",
        "No localizado",
    ]

    return render_template(
        "expedientes/listado.html",
        expedientes=expedientes,
        busqueda=busqueda,
        filtro_activo=filtro_activo,
        filtro_estado_admin=filtro_estado_admin,
        filtro_estado_fisico=filtro_estado_fisico,
        estados_administrativos=estados_administrativos,
        estados_fisicos=estados_fisicos,
    )

@expedientes_bp.route("/expedientes/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    form = ExpedienteForm()

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = Expediente.query.filter_by(codigo_interno=codigo_interno).first()
        existe_sp = Expediente.query.filter_by(no_sp=no_sp).first()

        if existe_codigo:
            flash("Ya existe un expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        if existe_sp:
            flash("Ya existe un expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        expediente = Expediente(
            codigo_interno=codigo_interno,
            no_sp=no_sp,
            nombre_referencia=form.nombre_referencia.data.strip() if form.nombre_referencia.data else None,
            estado_administrativo=form.estado_administrativo.data,
            estado_fisico_documental=form.estado_fisico_documental.data,
            observaciones=form.observaciones.data,
            activo=True,
        )

        db.session.add(expediente)
        db.session.flush()

        ubicacion = UbicacionFisica(
            expediente_id=expediente.id,
            archivador=form.archivador.data,
            sicoin=form.sicoin.data,
            estante=form.estante.data,
            caja=form.caja.data,
            modulo=form.modulo.data,
            posicion=form.posicion.data,
            observaciones=form.observaciones.data,
        )

        db.session.add(ubicacion)
        db.session.commit()

        registrar_bitacora(
            accion="CREAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se creó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        if expediente.estado_fisico_documental in ["Con observaciones", "Incompleto", "No localizado"]:
            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                tipo_alerta="REVISION_EXPEDIENTE",
                titulo=f"Expediente requiere revisión: {expediente.no_sp}",
                descripcion=f"El expediente fue registrado con estado físico/documental: {expediente.estado_fisico_documental}.",
                gravedad="Alta" if expediente.estado_fisico_documental == "No localizado" else "Media",
                usuario_id=current_user.id,
            )

        flash("Expediente creado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

@expedientes_bp.route("/expedientes/<int:expediente_id>")
@login_required
def detalle(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    return render_template(
        "expedientes/detalle.html",
        expediente=expediente,
        ubicacion=ubicacion,
    )

@expedientes_bp.route("/expedientes/<int:expediente_id>/editar", methods=["GET", "POST"])
@login_required
def editar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    form = ExpedienteForm()
    form.submit.label.text = "Actualizar expediente"

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = (
            Expediente.query
            .filter(Expediente.codigo_interno == codigo_interno, Expediente.id != expediente.id)
            .first()
        )

        existe_sp = (
            Expediente.query
            .filter(Expediente.no_sp == no_sp, Expediente.id != expediente.id)
            .first()
        )

        if existe_codigo:
            flash("Ya existe otro expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        if existe_sp:
            flash("Ya existe otro expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        expediente.codigo_interno = codigo_interno
        expediente.no_sp = no_sp
        expediente.nombre_referencia = form.nombre_referencia.data.strip() if form.nombre_referencia.data else None
        expediente.estado_administrativo = form.estado_administrativo.data
        expediente.estado_fisico_documental = form.estado_fisico_documental.data
        expediente.observaciones = form.observaciones.data

        if not ubicacion:
            ubicacion = UbicacionFisica(expediente_id=expediente.id)
            db.session.add(ubicacion)

        ubicacion.archivador = form.archivador.data
        ubicacion.sicoin = form.sicoin.data
        ubicacion.estante = form.estante.data
        ubicacion.caja = form.caja.data
        ubicacion.modulo = form.modulo.data
        ubicacion.posicion = form.posicion.data
        ubicacion.observaciones = form.observaciones.data

        db.session.commit()

        registrar_bitacora(
            accion="EDITAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se actualizó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        if expediente.estado_fisico_documental in ["Con observaciones", "Incompleto", "No localizado"]:
            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                tipo_alerta="REVISION_EXPEDIENTE",
                titulo=f"Expediente requiere revisión: {expediente.no_sp}",
                descripcion=f"El expediente fue actualizado con estado físico/documental: {expediente.estado_fisico_documental}.",
                gravedad="Alta" if expediente.estado_fisico_documental == "No localizado" else "Media",
                usuario_id=current_user.id,
            )

        flash("Expediente actualizado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    if request.method == "GET":
        form.codigo_interno.data = expediente.codigo_interno
        form.no_sp.data = expediente.no_sp
        form.nombre_referencia.data = expediente.nombre_referencia
        form.estado_administrativo.data = expediente.estado_administrativo
        form.estado_fisico_documental.data = expediente.estado_fisico_documental
        form.observaciones.data = expediente.observaciones

        if ubicacion:
            form.archivador.data = ubicacion.archivador
            form.sicoin.data = ubicacion.sicoin
            form.estante.data = ubicacion.estante
            form.caja.data = ubicacion.caja
            form.modulo.data = ubicacion.modulo
            form.posicion.data = ubicacion.posicion

    return render_template("expedientes/formulario.html", form=form, modo="Editar")

@expedientes_bp.route("/expedientes/<int:expediente_id>/desactivar", methods=["POST"])
@login_required
def desactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("El expediente ya se encuentra desactivado.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = False
    db.session.commit()

    registrar_bitacora(
        accion="DESACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se desactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente desactivado correctamente. El registro se conserva para trazabilidad.", "info")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

@expedientes_bp.route("/expedientes/<int:expediente_id>/reactivar", methods=["POST"])
@login_required
def reactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if expediente.activo:
        flash("El expediente ya se encuentra activo.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = True
    db.session.commit()

    registrar_bitacora(
        accion="REACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se reactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente reactivado correctamente.", "success")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

@expedientes_bp.route("/expedientes/exportar/excel")
@login_required
def exportar_excel():
    busqueda = request.args.get("q", "").strip()
    filtro_activo = request.args.get("activo", "").strip()
    filtro_estado_admin = request.args.get("estado_administrativo", "").strip()
    filtro_estado_fisico = request.args.get("estado_fisico_documental", "").strip()

    consulta = Expediente.query

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
            )
        )

    if filtro_activo == "si":
        consulta = consulta.filter(Expediente.activo == True)
    elif filtro_activo == "no":
        consulta = consulta.filter(Expediente.activo == False)

    if filtro_estado_admin:
        consulta = consulta.filter(Expediente.estado_administrativo == filtro_estado_admin)

    if filtro_estado_fisico:
        consulta = consulta.filter(Expediente.estado_fisico_documental == filtro_estado_fisico)

    expedientes = consulta.order_by(Expediente.creado_en.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expedientes"

    encabezados = [
        "ID",
        "Código interno",
        "No. de SP",
        "Nombre referencia",
        "Estado administrativo",
        "Estado físico/documental",
        "Activo",
        "Archivador",
        "SICOIN",
        "Estante",
        "Caja",
        "Módulo",
        "Posición",
        "Observaciones",
        "Fecha creación",
    ]

    ws.append(encabezados)

    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for expediente in expedientes:
        ubicacion = (
            UbicacionFisica.query
            .filter_by(expediente_id=expediente.id)
            .order_by(UbicacionFisica.creado_en.desc())
            .first()
        )

        ws.append([
            expediente.id,
            expediente.codigo_interno,
            expediente.no_sp,
            expediente.nombre_referencia or "",
            expediente.estado_administrativo,
            expediente.estado_fisico_documental,
            "Sí" if expediente.activo else "No",
            ubicacion.archivador if ubicacion else "",
            ubicacion.sicoin if ubicacion else "",
            ubicacion.estante if ubicacion else "",
            ubicacion.caja if ubicacion else "",
            ubicacion.modulo if ubicacion else "",
            ubicacion.posicion if ubicacion else "",
            expediente.observaciones or "",
            expediente.creado_en.strftime("%d/%m/%Y %H:%M") if expediente.creado_en else "",
        ])

    anchos = {
        "A": 8,
        "B": 22,
        "C": 16,
        "D": 28,
        "E": 24,
        "F": 28,
        "G": 12,
        "H": 16,
        "I": 16,
        "J": 16,
        "K": 16,
        "L": 16,
        "M": 16,
        "N": 40,
        "O": 22,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    registrar_bitacora(
        accion="EXPORTAR_EXPEDIENTES_EXCEL",
        modulo="Reportes",
        descripcion=f"Se exportó listado de expedientes a Excel. Registros exportados: {len(expedientes)}.",
        usuario_id=current_user.id,
    )

    archivo_excel = BytesIO()
    wb.save(archivo_excel)
    archivo_excel.seek(0)

    return send_file(
        archivo_excel,
        as_attachment=True,
        download_name="reporte_expedientes_sicode_uct.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@expedientes_bp.route("/expedientes/<int:expediente_id>/exportar/pdf")
@login_required
def exportar_pdf(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

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

    titulo = Paragraph("SICODE-UCT", estilos["Title"])
    subtitulo = Paragraph("Reporte individual de expediente", estilos["Heading2"])
    nota = Paragraph(
        "Reporte administrativo generado con metadatos de control, ubicación física y observaciones. "
        "Este reporte no contiene documentos sensibles ni copias completas del expediente físico.",
        estilos["Normal"],
    )

    elementos.append(titulo)
    elementos.append(subtitulo)
    elementos.append(Spacer(1, 12))
    elementos.append(nota)
    elementos.append(Spacer(1, 18))

    datos_principales = [
        ["Campo", "Valor"],
        ["Código interno", valor_pdf(expediente.codigo_interno)],
        ["No. de SP", valor_pdf(expediente.no_sp)],
        ["Nombre referencia", valor_pdf(expediente.nombre_referencia)],
        ["Estado administrativo", valor_pdf(expediente.estado_administrativo)],
        ["Estado físico/documental", valor_pdf(expediente.estado_fisico_documental)],
        ["Activo", "Sí" if expediente.activo else "No"],
        [
            "Fecha de creación",
            expediente.creado_en.strftime("%d/%m/%Y %H:%M") if expediente.creado_en else "Sin dato",
        ],
    ]

    tabla_principal = Table(datos_principales, colWidths=[2.2 * inch, 4.8 * inch])
    tabla_principal.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(Paragraph("Datos principales", estilos["Heading3"]))
    elementos.append(tabla_principal)
    elementos.append(Spacer(1, 18))

    datos_ubicacion = [
        ["Campo", "Valor"],
        ["Archivador", valor_pdf(ubicacion.archivador if ubicacion else None)],
        ["SICOIN", valor_pdf(ubicacion.sicoin if ubicacion else None)],
        ["Estante", valor_pdf(ubicacion.estante if ubicacion else None)],
        ["Caja", valor_pdf(ubicacion.caja if ubicacion else None)],
        ["Módulo", valor_pdf(ubicacion.modulo if ubicacion else None)],
        ["Posición", valor_pdf(ubicacion.posicion if ubicacion else None)],
    ]

    tabla_ubicacion = Table(datos_ubicacion, colWidths=[2.2 * inch, 4.8 * inch])
    tabla_ubicacion.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(Paragraph("Ubicación física", estilos["Heading3"]))
    elementos.append(tabla_ubicacion)
    elementos.append(Spacer(1, 18))

    elementos.append(Paragraph("Observaciones", estilos["Heading3"]))
    elementos.append(Paragraph(valor_pdf(expediente.observaciones), estilos["Normal"]))
    elementos.append(Spacer(1, 18))

    elementos.append(Paragraph(
        "Generado desde SICODE-UCT para control interno institucional.",
        estilos["Italic"],
    ))

    doc.build(elementos)
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_EXPEDIENTE_PDF",
        modulo="Reportes",
        descripcion=f"Se exportó PDF del expediente No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    nombre_archivo = f"expediente_{expediente.no_sp}_sicode_uct.pdf".replace(" ", "_")

    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )


@expedientes_bp.route("/expedientes/<int:expediente_id>/reporte-completo/pdf")
@login_required
def reporte_completo_pdf(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    ubicacion = UbicacionFisica.query.filter_by(expediente_id=expediente.id).first()

    documentos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id)
        .order_by(DocumentoExpediente.folio_inicio.asc(), DocumentoExpediente.id.asc())
        .all()
    )

    alertas = (
        Alerta.query
        .filter_by(expediente_id=expediente.id)
        .order_by(Alerta.creado_en.desc())
        .all()
    )

    prestamos = (
        PrestamoExpediente.query
        .filter_by(expediente_id=expediente.id)
        .order_by(PrestamoExpediente.fecha_prestamo.desc())
        .all()
    )

    eventos_bitacora = (
        Bitacora.query
        .filter_by(expediente_id=expediente.id)
        .order_by(Bitacora.creado_en.desc())
        .limit(20)
        .all()
    )

    def limpiar_texto(valor):
        if valor is None or valor == "":
            return "Sin dato"

        texto = str(valor)
        texto = texto.encode("latin-1", "replace").decode("latin-1")
        return escape(texto)

    def p(valor):
        return Paragraph(limpiar_texto(valor), estilos["Normal"])

    def fecha_dt(valor):
        if not valor:
            return "Sin dato"
        return valor.strftime("%d/%m/%Y %H:%M")

    def fecha_d(valor):
        if not valor:
            return "Sin dato"
        return valor.strftime("%d/%m/%Y")

    def crear_tabla(datos, anchos):
        tabla = Table(datos, colWidths=anchos, repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        return tabla

    archivo_pdf = BytesIO()

    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=letter,
        rightMargin=34,
        leftMargin=34,
        topMargin=34,
        bottomMargin=34,
    )

    estilos = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("SICODE-UCT", estilos["Title"]))
    elementos.append(Paragraph("Reporte completo administrativo del expediente", estilos["Heading2"]))
    elementos.append(Spacer(1, 10))

    elementos.append(Paragraph(
        "Este reporte contiene metadatos administrativos, ubicacion fisica, foliacion, alertas, "
        "prestamos, devoluciones y bitacora relacionada. No contiene documentos sensibles ni copias completas del expediente.",
        estilos["Normal"],
    ))

    elementos.append(Spacer(1, 16))

    datos_expediente = [
        ["Campo", "Valor"],
        ["Codigo interno", p(expediente.codigo_interno)],
        ["No. de SP", p(expediente.no_sp)],
        ["Nombre referencia", p(expediente.nombre_referencia)],
        ["Estado administrativo", p(expediente.estado_administrativo)],
        ["Estado fisico/documental", p(expediente.estado_fisico_documental)],
        ["Activo", p("Si" if expediente.activo else "No")],
        ["Fecha de creacion", p(fecha_dt(expediente.creado_en))],
        ["Ultima actualizacion", p(fecha_dt(expediente.actualizado_en))],
        ["Observaciones", p(expediente.observaciones)],
    ]

    elementos.append(Paragraph("1. Datos principales del expediente", estilos["Heading3"]))
    elementos.append(crear_tabla(datos_expediente, [2.2 * inch, 4.8 * inch]))
    elementos.append(Spacer(1, 14))

    datos_ubicacion = [
        ["Campo", "Valor"],
        ["Archivador", p(ubicacion.archivador if ubicacion else None)],
        ["SICOIN", p(ubicacion.sicoin if ubicacion else None)],
        ["Estante", p(ubicacion.estante if ubicacion else None)],
        ["Caja", p(ubicacion.caja if ubicacion else None)],
        ["Modulo", p(ubicacion.modulo if ubicacion else None)],
        ["Posicion", p(ubicacion.posicion if ubicacion else None)],
        ["Observaciones ubicacion", p(ubicacion.observaciones if ubicacion else None)],
    ]

    elementos.append(Paragraph("2. Ubicacion fisica", estilos["Heading3"]))
    elementos.append(crear_tabla(datos_ubicacion, [2.2 * inch, 4.8 * inch]))
    elementos.append(Spacer(1, 14))

    total_documentos_activos = sum(1 for documento in documentos if documento.activo)
    total_folios_activos = sum((documento.total_folios or 0) for documento in documentos if documento.activo)
    alertas_abiertas = sum(1 for alerta in alertas if alerta.estado in ["Abierta", "En revisión"])
    prestamos_activos = sum(1 for prestamo in prestamos if prestamo.estado == "En préstamo")

    resumen = [
        ["Indicador", "Valor"],
        ["Documentos activos", p(total_documentos_activos)],
        ["Total folios activos registrados", p(total_folios_activos)],
        ["Total alertas relacionadas", p(len(alertas))],
        ["Alertas abiertas o en revision", p(alertas_abiertas)],
        ["Total prestamos registrados", p(len(prestamos))],
        ["Prestamos activos", p(prestamos_activos)],
        ["Eventos de bitacora incluidos", p(len(eventos_bitacora))],
    ]

    elementos.append(Paragraph("3. Resumen operativo", estilos["Heading3"]))
    elementos.append(crear_tabla(resumen, [3.2 * inch, 3.8 * inch]))
    elementos.append(PageBreak())

    elementos.append(Paragraph("4. Indice documental y foliacion", estilos["Heading3"]))

    datos_documentos = [["Documento", "Tipo", "Folios", "Total", "Estado", "Activo"]]

    for documento in documentos:
        rango_folios = f"{documento.folio_inicio} - {documento.folio_fin}"
        datos_documentos.append([
            p(documento.nombre_documento),
            p(documento.tipo_documento),
            p(rango_folios),
            p(documento.total_folios),
            p(documento.estado_revision),
            p("Si" if documento.activo else "No"),
        ])

    if len(datos_documentos) == 1:
        datos_documentos.append([p("Sin documentos registrados"), p(""), p(""), p(""), p(""), p("")])

    elementos.append(crear_tabla(
        datos_documentos,
        [2.0 * inch, 1.0 * inch, 1.0 * inch, 0.7 * inch, 1.5 * inch, 0.8 * inch],
    ))

    elementos.append(Spacer(1, 16))
    elementos.append(Paragraph("5. Alertas e incidentes relacionados", estilos["Heading3"]))

    datos_alertas = [["Fecha", "Tipo", "Gravedad", "Estado", "Titulo"]]

    for alerta in alertas:
        datos_alertas.append([
            p(fecha_dt(alerta.creado_en)),
            p(alerta.tipo_alerta),
            p(alerta.gravedad),
            p(alerta.estado),
            p(alerta.titulo),
        ])

    if len(datos_alertas) == 1:
        datos_alertas.append([p("Sin alertas registradas"), p(""), p(""), p(""), p("")])

    elementos.append(crear_tabla(
        datos_alertas,
        [1.3 * inch, 1.3 * inch, 0.9 * inch, 1.0 * inch, 2.5 * inch],
    ))

    elementos.append(PageBreak())
    elementos.append(Paragraph("6. Prestamos y devoluciones", estilos["Heading3"]))

    datos_prestamos = [["Numero control", "Solicitante", "Fecha prestamo", "Fecha estimada", "Fecha real", "Estado"]]

    for prestamo in prestamos:
        datos_prestamos.append([
            p(prestamo.numero_control),
            p(prestamo.solicitante),
            p(fecha_dt(prestamo.fecha_prestamo)),
            p(fecha_d(prestamo.fecha_estimada_devolucion)),
            p(fecha_dt(prestamo.fecha_real_devolucion) if prestamo.fecha_real_devolucion else "Pendiente"),
            p(prestamo.estado),
        ])

    if len(datos_prestamos) == 1:
        datos_prestamos.append([p("Sin prestamos registrados"), p(""), p(""), p(""), p(""), p("")])

    elementos.append(crear_tabla(
        datos_prestamos,
        [1.6 * inch, 1.4 * inch, 1.2 * inch, 1.1 * inch, 1.1 * inch, 0.9 * inch],
    ))

    elementos.append(Spacer(1, 16))
    elementos.append(Paragraph("7. Ultimos eventos de bitacora relacionados", estilos["Heading3"]))

    datos_bitacora = [["Fecha", "Accion", "Modulo", "Descripcion"]]

    for evento in eventos_bitacora:
        datos_bitacora.append([
            p(fecha_dt(evento.creado_en)),
            p(evento.accion),
            p(evento.modulo),
            p(evento.descripcion),
        ])

    if len(datos_bitacora) == 1:
        datos_bitacora.append([p("Sin eventos registrados"), p(""), p(""), p("")])

    elementos.append(crear_tabla(
        datos_bitacora,
        [1.3 * inch, 1.5 * inch, 1.1 * inch, 3.1 * inch],
    ))

    elementos.append(Spacer(1, 18))
    elementos.append(Paragraph(
        "Reporte generado desde SICODE-UCT para control interno institucional.",
        estilos["Italic"],
    ))

    doc.build(elementos)
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_REPORTE_COMPLETO_EXPEDIENTE_PDF",
        modulo="Reportes",
        descripcion=f"Se genero reporte completo PDF del expediente No. de SP {expediente.no_sp}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
    nombre_archivo = f"reporte_completo_expediente_{no_sp_limpio}.pdf"

    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )

