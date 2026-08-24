from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import cast, or_

from app import db
from app.forms.soporte_tecnico_form import (
    ESTADOS,
    GESTION_USUARIO,
    HARDWARE,
    INSTALACION,
    REVISION,
    SOFTWARE,
    TIPOS_EQUIPO,
    TIPOS_SERVICIO,
    TRASLADO,
    SoporteTecnicoForm,
)
from app.models.coordinacion import ActividadCoordinacion, RegistroCoordinacion
from app.models.soporte_tecnico import ServicioSoporteTecnico
from app.services.bitacora_service import registrar_bitacora


soporte_tecnico_bp = Blueprint(
    "soporte_tecnico",
    __name__,
    url_prefix="/coordinacion/soporte-tecnico",
)


CATALOGOS_PDF = {
    "tipos_servicio": TIPOS_SERVICIO,
    "gestion_usuario_detalles": GESTION_USUARIO,
    "hardware_detalles": HARDWARE,
    "software_detalles": SOFTWARE,
    "instalacion_detalles": INSTALACION,
    "traslado_detalles": TRASLADO,
    "revision_detalles": REVISION,
}


def _limpiar(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def _estado_registro(estado_final):
    return "Completo" if estado_final == "RESUELTO" else "Información pendiente"


def _numero_boleta(registro_id, fecha_hora):
    return f"BST-{fecha_hora.year}-{registro_id:05d}"


def _datos_bitacora(boleta):
    return {
        "numero_boleta": boleta.numero_boleta,
        "fecha_hora_solicitud": boleta.fecha_hora_solicitud.isoformat() if boleta.fecha_hora_solicitud else None,
        "usuario_solicitante": boleta.usuario_solicitante,
        "coordinacion_area": boleta.coordinacion_area,
        "tecnico_asignado": boleta.tecnico_asignado,
        "tipos_servicio": list(boleta.tipos_servicio or []),
        "estado_final": boleta.estado_final,
        "seguimiento": boleta.seguimiento,
        "tipo_equipo": boleta.tipo_equipo,
        "inventario": boleta.inventario,
        "numero_serie": boleta.numero_serie,
    }


def _aplicar_formulario(boleta, form):
    boleta.fecha_hora_solicitud = form.fecha_hora_solicitud.data
    boleta.usuario_solicitante = form.usuario_solicitante.data.strip()
    boleta.puesto_cargo = _limpiar(form.puesto_cargo.data)
    boleta.coordinacion_area = form.coordinacion_area.data.strip()
    boleta.tecnico_asignado = form.tecnico_asignado.data.strip()

    boleta.tipos_servicio = list(form.tipos_servicio.data or [])
    boleta.gestion_usuario_detalles = list(form.gestion_usuario_detalles.data or [])
    boleta.hardware_detalles = list(form.hardware_detalles.data or [])
    boleta.software_detalles = list(form.software_detalles.data or [])
    boleta.instalacion_detalles = list(form.instalacion_detalles.data or [])
    boleta.traslado_detalles = list(form.traslado_detalles.data or [])
    boleta.revision_detalles = list(form.revision_detalles.data or [])
    boleta.otro_servicio_ti = _limpiar(form.otro_servicio_ti.data)
    boleta.otro_instalacion = _limpiar(form.otro_instalacion.data)
    boleta.otro_traslado = _limpiar(form.otro_traslado.data)
    boleta.otro_revision = _limpiar(form.otro_revision.data)

    boleta.tipo_equipo = _limpiar(form.tipo_equipo.data)
    boleta.tipo_equipo_otro = _limpiar(form.tipo_equipo_otro.data)
    boleta.marca_modelo = _limpiar(form.marca_modelo.data)
    boleta.numero_serie = _limpiar(form.numero_serie.data)
    boleta.inventario = _limpiar(form.inventario.data)
    boleta.ip_nombre_equipo = _limpiar(form.ip_nombre_equipo.data)

    boleta.descripcion_solicitud = form.descripcion_solicitud.data.strip()
    boleta.diagnostico_trabajo = _limpiar(form.diagnostico_trabajo.data)
    boleta.estado_final = form.estado_final.data
    boleta.seguimiento = form.seguimiento.data == "SI"
    boleta.fecha_hora_cierre = form.fecha_hora_cierre.data
    if boleta.estado_final != "PENDIENTE" and not boleta.fecha_hora_cierre:
        boleta.fecha_hora_cierre = datetime.now().replace(second=0, microsecond=0)
    boleta.tiempo_empleado = _limpiar(form.tiempo_empleado.data)
    boleta.observaciones_cierre = _limpiar(form.observaciones_cierre.data)

    boleta.nombre_firma_usuario = _limpiar(form.nombre_firma_usuario.data)
    boleta.fecha_firma_usuario = form.fecha_firma_usuario.data
    boleta.nombre_firma_tecnico = _limpiar(form.nombre_firma_tecnico.data)
    boleta.fecha_firma_tecnico = form.fecha_firma_tecnico.data


def _preparar_formulario_get(form, boleta=None):
    if boleta is None:
        form.fecha_hora_solicitud.data = datetime.now().replace(second=0, microsecond=0)
        form.tecnico_asignado.data = current_user.nombre
        form.nombre_firma_tecnico.data = current_user.nombre
        form.estado_final.data = "PENDIENTE"
        form.seguimiento.data = "NO"
        return

    form.seguimiento.data = "SI" if boleta.seguimiento else "NO"


@soporte_tecnico_bp.route("")
@soporte_tecnico_bp.route("/")
@login_required
def listado():
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "").strip().upper()
    tipo = request.args.get("tipo", "").strip().upper()
    pagina = request.args.get("page", 1, type=int)

    consulta = ServicioSoporteTecnico.query
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(or_(
            ServicioSoporteTecnico.numero_boleta.ilike(patron),
            ServicioSoporteTecnico.usuario_solicitante.ilike(patron),
            ServicioSoporteTecnico.puesto_cargo.ilike(patron),
            ServicioSoporteTecnico.coordinacion_area.ilike(patron),
            ServicioSoporteTecnico.tecnico_asignado.ilike(patron),
            ServicioSoporteTecnico.descripcion_solicitud.ilike(patron),
            ServicioSoporteTecnico.numero_serie.ilike(patron),
            ServicioSoporteTecnico.inventario.ilike(patron),
            ServicioSoporteTecnico.ip_nombre_equipo.ilike(patron),
        ))
    if estado:
        consulta = consulta.filter(ServicioSoporteTecnico.estado_final == estado)
    if tipo:
        # JSON contiene una lista de códigos. En PostgreSQL/SQLite el cast a
        # texto permite el filtro de interfaz sin amarrar la consulta a un
        # operador exclusivo de un motor.
        consulta = consulta.filter(cast(ServicioSoporteTecnico.tipos_servicio, db.String).ilike(f'%"{tipo}"%'))

    paginacion = consulta.order_by(
        ServicioSoporteTecnico.fecha_hora_solicitud.desc(),
        ServicioSoporteTecnico.id.desc(),
    ).paginate(page=max(pagina, 1), per_page=50, error_out=False)

    total = ServicioSoporteTecnico.query.count()
    pendientes = ServicioSoporteTecnico.query.filter(ServicioSoporteTecnico.estado_final != "RESUELTO").count()
    resueltos = ServicioSoporteTecnico.query.filter_by(estado_final="RESUELTO").count()
    seguimiento = ServicioSoporteTecnico.query.filter_by(seguimiento=True).count()
    registros_soporte = db.session.query(ServicioSoporteTecnico.registro_id)
    historicos = RegistroCoordinacion.query.filter(
        RegistroCoordinacion.tipo == "ACTIVIDAD",
        ~RegistroCoordinacion.id.in_(registros_soporte),
    ).count()

    return render_template(
        "soporte_tecnico/listado.html",
        boletas=paginacion.items,
        paginacion=paginacion,
        q=q,
        estado=estado,
        tipo=tipo,
        estados=ESTADOS,
        tipos_servicio=TIPOS_SERVICIO,
        total=total,
        pendientes=pendientes,
        resueltos=resueltos,
        seguimiento=seguimiento,
        historicos=historicos,
    )


