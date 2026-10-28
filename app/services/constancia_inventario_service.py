"""Constancia tabular, una página A4, para inventario de activos agrupados."""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether


def generar_constancia_inventario(principal, equipos):
    """Devuelve PDF de una sola hoja. Limita el tamaño de grupo a 21 activos."""
    if len(equipos) > 21:
        raise ValueError("La constancia admite un máximo de 21 activos.")
    buffer = BytesIO()
    ancho, alto = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(ancho, alto), leftMargin=30, rightMargin=30,
                            topMargin=25, bottomMargin=25)
    estilo = ParagraphStyle("celda", fontName="Helvetica", fontSize=7.1, leading=9.2)
    encabezado = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=1)
    sub = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=7.2, leading=10, alignment=1)
    nota = ParagraphStyle("nota", fontName="Helvetica", fontSize=6.2, leading=8)
    def c(value):
        return Paragraph(escape(str(value if value not in (None, "") else "No consignado")), estilo)
    def tabla(filas, anchos, header=True):
        t = Table(filas, colWidths=anchos, repeatRows=1 if header else 0, hAlign="LEFT")
        estilos = [
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#94a3b8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            estilos += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        t.setStyle(TableStyle(estilos))
        return t

    width = ancho - 60
    elementos = [
        Paragraph("SICODE-UCT · COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS", sub),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO · MINISTERIO DE GOBERNACIÓN", sub),
        Spacer(1, 8),
        Paragraph("CONSTANCIA DE INVENTARIO INSTITUCIONAL DE EQUIPOS", encabezado),
        Spacer(1, 8),
    ]
    metadatos = [
        [c("No. registro"), c(principal.numero_registro),
         c("Fecha de emisión"), c(datetime.now().strftime("%d/%m/%Y %H:%M"))],
        [c("Custodio institucional"), c(principal.nombre_responsable),
         c("Usuario habitual"), c(principal.nombre_usuario_habitual)],
        [c("Coordinación"), c(principal.area), c("Ubicación"), c(principal.ubicacion)],
    ]
    elementos.append(tabla(metadatos, [100, width / 2 - 100, 100, width / 2 - 100], header=False))
    elementos += [Spacer(1, 9), Paragraph("EQUIPOS Y PERIFÉRICOS VINCULADOS", sub), Spacer(1, 4)]
    anchos = [33, 60, 83, 110, 67, 80, 85, width - 518]
    titulos = ["No.", "Tipo", "SICOIN", "Nombre", "Marca", "Modelo", "Serie", "IP estática"]
    cabecera = [Paragraph(f"<font color='white'><b>{escape(t)}</b></font>", estilo) for t in titulos]
    filas = [cabecera]
    for i, equipo in enumerate(equipos, 1):
        filas.append([c(i), c(equipo.tipo), c(equipo.codigo), c(equipo.nombre),
                      c(equipo.marca), c(equipo.modelo), c(equipo.serie), c(equipo.ip_estatica)])
    # Shrink dimensions for a single page while retaining full text (no slicing).
    table = tabla(filas, anchos)
    total_height = table.wrap(width, alto)[1]
    disponibles = alto - 240
    if total_height > disponibles:
        from reportlab.platypus import KeepInFrame
        elementos.append(KeepInFrame(width, disponibles, [table], mode="shrink", hAlign="LEFT"))
    else:
        elementos.append(table)
    elementos += [
        Spacer(1, 10),
        Paragraph(f"Total de activos vinculados: <b>{len(equipos)}</b>. Cada activo conserva su SICOIN e historial individual.", nota),
        Paragraph("Documento administrativo generado por SICODE-UCT; no acredita por sí solo cumplimiento técnico. "
                  "Las modificaciones y emisiones quedan registradas en bitácora.", nota),
    ]
    doc.build(elementos)
    buffer.seek(0)
    return buffer
