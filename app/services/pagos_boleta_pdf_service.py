from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import legal
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


AZUL = HexColor("#002060")
GRIS = HexColor("#D9D9D9")
GRIS_OSCURO = HexColor("#BFBFBF")
NEGRO = black
BLANCO = white

TARIFA_DIA = Decimal("50.00")
TARIFA_MES = Decimal("1500.00")
BANCO_DEFAULT = "Banco de los Trabajadores (BANTRAB)"
CUENTA_DEFAULT = "2850093390"
CUENTA_NOMBRE_DEFAULT = "Dirección de Servicios Administrativos y Financieros / Ingresos Propios"
BASE_LEGAL_DEFAULT = (
    "Base legal: artículo 7 de la Ley de implementación del Control Telemático en el Proceso Penal, "
    "Decreto Número 49-2016 del Congreso de la República; artículos 3 y 5 del Acuerdo Gubernativo "
    "Número 89-2023 de fecha 16 de mayo de 2023, Tarifario para el cobro de los servicios de control telemático."
)
PLANTILLA_VERSION = "PAGOS-UCT-LEGAL-2026-09-V1"


@dataclass(frozen=True)
class DatosBoletaPago:
    fecha_comprobante: date
    no_sp: str
    numero_expediente: str
    organo_jurisdiccional: str
    nombre_sujeto: str
    periodo_desde: date
    periodo_hasta: date
    dias_aplicados: int
    meses_aplicados: int
    numero_boleta: str
    elaborado_por: str = ""
    contacto: str = ""
    banco: str = BANCO_DEFAULT
    cuenta: str = CUENTA_DEFAULT
    cuenta_nombre: str = CUENTA_NOMBRE_DEFAULT
    tarifa_dia: Decimal = TARIFA_DIA
    tarifa_mes: Decimal = TARIFA_MES
    base_legal: str = BASE_LEGAL_DEFAULT

    @property
    def total(self) -> Decimal:
        return (
            Decimal(self.dias_aplicados or 0) * Decimal(self.tarifa_dia)
            + Decimal(self.meses_aplicados or 0) * Decimal(self.tarifa_mes)
        ).quantize(Decimal("0.01"))


def _fecha(valor: Optional[date]) -> str:
    if not valor:
        return ""
    return f"{valor.month}/{valor.day}/{str(valor.year)[-2:]}"


def _money(valor: Decimal) -> str:
    return f"Q{Decimal(valor or 0):,.2f}"


def _draw_wrapped(
    c,
    text,
    x,
    y,
    w,
    h,
    *,
    font_size=10,
    leading=None,
    align="CENTER",
    bold=False,
    color=AZUL,
    valign="MIDDLE",
):
    texto = "" if text is None else str(text)
    font_name = "Helvetica-Bold" if bold else "Helvetica"
    style = ParagraphStyle(
        "pagoCell",
        fontName=font_name,
        fontSize=font_size,
        leading=leading or (font_size * 1.16),
        textColor=color,
        alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 1),
        spaceBefore=0,
        spaceAfter=0,
    )
    para = Paragraph(escape(texto).replace("\n", "<br/>"), style)
    _aw, ah = para.wrap(max(1, w - 6), max(1, h - 4))
    if valign == "TOP":
        py = y + h - ah - 3
    elif valign == "BOTTOM":
        py = y + 3
    else:
        py = y + max(2, (h - ah) / 2)
    para.drawOn(c, x + 3, py)


def _cell(
    c,
    x,
    y,
    w,
    h,
    text="",
    *,
    fill=None,
    bold=False,
    size=10,
    align="CENTER",
    border=True,
    valign="MIDDLE",
    leading=None,
):
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, stroke=0, fill=1)
    if border:
        c.setStrokeColor(NEGRO)
        c.setLineWidth(0.65)
        c.rect(x, y, w, h, stroke=1, fill=0)
    if text not in (None, ""):
        _draw_wrapped(
            c,
            text,
            x,
            y,
            w,
            h,
            font_size=size,
            align=align,
            bold=bold,
            color=AZUL,
            valign=valign,
            leading=leading,
        )


