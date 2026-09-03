from datetime import datetime
from io import BytesIO
from uuid import uuid4
from xml.sax.saxutils import escape

from flask import flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_

from app import db
from app.models.cola_recepcion import ColaRecepcionDocumental
from app.routes.admin import admin_bp, admin_required
from app.services.bitacora_service import registrar_bitacora


ACCIONES_COLA_RECEPCION = (
    ("ARCHIVAR", "Archivar"),
    ("REGISTRAR_SICODE", "Registrar en SICODE"),
    ("ORDENAR_CARATULAS", "Ordenar carátulas"),
    ("FOLIAR", "Foliar"),
    ("ESCANEAR", "Escanear"),
    ("REVISAR_FILE_SERVER", "Revisar en File Server"),
    ("CORROBORAR", "Corroborar"),
    ("RECTIFICAR", "Rectificar"),
)
ACCIONES_MAPA = dict(ACCIONES_COLA_RECEPCION)
ESTADOS_COLA = (
    ("PENDIENTE", "Pendiente"),
    ("EN_PROCESO", "En proceso"),
    ("COMPLETADO", "Completado"),
)


def _limpiar(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def _parsear_fecha_hora(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _acciones_formulario():
    permitidas = set(ACCIONES_MAPA)
    return [accion for accion in request.form.getlist("acciones") if accion in permitidas]


def _datos_item(item):
    return {
        "correlativo": item.correlativo,
        "recibido_en": item.recibido_en.isoformat(timespec="minutes") if item.recibido_en else None,
        "recibido_de": item.recibido_de,
        "descripcion": item.descripcion,
        "ubicacion_temporal": item.ubicacion_temporal,
        "acciones": list(item.acciones or []),
        "observaciones": item.observaciones,
        "estado": item.estado,
        "completado_en": item.completado_en.isoformat(timespec="minutes") if item.completado_en else None,
    }


def _registrar_bitacora_cola(accion, item, descripcion, anteriores=None):
    registrar_bitacora(
        accion=accion,
        modulo="Administración",
        descripcion=descripcion,
        usuario_id=current_user.id,
        entidad="ColaRecepcionDocumental",
        entidad_id=item.id,
        datos_anteriores=anteriores,
        datos_posteriores=_datos_item(item),
        commit=False,
    )


def _validar_campos():
    recibido_en = _parsear_fecha_hora(request.form.get("recibido_en"))
    recibido_de = _limpiar(request.form.get("recibido_de"))
    descripcion = _limpiar(request.form.get("descripcion"))
    ubicacion_temporal = _limpiar(request.form.get("ubicacion_temporal"))
    observaciones = _limpiar(request.form.get("observaciones"))
    acciones = _acciones_formulario()

    errores = []
    if not recibido_en:
        errores.append("Indique una fecha y hora de recepción válidas.")
    if not recibido_de:
        errores.append("Indique de quién se recibió el material.")
    if not descripcion:
        errores.append("Agregue una descripción breve de lo recibido.")
    if not acciones:
        errores.append("Seleccione por lo menos una tarea pendiente.")

    return {
        "recibido_en": recibido_en,
        "recibido_de": recibido_de,
        "descripcion": descripcion,
        "ubicacion_temporal": ubicacion_temporal,
        "observaciones": observaciones,
        "acciones": acciones,
    }, errores


@admin_bp.route("/cola-recepcion", methods=["GET", "POST"])
@login_required
@admin_required
def cola_recepcion():
    if request.method == "POST":
        datos, errores = _validar_campos()
        if errores:
            for error in errores:
                flash(error, "danger")
        else:
            item = ColaRecepcionDocumental(
                correlativo=f"TEMP-{uuid4().hex[:20]}",
                recibido_en=datos["recibido_en"],
                recibido_de=datos["recibido_de"],
                descripcion=datos["descripcion"],
                ubicacion_temporal=datos["ubicacion_temporal"],
                acciones=datos["acciones"],
                observaciones=datos["observaciones"],
                estado="PENDIENTE",
                usuario_id=current_user.id,
            )
            db.session.add(item)
            db.session.flush()
            item.correlativo = f"CRD-{item.recibido_en.year}-{item.id:05d}"

            _registrar_bitacora_cola(
                "REGISTRAR_COLA_RECEPCION",
                item,
                (
                    f"Se registró {item.correlativo} en la cola de recepción documental, "
                    f"recibido de {item.recibido_de}."
                ),
            )
            db.session.commit()
            flash(
                f"{item.correlativo} fue agregado a la cola de pendientes.",
                "success",
            )
            return redirect(url_for("admin.cola_recepcion"))

    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "ACTIVOS").strip().upper()
    pagina = max(request.args.get("page", 1, type=int), 1)

    consulta = ColaRecepcionDocumental.query
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(or_(
            ColaRecepcionDocumental.correlativo.ilike(patron),
            ColaRecepcionDocumental.recibido_de.ilike(patron),
            ColaRecepcionDocumental.descripcion.ilike(patron),
            ColaRecepcionDocumental.ubicacion_temporal.ilike(patron),
            ColaRecepcionDocumental.observaciones.ilike(patron),
        ))

    if estado == "ACTIVOS":
        consulta = consulta.filter(ColaRecepcionDocumental.estado != "COMPLETADO")
    elif estado in ColaRecepcionDocumental.ESTADOS:
        consulta = consulta.filter(ColaRecepcionDocumental.estado == estado)
    elif estado != "TODOS":
        estado = "ACTIVOS"
        consulta = consulta.filter(ColaRecepcionDocumental.estado != "COMPLETADO")

    paginacion = consulta.order_by(
        ColaRecepcionDocumental.recibido_en.asc(),
        ColaRecepcionDocumental.id.asc(),
    ).paginate(page=pagina, per_page=40, error_out=False)

    pendientes = ColaRecepcionDocumental.query.filter_by(estado="PENDIENTE").count()
    en_proceso = ColaRecepcionDocumental.query.filter_by(estado="EN_PROCESO").count()
    completados = ColaRecepcionDocumental.query.filter_by(estado="COMPLETADO").count()
    ahora = datetime.now()

    return render_template(
        "admin/cola_recepcion.html",
        items=paginacion.items,
        paginacion=paginacion,
        acciones=ACCIONES_COLA_RECEPCION,
        acciones_mapa=ACCIONES_MAPA,
        estados=ESTADOS_COLA,
        q=q,
        estado=estado,
        pendientes=pendientes,
        en_proceso=en_proceso,
        completados=completados,
        ahora=ahora,
        fecha_hora_default=ahora.strftime("%Y-%m-%dT%H:%M"),
    )


@admin_bp.route("/cola-recepcion/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_cola_recepcion(item_id):
    item = ColaRecepcionDocumental.query.get_or_404(item_id)

    if request.method == "POST":
        datos, errores = _validar_campos()
        if errores:
            for error in errores:
                flash(error, "danger")
        else:
            anteriores = _datos_item(item)
            item.recibido_en = datos["recibido_en"]
            item.recibido_de = datos["recibido_de"]
            item.descripcion = datos["descripcion"]
            item.ubicacion_temporal = datos["ubicacion_temporal"]
            item.acciones = datos["acciones"]
            item.observaciones = datos["observaciones"]

            _registrar_bitacora_cola(
                "EDITAR_COLA_RECEPCION",
                item,
                f"Se actualizó el control {item.correlativo} de la cola de recepción.",
                anteriores=anteriores,
            )
            db.session.commit()
            flash(f"{item.correlativo} fue actualizado.", "success")
            return redirect(url_for("admin.cola_recepcion"))

    return render_template(
        "admin/cola_recepcion_editar.html",
        item=item,
        acciones=ACCIONES_COLA_RECEPCION,
    )


@admin_bp.route("/cola-recepcion/<int:item_id>/estado", methods=["POST"])
@login_required
@admin_required
def cambiar_estado_cola_recepcion(item_id):
    item = ColaRecepcionDocumental.query.get_or_404(item_id)
    nuevo_estado = (request.form.get("estado") or "").strip().upper()

    if nuevo_estado not in ColaRecepcionDocumental.ESTADOS:
        flash("Estado no válido para la cola de recepción.", "danger")
        return redirect(url_for("admin.cola_recepcion"))

    anteriores = _datos_item(item)
    item.estado = nuevo_estado
    item.completado_en = datetime.now() if nuevo_estado == "COMPLETADO" else None

    _registrar_bitacora_cola(
        "CAMBIAR_ESTADO_COLA_RECEPCION",
        item,
        f"{item.correlativo} cambió a estado {item.estado_legible}.",
        anteriores=anteriores,
    )
    db.session.commit()
    flash(f"{item.correlativo}: {item.estado_legible}.", "success")
    return redirect(request.referrer or url_for("admin.cola_recepcion"))


def _p(texto, estilo):
    return Paragraph(escape(str(texto or "—")).replace("\n", "<br/>"), estilo)


@admin_bp.route("/cola-recepcion/<int:item_id>/pdf")
@login_required
@admin_required
def pdf_cola_recepcion(item_id):
    item = ColaRecepcionDocumental.query.get_or_404(item_id)

    archivo = BytesIO()
    doc = SimpleDocTemplate(
        archivo,
        pagesize=letter,
        leftMargin=30,
        rightMargin=30,
        topMargin=28,
        bottomMargin=28,
        title=f"Control {item.correlativo}",
        author="SICODE-UCT",
    )
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle(
        "NormalCola",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )
    centro = ParagraphStyle(
        "CentroCola",
        parent=normal,
        alignment=1,
    )
    titulo = ParagraphStyle(
        "TituloCola",
        parent=centro,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
    )
    correlativo = ParagraphStyle(
        "CorrelativoCola",
        parent=centro,
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
    )

    elementos = [
        Paragraph("<b>SICODE-UCT</b>", centro),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", centro),
        Paragraph("CONTROL INTERNO DE ADMINISTRACIÓN", centro),
        Spacer(1, 5),
        Paragraph("HOJA DE RECEPCIÓN PENDIENTE DE PROCESAMIENTO", titulo),
        Spacer(1, 5),
        Paragraph(escape(item.correlativo), correlativo),
        Spacer(1, 8),
    ]

    fecha_recepcion = item.recibido_en.strftime("%d/%m/%Y %H:%M") if item.recibido_en else "—"
    tabla_datos = Table(
        [
            [Paragraph("<b>Fecha y hora de recepción</b>", normal), _p(fecha_recepcion, normal)],
            [Paragraph("<b>Recibido de</b>", normal), _p(item.recibido_de, normal)],
            [Paragraph("<b>Descripción breve</b>", normal), _p(item.descripcion, normal)],
            [Paragraph("<b>Ubicación temporal</b>", normal), _p(item.ubicacion_temporal, normal)],
            [Paragraph("<b>Estado</b>", normal), _p(item.estado_legible, normal)],
        ],
        colWidths=[2.1 * inch, 5.0 * inch],
    )
    tabla_datos.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.extend([tabla_datos, Spacer(1, 10)])

    seleccionadas = set(item.acciones or [])
    filas_tareas = []
    for codigo, etiqueta in ACCIONES_COLA_RECEPCION:
        marca = "[X]" if codigo in seleccionadas else "[ ]"
        filas_tareas.append([_p(f"{marca} {etiqueta}", normal)])
    tabla_tareas = Table(
        [[Paragraph("<b>TAREAS PENDIENTES / ACCIONES A REALIZAR</b>", normal)]] + filas_tareas,
        colWidths=[7.1 * inch],
    )
    tabla_tareas.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([tabla_tareas, Spacer(1, 10)])

    observaciones = Table(
        [
            [Paragraph("<b>OBSERVACIONES</b>", normal)],
            [_p(item.observaciones or "Sin observaciones adicionales.", normal)],
        ],
        colWidths=[7.1 * inch],
    )
    observaciones.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.extend([observaciones, Spacer(1, 12)])

    cierre = item.completado_en.strftime("%d/%m/%Y %H:%M") if item.completado_en else "________________________"
    pie = Table(
        [
            [_p(f"Registrado por: {item.usuario.nombre if item.usuario else current_user.nombre}", normal),
             _p(f"Procesado/finalizado: {cierre}", normal)],
            [_p("Firma / control: ______________________________", normal),
             _p("Observación final: ____________________________", normal)],
        ],
        colWidths=[3.55 * inch, 3.55 * inch],
    )
    pie.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elementos.extend([
        pie,
        Spacer(1, 9),
        Paragraph(
            "Control temporal administrativo. Esta hoja no sustituye el registro formal del expediente "
            "ni almacena copias de documentos; identifica material recibido que aún requiere procesamiento.",
            normal,
        ),
    ])

    doc.build(elementos)
    archivo.seek(0)

    registrar_bitacora(
        accion="GENERAR_PDF_COLA_RECEPCION",
        modulo="Administración",
        descripcion=f"Se generó el PDF de control {item.correlativo}.",
        usuario_id=current_user.id,
        entidad="ColaRecepcionDocumental",
        entidad_id=item.id,
        datos_posteriores=_datos_item(item),
        commit=True,
    )

    return send_file(
        archivo,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{item.correlativo}.pdf",
    )