@soporte_tecnico_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    form = SoporteTecnicoForm()
    if request.method == "GET":
        _preparar_formulario_get(form)

    if form.validate_on_submit():
        registro = RegistroCoordinacion(
            tipo="ACTIVIDAD",
            fecha_recepcion=form.fecha_hora_solicitud.data.date(),
            usuario_id=current_user.id,
            usuario_origen=current_user.nombre,
            estado=_estado_registro(form.estado_final.data),
            observaciones=_limpiar(form.observaciones_cierre.data),
            origen_registro="MANUAL",
        )
        db.session.add(registro)
        db.session.flush()

        actividad = ActividadCoordinacion(
            registro_id=registro.id,
            tipo_actividad="SOPORTE TI",
            area_apoyo=form.coordinacion_area.data.strip(),
            descripcion=form.descripcion_solicitud.data.strip(),
        )
        boleta = ServicioSoporteTecnico(
            registro_id=registro.id,
            numero_boleta=_numero_boleta(registro.id, form.fecha_hora_solicitud.data),
            fecha_hora_solicitud=form.fecha_hora_solicitud.data,
            usuario_solicitante=form.usuario_solicitante.data.strip(),
            coordinacion_area=form.coordinacion_area.data.strip(),
            tecnico_asignado=form.tecnico_asignado.data.strip(),
            descripcion_solicitud=form.descripcion_solicitud.data.strip(),
        )
        _aplicar_formulario(boleta, form)
        db.session.add_all([actividad, boleta])
        db.session.flush()

        registrar_bitacora(
            accion="REGISTRAR_SOPORTE_TECNICO",
            modulo="Coordinación",
            descripcion=(
                f"Se registró la boleta de soporte {boleta.numero_boleta} para "
                f"{boleta.usuario_solicitante} ({boleta.coordinacion_area})."
            ),
            usuario_id=current_user.id,
            entidad="ServicioSoporteTecnico",
            entidad_id=boleta.id,
            datos_posteriores=_datos_bitacora(boleta),
            commit=False,
        )
        db.session.commit()
        flash(f"Boleta {boleta.numero_boleta} registrada correctamente.", "success")
        return redirect(url_for("soporte_tecnico.detalle", boleta_id=boleta.id))

    return render_template(
        "soporte_tecnico/formulario.html",
        form=form,
        boleta=None,
    )


