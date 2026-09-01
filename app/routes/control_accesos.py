from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_

from app import db
from app.models.control_acceso import AccesoCCT
from app.services.bitacora_service import registrar_bitacora


control_accesos_bp = Blueprint("control_accesos", __name__, url_prefix="/ca-cct")

MOTIVOS = [
    ("SERVICIO_TECNICO", "Servicio técnico"),
    ("VISITA_TECNICA", "Visita técnica"),
    ("AUDITORIA", "Auditoría"),
    ("OTRO", "Otro"),
]
MOTIVOS_VALIDOS = {codigo for codigo, _ in MOTIVOS}


def _normalizar_cui(valor):
    return "".join(caracter for caracter in str(valor or "") if caracter.isdigit())


def _datos_bitacora(acceso):
    cui = acceso.cui or ""
    return {
        "correlativo": acceso.correlativo,
        "nombre": acceso.nombre,
        "cui_final": cui[-4:] if cui else None,
        "motivo": acceso.motivo,
        "motivo_otro": acceso.motivo_otro,
        "fecha_hora_entrada": acceso.fecha_hora_entrada.isoformat() if acceso.fecha_hora_entrada else None,
    }


def _consulta_listado():
    q = request.args.get("q", "").strip()
    motivo = request.args.get("motivo", "").strip().upper()
    pagina = request.args.get("page", 1, type=int)

    consulta = AccesoCCT.query
    if q:
        patron = f"%{q}%"
        condiciones = [
            AccesoCCT.nombre.ilike(patron),
            AccesoCCT.cui.ilike(patron),
            AccesoCCT.motivo_otro.ilike(patron),
        ]
        q_mayus = q.upper()
        if q_mayus.startswith("CCT-"):
            try:
                condiciones.append(AccesoCCT.id == int(q_mayus.split("-", 1)[1]))
            except (TypeError, ValueError):
                pass
        consulta = consulta.filter(or_(*condiciones))
    if motivo in MOTIVOS_VALIDOS:
        consulta = consulta.filter(AccesoCCT.motivo == motivo)
    else:
        motivo = ""

    paginacion = consulta.order_by(
        AccesoCCT.fecha_hora_entrada.desc(),
        AccesoCCT.id.desc(),
    ).paginate(page=max(pagina, 1), per_page=40, error_out=False)
    return q, motivo, paginacion


def _render_inicio(form_data=None, errores=None, status=200):
    q, motivo, paginacion = _consulta_listado()
    hoy = datetime.now().date().isoformat()
    total = AccesoCCT.query.count()
    total_hoy = AccesoCCT.query.filter(db.func.date(AccesoCCT.fecha_hora_entrada) == hoy).count()
    return render_template(
        "control_accesos/inicio.html",
        accesos=paginacion.items,
        paginacion=paginacion,
        motivos=MOTIVOS,
        q=q,
        motivo_filtro=motivo,
        total=total,
        total_hoy=total_hoy,
        form_data=form_data or {},
        errores=errores or [],
    ), status


@control_accesos_bp.route("/", methods=["GET", "POST"])
@login_required
def inicio():
    if request.method == "GET":
        return _render_inicio()

    if not current_user.puede_modificar:
        abort(403)

    nombre = (request.form.get("nombre") or "").strip()
    cui = _normalizar_cui(request.form.get("cui"))
    motivo = (request.form.get("motivo") or "").strip().upper()
    motivo_otro = (request.form.get("motivo_otro") or "").strip()

    errores = []
    if not nombre:
        errores.append("Debe ingresar el nombre de la persona.")
    elif len(nombre) > 180:
        errores.append("El nombre no puede superar 180 caracteres.")
    if len(cui) != 13:
        errores.append("El CUI debe contener exactamente 13 dígitos.")
    if motivo not in MOTIVOS_VALIDOS:
        errores.append("Seleccione un motivo de ingreso válido.")
    if motivo == "OTRO" and not motivo_otro:
        errores.append("Describa el motivo cuando seleccione Otro.")
    if len(motivo_otro) > 240:
        errores.append("El motivo personalizado no puede superar 240 caracteres.")

    if errores:
        return _render_inicio(request.form, errores, status=400)

    acceso = AccesoCCT(
        nombre=nombre,
        cui=cui,
        motivo=motivo,
        motivo_otro=motivo_otro or None,
        fecha_hora_entrada=datetime.now().replace(microsecond=0),
        usuario_id=current_user.id,
    )
    db.session.add(acceso)
    db.session.flush()

    registrar_bitacora(
        accion="REGISTRAR_ACCESO_CCT",
        modulo="C.A CCT",
        descripcion=f"Se registró la entrada {acceso.correlativo} al Centro de Control Telemático.",
        usuario_id=current_user.id,
        entidad="AccesoCCT",
        entidad_id=acceso.id,
        datos_posteriores=_datos_bitacora(acceso),
        commit=False,
    )
    db.session.commit()

    flash(f"Entrada {acceso.correlativo} registrada. La boleta PDF está lista para imprimir.", "success")
    return redirect(url_for("control_accesos.pdf", acceso_id=acceso.id))