def _logo_path_default() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "img" / "boleta_pagos_mingob.jpeg"


def _dibujar_formulario(c, datos: DatosBoletaPago, logo_path: Optional[Path] = None):
    _page_w, page_h = legal
    x0 = 51.0
    widths = [151.0, 70.0, 94.0, 15.0, 67.0, 99.0]
    xs = [x0]
    for width in widths:
        xs.append(xs[-1] + width)

    # Alturas, proporciones y combinaciones tomadas de la hoja Excel operativa.
    heights = {
        1: 23.1, 2: 23.1, 3: 23.1, 4: 23.1, 5: 23.1, 6: 23.1,
        7: 24.9, 8: 24.9, 9: 24.9, 10: 57.0, 11: 35.25, 12: 24.9,
        13: 6.9, 14: 8.25, 15: 24.9, 16: 24.9, 17: 24.9, 18: 6.9,
        19: 30.0, 20: 30.0, 21: 30.0, 22: 24.9, 23: 24.9, 24: 24.9,
        25: 24.9, 26: 24.9, 27: 24.9, 28: 12.75, 29: 12.75,
        30: 23.25, 31: 23.25, 32: 24.9, 33: 23.1, 34: 23.1,
    }
    y_top = {}
    y_bottom = {}
    cursor = page_h
    for row in range(1, 35):
        y_top[row] = cursor
        cursor -= heights[row]
        y_bottom[row] = cursor

    logo_y = y_bottom[6]
    logo_h = y_top[2] - y_bottom[6]
    _cell(c, x0, logo_y, sum(widths), logo_h, fill=BLANCO, border=True)
    logo = Path(logo_path) if logo_path else _logo_path_default()
    if logo.exists():
        image = ImageReader(str(logo))
        iw, ih = image.getSize()
        max_w = sum(widths) - 26
        max_h = logo_h - 7
        scale = min(max_w / iw, max_h / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(
            image,
            x0 + (sum(widths) - dw) / 2,
            logo_y + (logo_h - dh) / 2,
            width=dw,
            height=dh,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        _draw_wrapped(
            c,
            "GOBIERNO DE LA REPÚBLICA DE GUATEMALA | Ministerio de Gobernación",
            x0,
            logo_y,
            sum(widths),
            logo_h,
            font_size=16,
            bold=True,
        )

    _cell(
        c,
        x0,
        y_bottom[7],
        sum(widths),
        heights[7],
        "DATOS DEL USUARIO DEL DISPOSITIVO DE CONTROL TELEMÁTICO",
        fill=GRIS,
        bold=True,
        size=10.5,
    )

    _cell(c, xs[0], y_bottom[8], widths[0], heights[8], "Fecha:", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[8], widths[1] + widths[2], heights[8], _fecha(datos.fecha_comprobante), bold=True)
    _cell(c, xs[3], y_bottom[8], widths[3] + widths[4], heights[8], "SP No.", fill=GRIS, bold=True)
    _cell(c, xs[5], y_bottom[8], widths[5], heights[8], datos.no_sp, bold=True)

    _cell(
        c, xs[0], y_bottom[9], widths[0], heights[9],
        "Número único de expediente:", fill=GRIS, bold=True, align="LEFT", size=9.3,
    )
    _cell(c, xs[1], y_bottom[9], sum(widths[1:]), heights[9], datos.numero_expediente, bold=True)

    _cell(
        c, xs[0], y_bottom[10], widths[0], heights[10],
        "Órgano jurisdiccional:", fill=GRIS, bold=True, align="LEFT", size=9.3,
    )
    _cell(
        c, xs[1], y_bottom[10], sum(widths[1:]), heights[10],
        datos.organo_jurisdiccional, size=9.3, leading=11,
    )

    _cell(
        c, xs[0], y_bottom[11], widths[0], heights[11],
        "Nombre del Sujeto Portador", fill=GRIS, bold=True, align="LEFT", size=9.2,
    )
    _cell(
        c, xs[1], y_bottom[11], sum(widths[1:]), heights[11],
        datos.nombre_sujeto, bold=True, size=10.2,
    )

    _cell(c, xs[0], y_bottom[12], widths[0], heights[12], "Plazo", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[12], widths[1], heights[12], "Inicio:", fill=GRIS, bold=True)
    _cell(c, xs[2], y_bottom[12], widths[2], heights[12], _fecha(datos.periodo_desde), bold=True)
    _cell(c, xs[3], y_bottom[12], widths[3], heights[12], "", fill=BLANCO)
    _cell(c, xs[4], y_bottom[12], widths[4], heights[12], "Fin:", fill=GRIS, bold=True)
    _cell(c, xs[5], y_bottom[12], widths[5], heights[12], _fecha(datos.periodo_hasta), bold=True)

    _cell(c, x0, y_bottom[13], sum(widths), heights[13], border=False)
    _cell(c, x0, y_bottom[14], sum(widths), heights[14], border=True)

    _cell(c, xs[0], y_bottom[15], sum(widths[:4]), heights[15], "", border=False)
    _cell(
        c, xs[4], y_bottom[15], widths[4] + widths[5], heights[15],
        "Tarifa aplicada", fill=GRIS_OSCURO, bold=True,
    )

    _cell(c, xs[0], y_bottom[16], widths[0], heights[16], "Días aplicados:", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[16], widths[1] + widths[2], heights[16], str(datos.dias_aplicados or 0))
    _cell(c, xs[3], y_bottom[16], widths[3], heights[16], "", border=False)
    _cell(c, xs[4], y_bottom[16], widths[4], heights[16], str(datos.dias_aplicados or 0))
    _cell(c, xs[5], y_bottom[16], widths[5], heights[16], _money(datos.tarifa_dia))

    _cell(c, xs[0], y_bottom[17], widths[0], heights[17], "Meses aplicados:", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[17], widths[1] + widths[2], heights[17], str(datos.meses_aplicados or 0))
    _cell(c, xs[3], y_bottom[17], widths[3], heights[17], "", border=False)
    _cell(c, xs[4], y_bottom[17], widths[4], heights[17], "X")
    _cell(c, xs[5], y_bottom[17], widths[5], heights[17], _money(datos.tarifa_mes))

    _cell(c, x0, y_bottom[18], sum(widths), heights[18], border=False)

    _cell(c, xs[0], y_bottom[19], widths[0], heights[19], "Banco:", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[19], sum(widths[1:]), heights[19], datos.banco, size=9.5)

    _cell(c, xs[0], y_bottom[20], widths[0], heights[20], "Numero de cuenta:", fill=GRIS, bold=True, align="LEFT")
    cuenta_texto = f"{datos.cuenta} a nombre de: {datos.cuenta_nombre}".strip()
    _cell(c, xs[1], y_bottom[20], sum(widths[1:]), heights[20], cuenta_texto, size=8.8, leading=10.4)

    _cell(c, xs[0], y_bottom[21], widths[0], heights[21], "Cantidad a pagar:", fill=GRIS, bold=True, align="LEFT")
    _cell(c, xs[1], y_bottom[21], sum(widths[1:]), heights[21], _money(datos.total), bold=True, size=11)

    for row in range(22, 28):
        _cell(c, x0, y_bottom[row], sum(widths), heights[row], border=False)

    elaborado_h = heights[28] + heights[29]
    _cell(c, xs[0], y_bottom[29], widths[0], elaborado_h, "", border=False)
    elaborado = f"Elaborado Por:\n{datos.elaborado_por}" if datos.elaborado_por else "Elaborado Por:"
    _cell(
        c, xs[1], y_bottom[29], sum(widths[1:5]), elaborado_h,
        elaborado, bold=True, size=9.5, border=True,
    )
    _cell(c, xs[5], y_bottom[29], widths[5], elaborado_h, "", border=False)

    contacto_h = heights[30] + heights[31]
    _cell(c, xs[0], y_bottom[31], widths[0], contacto_h, "Contacto:", fill=GRIS, bold=True)
    _cell(c, xs[1], y_bottom[31], sum(widths[1:]), contacto_h, datos.contacto or "", bold=True, size=8.8)

    _cell(c, xs[0], y_bottom[32], widths[0], heights[32], "Boleta No.", bold=True)
    _cell(c, xs[1], y_bottom[32], sum(widths[1:]), heights[32], datos.numero_boleta, bold=True)

    base_h = heights[33] + heights[34]
    _cell(
        c, x0, y_bottom[34], sum(widths), base_h,
        datos.base_legal, size=6.8, align="LEFT", leading=7.7,
    )

    c.setTitle(f"Boleta de pago SP {datos.no_sp} - {datos.numero_boleta}")
    c.setAuthor("SICODE-UCT")
    c.setSubject("Boleta administrativa de pago de control telemático")


def _pdf_formulario(datos: DatosBoletaPago, logo_path: Optional[Path] = None) -> bytes:
    salida = BytesIO()
    c = canvas.Canvas(salida, pagesize=legal, pageCompression=1)
    _dibujar_formulario(c, datos, logo_path=logo_path)
    c.showPage()
    c.save()
    return salida.getvalue()


def _pdf_imagen_comprobante(comprobante: bytes) -> bytes:
    salida = BytesIO()
    c = canvas.Canvas(salida, pagesize=legal, pageCompression=1)
    page_w, page_h = legal
    with PILImage.open(BytesIO(comprobante)) as imagen_verificacion:
        imagen_verificacion.verify()

    image = ImageReader(BytesIO(comprobante))
    iw, ih = image.getSize()
    margen = 36
    max_w, max_h = page_w - 2 * margen, page_h - 2 * margen
    scale = min(max_w / iw, max_h / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(
        image,
        (page_w - dw) / 2,
        (page_h - dh) / 2,
        width=dw,
        height=dh,
        preserveAspectRatio=True,
        mask="auto",
    )
    c.showPage()
    c.save()
    return salida.getvalue()


def _fusionar_pdf(base_pdf: bytes, comprobante: Optional[bytes], comprobante_mime: str = "") -> bytes:
    if not comprobante:
        return base_pdf

    mime = (comprobante_mime or "").lower().strip()
    if mime == "application/pdf" or comprobante[:5] == b"%PDF-":
        anexo_pdf = comprobante
    else:
        anexo_pdf = _pdf_imagen_comprobante(comprobante)

    writer = PdfWriter()
    for page in PdfReader(BytesIO(base_pdf)).pages:
        writer.add_page(page)

    lector_anexo = PdfReader(BytesIO(anexo_pdf))
    if len(lector_anexo.pages) > 5:
        raise ValueError("El comprobante PDF no puede contener más de 5 páginas.")
    for page in lector_anexo.pages:
        writer.add_page(page)

    salida = BytesIO()
    writer.write(salida)
    return salida.getvalue()


def generar_boleta_pago_pdf(
    datos: DatosBoletaPago,
    *,
    comprobante: Optional[bytes] = None,
    comprobante_mime: str = "",
    logo_path: Optional[Path] = None,
):
    base = _pdf_formulario(datos, logo_path=logo_path)
    final = _fusionar_pdf(base, comprobante, comprobante_mime)
    nombre = f"SP{datos.no_sp}_BOLETA_{datos.numero_boleta}.pdf".replace("/", "-").replace("\\", "-")
    return {
        "bytes": final,
        "sha256": sha256(final).hexdigest(),
        "nombre": nombre,
        "mime": "application/pdf",
        "plantilla_version": PLANTILLA_VERSION,
        "total": datos.total,
    }
