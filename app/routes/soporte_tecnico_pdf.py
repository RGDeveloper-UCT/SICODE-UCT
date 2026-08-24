from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, send_file
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.forms.soporte_tecnico_form import (
    GESTION_USUARIO,
    HARDWARE,
    INSTALACION,
    REVISION,
    SOFTWARE,
    TIPOS_EQUIPO,
    TIPOS_SERVICIO,
    TRASLADO,
)
from app.models.soporte_tecnico import ServicioSoporteTecnico
from app.services.bitacora_service import registrar_bitacora


soporte_tecnico_pdf_bp = Blueprint("soporte_tecnico_pdf", __name__)


def _texto(valor):
    return escape(str(valor)) if valor not in (None, "") else ""


def _seleccionados(valores, catalogo):
    mapa = dict(catalogo)
    return [mapa.get(codigo, codigo) for codigo in (valores or [])]


def _tabla_seccion(titulo, filas, mini):
    datos = [[Paragraph(f"<b>{escape(titulo)}</b>", mini), ""]]
    for etiqueta, valor in filas:
        if valor in (None, "", [], ()):  # No imprimir campos sin información.
            continue
        datos.append([
            Paragraph(f"<b>{escape(str(etiqueta))}</b>", mini),
            Paragraph(_texto(valor), mini),
        ])
    if len(datos) == 1:
        return None

    tabla = Table(datos, colWidths=[2.15 * inch, 4.85 * inch])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("SPAN", (0, 0), (-1, 0)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aeb8c7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabla


def _lista_texto(valores):
    return "<br/>".join(f"• {escape(str(valor))}" for valor in valores if valor)


def _agregar(elementos, tabla):
    if tabla is not None:
        elementos.extend([tabla, Spacer(1, 5)])


@soporte_tecnico_pdf_bp.route("/coordinacion/soporte-tecnico/boletas/<int:boleta_id>/pdf-limpio")
@login_required
def generar_pdf_limpio(boleta_id):
    boleta = ServicioSoporteTecnico.query.get_or_404(boleta_id)

    archivo = BytesIO()
    doc = SimpleDocTemplate(
        archivo,
        pagesize=letter,
        leftMargin=28,
        rightMargin=28,
        topMargin=24,
        bottomMargin=24,
    )
    estilos = getSampleStyleSheet()
    mini = ParagraphStyle(
        "MiniSoporteLimpio",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=9.1,
        spaceAfter=0,
    )
    centro = ParagraphStyle("CentroSoporteLimpio", parent=mini, alignment=1)
    titulo = ParagraphStyle(
        "TituloSoporteLimpio",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=12,
        alignment=1,
    )

    elementos = [
        Paragraph("SICODE-UCT", centro),
        Paragraph("COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS", centro),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", centro),
        Spacer(1, 3),
        Paragraph("BOLETA DE SERVICIO DE SOPORTE TÉCNICO", titulo),
        Spacer(1, 7),
    ]

    fecha = boleta.fecha_hora_solicitud
    cabecera = Table([[
        Paragraph(f"<b>No. de boleta:</b> {_texto(boleta.numero_boleta)}", mini),
        Paragraph(f"<b>Fecha:</b> {fecha.strftime('%d/%m/%Y') if fecha else ''}", mini),
        Paragraph(f"<b>Hora:</b> {fecha.strftime('%H:%M') if fecha else ''}", mini),
    ]], colWidths=[3.0 * inch, 2.0 * inch, 2.0 * inch])
    cabecera.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#6b7280")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([cabecera, Spacer(1, 5)])

    _agregar(elementos, _tabla_seccion("1. DATOS DEL USUARIO Y UBICACIÓN", [
        ("Nombre del usuario", boleta.usuario_solicitante),
        ("Puesto / cargo", boleta.puesto_cargo),
        ("Coordinación / área", boleta.coordinacion_area),
        ("Técnico asignado", boleta.tecnico_asignado),
    ], mini))

    tipos = _seleccionados(boleta.tipos_servicio, TIPOS_SERVICIO)
    if boleta.otro_servicio_ti:
        tipos.append(boleta.otro_servicio_ti)
    _agregar(elementos, _tabla_seccion("2. TIPO DE SERVICIO SOLICITADO", [
        ("Servicios seleccionados", _lista_texto(tipos)),
    ], mini))

    detalle = []
    bloques = [
        ("Gestión de usuario", boleta.gestion_usuario_detalles, GESTION_USUARIO),
        ("Mantenimiento de hardware", boleta.hardware_detalles, HARDWARE),
        ("Mantenimiento de software", boleta.software_detalles, SOFTWARE),
        ("Instalación", boleta.instalacion_detalles, INSTALACION),
        ("Traslado", boleta.traslado_detalles, TRASLADO),
        ("Revisión / diagnóstico", boleta.revision_detalles, REVISION),
    ]
    for etiqueta, valores, catalogo in bloques:
        seleccion = _seleccionados(valores, catalogo)
        if seleccion:
            detalle.append((etiqueta, _lista_texto(seleccion)))
    if boleta.otro_instalacion:
        detalle.append(("Otro detalle de instalación", boleta.otro_instalacion))
    if boleta.otro_traslado:
        detalle.append(("Otro detalle de traslado", boleta.otro_traslado))
    if boleta.otro_revision:
        detalle.append(("Otro detalle de revisión", boleta.otro_revision))
    _agregar(elementos, _tabla_seccion("3–4. DETALLE FUNCIONAL DEL SERVICIO", detalle, mini))

    tipo_equipo = dict(TIPOS_EQUIPO).get(boleta.tipo_equipo, boleta.tipo_equipo or "")
    if boleta.tipo_equipo == "OTRO" and boleta.tipo_equipo_otro:
        tipo_equipo = boleta.tipo_equipo_otro
    _agregar(elementos, _tabla_seccion("5. IDENTIFICACIÓN DEL EQUIPO", [
        ("Tipo", tipo_equipo),
        ("Marca / modelo", boleta.marca_modelo),
        ("No. de serie", boleta.numero_serie),
        ("SICOIN", boleta.inventario),
        ("IP / nombre de equipo", boleta.ip_nombre_equipo),
    ], mini))

    _agregar(elementos, _tabla_seccion("6. DESCRIPCIÓN DE LA SOLICITUD / FALLA REPORTADA", [
        ("Solicitud / falla", boleta.descripcion_solicitud),
    ], mini))

    _agregar(elementos, _tabla_seccion("7. DIAGNÓSTICO Y TRABAJO REALIZADO", [
        ("Diagnóstico / trabajo", boleta.diagnostico_trabajo),
    ], mini))

    cierre = boleta.fecha_hora_cierre.strftime("%d/%m/%Y %H:%M") if boleta.fecha_hora_cierre else ""
    filas_cierre = [
        ("Estado final", boleta.estado_legible),
        ("Fecha / hora de cierre", cierre),
        ("Tiempo de resolución", boleta.tiempo_empleado),
        ("Seguimiento", "Sí" if boleta.seguimiento else ""),
        ("Observaciones", boleta.observaciones_cierre),
    ]
    _agregar(elementos, _tabla_seccion("8. RESULTADO Y CIERRE DEL SERVICIO", filas_cierre, mini))

    firma_usuario_fecha = boleta.fecha_firma_usuario.strftime("%d/%m/%Y") if boleta.fecha_firma_usuario else "____/____/________"
    firma_tecnico_fecha = boleta.fecha_firma_tecnico.strftime("%d/%m/%Y") if boleta.fecha_firma_tecnico else "____/____/________"
    nombre_usuario = boleta.nombre_firma_usuario or boleta.usuario_solicitante
    nombre_tecnico = boleta.nombre_firma_tecnico or boleta.tecnico_asignado
    firmas = Table([
        [Paragraph("<b>USUARIO / SOLICITANTE</b>", centro), Paragraph("<b>TÉCNICO DE SOPORTE</b>", centro)],
        [Paragraph(f"Nombre: {_texto(nombre_usuario)}", mini), Paragraph(f"Nombre: {_texto(nombre_tecnico)}", mini)],
        [Paragraph("Firma: ______________________________", mini), Paragraph("Firma: ______________________________", mini)],
        [Paragraph(f"Fecha: {firma_usuario_fecha}", mini), Paragraph(f"Fecha: {firma_tecnico_fecha}", mini)],
    ], colWidths=[3.5 * inch, 3.5 * inch])
    firmas.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([firmas, Spacer(1, 5)])
    elementos.append(Paragraph(
        "Constancia administrativa generada por SICODE-UCT. La firma se realiza sobre la impresión. El sistema conserva metadatos de atención y no almacena contraseñas, archivos respaldados ni copias de documentos del usuario.",
        mini,
    ))

    doc.build(elementos)
    archivo.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_BOLETA_SOPORTE_PDF",
        modulo="Coordinación",
        descripcion=f"Se generó PDF depurado de la boleta {boleta.numero_boleta}.",
        usuario_id=current_user.id,
        entidad="ServicioSoporteTecnico",
        entidad_id=boleta.id,
        datos_posteriores={"numero_boleta": boleta.numero_boleta, "formato": "PDF", "modo": "solo_campos_con_datos"},
    )

    nombre = f"{boleta.numero_boleta}_soporte_tecnico.pdf".replace("/", "-")
    return send_file(archivo, as_attachment=True, download_name=nombre, mimetype="application/pdf")