def _p(texto, estilo):
    return Paragraph(escape(str(texto or "")), estilo)


@control_accesos_bp.route("/<int:acceso_id>/pdf")
@login_required
def pdf(acceso_id):
    acceso = AccesoCCT.query.get_or_404(acceso_id)

    archivo = BytesIO()
    doc = SimpleDocTemplate(
        archivo,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle(
        "CA_Normal",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
    )
    centro = ParagraphStyle("CA_Centro", parent=normal, alignment=1)
    titulo = ParagraphStyle(
        "CA_Titulo",
        parent=centro,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        spaceAfter=2,
    )
    subtitulo = ParagraphStyle(
        "CA_Subtitulo",
        parent=centro,
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
    )
    pequeno = ParagraphStyle("CA_Pequeno", parent=normal, fontSize=8, leading=10)
    pequeno_centro = ParagraphStyle("CA_Pequeno_Centro", parent=pequeno, alignment=1)

    elementos = [
        Paragraph("SICODE-UCT", subtitulo),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", subtitulo),
        Paragraph("CONTROL DE ACCESOS AL CENTRO DE CONTROL TELEMÁTICO", titulo),
        Paragraph("C.A CCT", pequeno_centro),
        Spacer(1, 10),
    ]

    fecha = acceso.fecha_hora_entrada
    cabecera = Table(
        [[
            Paragraph(f"<b>Correlativo:</b> {escape(acceso.correlativo)}", normal),
            Paragraph(f"<b>Fecha:</b> {fecha.strftime('%d/%m/%Y')}", normal),
            Paragraph(f"<b>Hora de entrada:</b> {fecha.strftime('%H:%M:%S')}", normal),
        ]],
        colWidths=[2.45 * inch, 2.1 * inch, 2.35 * inch],
    )
    cabecera.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#1f2937")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elementos.extend([cabecera, Spacer(1, 14)])

    datos = Table([
        [Paragraph("<b>DATOS DE LA PERSONA</b>", normal), ""],
        [Paragraph("<b>Nombre completo</b>", normal), _p(acceso.nombre, normal)],
        [Paragraph("<b>CUI</b>", normal), _p(acceso.cui_formateado, normal)],
        [Paragraph("<b>Motivo de ingreso</b>", normal), _p(acceso.motivo_legible, normal)],
    ], colWidths=[1.7 * inch, 5.2 * inch])
    datos.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#1f2937")),
        ("INNERGRID", (0, 1), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.extend([datos, Spacer(1, 22)])

    control = Table([
        [Paragraph("<b>CONTROL DE ENTRADA</b>", centro), Paragraph("<b>CONTROL DE SALIDA</b>", centro)],
        [
            Paragraph(f"Hora de entrada: <b>{fecha.strftime('%H:%M:%S')}</b>", normal),
            Paragraph("Hora de salida: __________________", normal),
        ],
        [Paragraph("", normal), Paragraph("", normal)],
        [Paragraph("Firma de entrada:", normal), Paragraph("Firma de salida:", normal)],
        [Paragraph("<br/><br/>____________________________________", centro), Paragraph("<br/><br/>____________________________________", centro)],
        [Paragraph("Firma de la persona", pequeno_centro), Paragraph("Firma de la persona", pequeno_centro)],
    ], colWidths=[3.45 * inch, 3.45 * inch], rowHeights=[0.38 * inch, 0.55 * inch, 0.18 * inch, 0.35 * inch, 0.78 * inch, 0.3 * inch])
    control.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#1f2937")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.extend([control, Spacer(1, 18)])

    elementos.append(Paragraph(
        "Registro administrativo de acceso generado por SICODE-UCT. La hora de entrada se registra automáticamente al crear la boleta. "
        "La hora de salida y la firma de salida se completan manualmente sobre la impresión al finalizar la visita.",
        pequeno,
    ))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(
        f"Registrado en SICODE-UCT por: {escape(acceso.creado_por.nombre if acceso.creado_por else 'Usuario autorizado')}",
        pequeno,
    ))

    doc.build(elementos)
    archivo.seek(0)

    registrar_bitacora(
        accion="CONSULTAR_BOLETA_ACCESO_CCT_PDF",
        modulo="C.A CCT",
        descripcion=f"Se generó la boleta PDF {acceso.correlativo} para impresión.",
        usuario_id=current_user.id,
        entidad="AccesoCCT",
        entidad_id=acceso.id,
        datos_posteriores={"correlativo": acceso.correlativo},
    )

    return send_file(
        archivo,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{acceso.correlativo}_acceso_CCT.pdf",
    )