@soporte_tecnico_bp.route("/boletas/<int:boleta_id>")
@login_required
def detalle(boleta_id):
    boleta = ServicioSoporteTecnico.query.get_or_404(boleta_id)
    return render_template(
        "soporte_tecnico/detalle.html",
        boleta=boleta,
        catalogos=CATALOGOS_PDF,
        tipos_equipo=dict(TIPOS_EQUIPO),
    )


@soporte_tecnico_bp.route("/boletas/<int:boleta_id>/editar", methods=["GET", "POST"])
@login_required
def editar(boleta_id):
    boleta = ServicioSoporteTecnico.query.get_or_404(boleta_id)
    form = SoporteTecnicoForm(obj=boleta)
    if request.method == "GET":
        _preparar_formulario_get(form, boleta)

    if form.validate_on_submit():
        anteriores = _datos_bitacora(boleta)
        _aplicar_formulario(boleta, form)

        registro = boleta.registro
        registro.fecha_recepcion = boleta.fecha_hora_solicitud.date()
        registro.estado = _estado_registro(boleta.estado_final)
        registro.observaciones = boleta.observaciones_cierre
        if registro.actividad_coordinacion:
            registro.actividad_coordinacion.tipo_actividad = "SOPORTE TI"
            registro.actividad_coordinacion.area_apoyo = boleta.coordinacion_area
            registro.actividad_coordinacion.descripcion = boleta.descripcion_solicitud

        registrar_bitacora(
            accion="EDITAR_SOPORTE_TECNICO",
            modulo="Coordinación",
            descripcion=(
                f"Se actualizó la boleta {boleta.numero_boleta}. "
                f"Estado: {boleta.estado_legible}."
            ),
            usuario_id=current_user.id,
            entidad="ServicioSoporteTecnico",
            entidad_id=boleta.id,
            datos_anteriores=anteriores,
            datos_posteriores=_datos_bitacora(boleta),
            commit=False,
        )
        db.session.commit()
        flash(f"Boleta {boleta.numero_boleta} actualizada.", "success")
        return redirect(url_for("soporte_tecnico.detalle", boleta_id=boleta.id))

    return render_template(
        "soporte_tecnico/formulario.html",
        form=form,
        boleta=boleta,
    )


def _valor(valor, sin_dato="—"):
    if valor is None or valor == "":
        return sin_dato
    return escape(str(valor))


def _marcas(seleccionados, opciones, estilo):
    seleccion = set(seleccionados or [])
    lineas = []
    for codigo, etiqueta in opciones:
        marca = "[X]" if codigo in seleccion else "[ ]"
        lineas.append(f"{marca} {_valor(etiqueta)}")
    return Paragraph("<br/>".join(lineas), estilo)


def _tabla_seccion(titulo, filas, anchos, estilo_encabezado=None):
    datos = [[Paragraph(f"<b>{escape(titulo)}</b>", estilo_encabezado)]] if estilo_encabezado else [[titulo]]
    datos.extend(filas)
    tabla = Table(datos, colWidths=anchos, repeatRows=0)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabla


