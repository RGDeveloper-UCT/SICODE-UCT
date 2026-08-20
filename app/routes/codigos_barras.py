import re
from io import BytesIO

from flask import Blueprint, Response, send_file
from flask_login import current_user, login_required
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models.expediente import Expediente
from app.services.bitacora_service import registrar_bitacora


codigos_barras_bp = Blueprint("codigos_barras", __name__)


def _valor_codigo(expediente):
    """Usa el identificador interno estable y evita exponer datos personales."""
    return (expediente.codigo_interno or f"SICODE-UCT-SP-{expediente.no_sp}").strip()


@codigos_barras_bp.route("/expedientes/<int:expediente_id>/codigo-barras.svg")
@login_required
def codigo_svg(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    codigo = _valor_codigo(expediente)

    dibujo = createBarcodeDrawing(
        "Code128",
        value=codigo,
        barHeight=34,
        barWidth=0.72,
        humanReadable=False,
    )
    svg = renderSVG.drawToString(dibujo)

    respuesta = Response(svg, mimetype="image/svg+xml")
    respuesta.headers["Cache-Control"] = "private, max-age=3600"
    respuesta.headers["Content-Disposition"] = f'inline; filename="codigo_barras_sp_{expediente.no_sp}.svg"'
    return respuesta


@codigos_barras_bp.route("/expedientes/<int:expediente_id>/exportar/etiqueta-codigo-barras.pdf")
@login_required
def exportar_etiqueta_pdf(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    codigo = _valor_codigo(expediente)

    ancho_pagina = 90 * mm
    alto_pagina = 40 * mm
    archivo_pdf = BytesIO()
    pdf = canvas.Canvas(archivo_pdf, pagesize=(ancho_pagina, alto_pagina))

    pdf.setTitle(f"Etiqueta SP {expediente.no_sp} - SICODE-UCT")
    pdf.setAuthor("SICODE-UCT")

    pdf.setFillColor(colors.HexColor("#17233c"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(5 * mm, alto_pagina - 7 * mm, "SICODE-UCT")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(ancho_pagina - 5 * mm, alto_pagina - 7 * mm, f"SP {expediente.no_sp}")

    maximo_barra = ancho_pagina - (10 * mm)
    ancho_barra = 0.28 * mm
    codigo_barras = Code128(codigo, barHeight=14 * mm, barWidth=ancho_barra, humanReadable=False)
    if codigo_barras.width > maximo_barra:
        proporcion = maximo_barra / codigo_barras.width
        ancho_barra = max(0.18 * mm, ancho_barra * proporcion)
        codigo_barras = Code128(codigo, barHeight=14 * mm, barWidth=ancho_barra, humanReadable=False)

    x_codigo = max(5 * mm, (ancho_pagina - codigo_barras.width) / 2)
    codigo_barras.drawOn(pdf, x_codigo, 10 * mm)

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(ancho_pagina / 2, 6.5 * mm, codigo)
    pdf.setFont("Helvetica", 6.5)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawCentredString(ancho_pagina / 2, 3.5 * mm, "Etiqueta de control interno · sin datos personales")

    pdf.showPage()
    pdf.save()
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_ETIQUETA_CODIGO_BARRAS",
        modulo="Expedientes",
        descripcion=f"Se generó etiqueta de código de barras para el SP {expediente.no_sp}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
    )

    no_sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", str(expediente.no_sp))
    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=f"etiqueta_sp_{no_sp_limpio}_sicode_uct.pdf",
        mimetype="application/pdf",
    )