@soporte_tecnico_bp.route("/boletas/<int:boleta_id>/pdf")
@login_required
def generar_pdf(boleta_id):
    boleta = ServicioSoporteTecnico.query.get_or_404(boleta_id)

    archivo = BytesIO()
    doc = SimpleDocTemplate(
        archivo,
        pagesize=letter,
        leftMargin=24,
        rightMargin=24,
        topMargin=22,
        bottomMargin=22,
    )
    estilos = getSampleStyleSheet()
    mini = ParagraphStyle(
        "MiniSoporte",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=6.7,
        leading=8.2,
        spaceAfter=0,
    )
    mini_centro = ParagraphStyle(
        "MiniCentro",
        parent=mini,
        alignment=1,
    )
    titulo = ParagraphStyle(
        "TituloBoleta",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11,
        alignment=1,
    )

    elementos = [
        Paragraph("SICODE-UCT", mini_centro),
        Paragraph("COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS", mini_centro),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", mini_centro),
        Paragraph("BOLETA DE SERVICIO DE SOPORTE TÉCNICO", titulo),
        Spacer(1, 5),
    ]

    fecha = boleta.fecha_hora_solicitud
    cabecera = Table([
        [Paragraph(f"<b>No. de boleta:</b> {_valor(boleta.numero_boleta)}", mini),
         Paragraph(f"<b>Fecha:</b> {fecha.strftime('%d/%m/%Y') if fecha else '—'}", mini),
         Paragraph(f"<b>Hora:</b> {fecha.strftime('%H:%M') if fecha else '—'}", mini)],
    ], colWidths=[3.0 * inch, 2.0 * inch, 2.0 * inch])
    cabecera.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6b7280")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos.extend([cabecera, Spacer(1, 4)])

    elementos.append(_tabla_seccion(
        "1. DATOS DEL USUARIO Y UBICACIÓN",
        [
            [Paragraph(f"<b>Nombre del usuario:</b> {_valor(boleta.usuario_solicitante)}", mini),
             Paragraph(f"<b>Puesto / Cargo:</b> {_valor(boleta.puesto_cargo)}", mini)],
            [Paragraph(f"<b>Coordinación / Área:</b> {_valor(boleta.coordinacion_area)}", mini),
             Paragraph(f"<b>Técnico asignado:</b> {_valor(boleta.tecnico_asignado)}", mini)],
        ],
        [3.5 * inch, 3.5 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 3))

    elementos.append(_tabla_seccion(
        "2. TIPO DE SERVICIO SOLICITADO",
        [[_marcas(boleta.tipos_servicio, TIPOS_SERVICIO, mini)]],
        [7.0 * inch],
        mini,
    ))
    if boleta.otro_servicio_ti:
        elementos.append(Paragraph(f"<b>Otro servicio TI:</b> {_valor(boleta.otro_servicio_ti)}", mini))
    elementos.append(Spacer(1, 3))

    detalle_filas = [
        [Paragraph("<b>3.1 CREACIÓN / GESTIÓN DE USUARIO</b>", mini), _marcas(boleta.gestion_usuario_detalles, GESTION_USUARIO, mini)],
        [Paragraph("<b>3.2 MANTENIMIENTO DE HARDWARE</b>", mini), _marcas(boleta.hardware_detalles, HARDWARE, mini)],
        [Paragraph("<b>3.3 MANTENIMIENTO DE SOFTWARE</b>", mini), _marcas(boleta.software_detalles, SOFTWARE, mini)],
    ]
    elementos.append(_tabla_seccion(
        "3. DETALLE FUNCIONAL DEL SERVICIO",
        detalle_filas,
        [2.2 * inch, 4.8 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 3))

    seccion4 = [
        [Paragraph("<b>4.1 INSTALACIÓN</b>", mini), _marcas(boleta.instalacion_detalles, INSTALACION, mini)],
        [Paragraph("<b>4.2 TRASLADO</b>", mini), _marcas(boleta.traslado_detalles, TRASLADO, mini)],
        [Paragraph("<b>4.3 REVISIÓN</b>", mini), _marcas(boleta.revision_detalles, REVISION, mini)],
    ]
    elementos.append(_tabla_seccion(
        "4. INSTALACIÓN, TRASLADO Y REVISIÓN DE EQUIPO",
        seccion4,
        [2.2 * inch, 4.8 * inch],
        mini,
    ))
    extras = []
    if boleta.otro_instalacion:
        extras.append(f"Instalación: {_valor(boleta.otro_instalacion)}")
    if boleta.otro_traslado:
        extras.append(f"Traslado: {_valor(boleta.otro_traslado)}")
    if boleta.otro_revision:
        extras.append(f"Revisión: {_valor(boleta.otro_revision)}")
    if extras:
        elementos.append(Paragraph("<b>Otros:</b> " + " | ".join(extras), mini))
    elementos.append(Spacer(1, 3))

    tipo_equipo = dict(TIPOS_EQUIPO).get(boleta.tipo_equipo, boleta.tipo_equipo or "—")
    if boleta.tipo_equipo == "OTRO" and boleta.tipo_equipo_otro:
        tipo_equipo = f"Otro: {boleta.tipo_equipo_otro}"
    elementos.append(_tabla_seccion(
        "5. IDENTIFICACIÓN DEL EQUIPO",
        [
            [Paragraph(f"<b>Tipo:</b> {_valor(tipo_equipo)}", mini), Paragraph(f"<b>Marca / Modelo:</b> {_valor(boleta.marca_modelo)}", mini)],
            [Paragraph(f"<b>No. de serie:</b> {_valor(boleta.numero_serie)}", mini), Paragraph(f"<b>Inventario:</b> {_valor(boleta.inventario)}", mini)],
            [Paragraph(f"<b>IP / Nombre de equipo:</b> {_valor(boleta.ip_nombre_equipo)}", mini), Paragraph("", mini)],
        ],
        [3.5 * inch, 3.5 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 3))

    elementos.append(_tabla_seccion(
        "6. DESCRIPCIÓN DE LA SOLICITUD / FALLA REPORTADA",
        [[Paragraph(_valor(boleta.descripcion_solicitud), mini)]],
        [7.0 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 3))
    elementos.append(_tabla_seccion(
        "7. DIAGNÓSTICO Y TRABAJO REALIZADO",
        [[Paragraph(_valor(boleta.diagnostico_trabajo), mini)]],
        [7.0 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 3))

    cierre = boleta.fecha_hora_cierre.strftime("%d/%m/%Y %H:%M") if boleta.fecha_hora_cierre else "—"
    elementos.append(_tabla_seccion(
        "8. RESULTADO Y CIERRE DEL SERVICIO",
        [
            [Paragraph(f"<b>Estado final:</b> {_valor(boleta.estado_legible)}", mini),
             Paragraph(f"<b>Seguimiento:</b> {'Sí' if boleta.seguimiento else 'No'}", mini)],
            [Paragraph(f"<b>Fecha / hora cierre:</b> {cierre}", mini),
             Paragraph(f"<b>Tiempo empleado:</b> {_valor(boleta.tiempo_empleado)}", mini)],
            [Paragraph(f"<b>Observaciones:</b> {_valor(boleta.observaciones_cierre)}", mini), Paragraph("", mini)],
        ],
        [3.5 * inch, 3.5 * inch],
        mini,
    ))
    elementos.append(Spacer(1, 5))

    firma_usuario_fecha = boleta.fecha_firma_usuario.strftime("%d/%m/%Y") if boleta.fecha_firma_usuario else "____/____/________"
    firma_tecnico_fecha = boleta.fecha_firma_tecnico.strftime("%d/%m/%Y") if boleta.fecha_firma_tecnico else "____/____/________"
    firmas = Table([
        [Paragraph("<b>USUARIO / SOLICITANTE</b>", mini_centro), Paragraph("<b>TÉCNICO DE SOPORTE</b>", mini_centro)],
        [Paragraph(f"Nombre: {_valor(boleta.nombre_firma_usuario or boleta.usuario_solicitante)}", mini),
         Paragraph(f"Nombre: {_valor(boleta.nombre_firma_tecnico or boleta.tecnico_asignado)}", mini)],
        [Paragraph("Firma: ______________________________", mini), Paragraph("Firma: ______________________________", mini)],
        [Paragraph(f"Fecha: {firma_usuario_fecha}", mini), Paragraph(f"Fecha: {firma_tecnico_fecha}", mini)],
    ], colWidths=[3.5 * inch, 3.5 * inch])
    firmas.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos.extend([
        firmas,
        Spacer(1, 4),
        Paragraph(
            "Constancia administrativa generada por SICODE-UCT. La firma se realiza sobre la impresión. "
            "El sistema conserva metadatos de atención y no almacena contraseñas, archivos respaldados ni copias de documentos del usuario.",
            mini,
        ),
    ])

    doc.build(elementos)
    archivo.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_BOLETA_SOPORTE_PDF",
        modulo="Coordinación",
        descripcion=f"Se generó PDF de la boleta de soporte {boleta.numero_boleta}.",
        usuario_id=current_user.id,
        entidad="ServicioSoporteTecnico",
        entidad_id=boleta.id,
    )

    return send_file(
        archivo,
        as_attachment=True,
        download_name=f"boleta_soporte_{boleta.numero_boleta}.pdf",
        mimetype="application/pdf",
    )
