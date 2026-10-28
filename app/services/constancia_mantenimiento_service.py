"""Constancia compacta con formato institucional similar a la boleta de soporte."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame

AZUL = colors.HexColor("#1F2D44")
BORDE = colors.HexColor("#A8B4C4")
FONDO = colors.HexColor("#EDF2F8")

NORMAL = ParagraphStyle("MntNormal", fontName="Helvetica", fontSize=7.3, leading=9.3, spaceAfter=0)
PEQUENO = ParagraphStyle("MntPequeno", parent=NORMAL, fontSize=6.6, leading=8)
TITULO = ParagraphStyle("MntTitulo", parent=NORMAL, fontName="Helvetica-Bold",
                        fontSize=11, leading=14, alignment=TA_CENTER)
CENTRO = ParagraphStyle("MntCentro", parent=PEQUENO, alignment=TA_CENTER)

def p(valor, estilo=NORMAL):
    return Paragraph(escape(str(valor if valor is not None else "—")).replace("\n", "<br/>"), estilo)

def encabezado(texto, ancho):
    t = Table([[Paragraph(f'<font color="white"><b>{escape(texto)}</b></font>', PEQUENO)]], colWidths=[ancho])
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), AZUL),
                           ("TOPPADDING", (0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    return t

def tabla(filas, anchos, centrado=False):
    t=Table([[p(c, PEQUENO) for c in fila] for fila in filas], colWidths=anchos, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.35,BORDE),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
    ]))
    return t

def generar_constancia_mantenimiento(m):
    """Resumen verificable de una hoja normalmente; puede crecer si las observaciones lo exigen."""
    buffer=BytesIO()
    documento=SimpleDocTemplate(buffer,pagesize=letter,leftMargin=28,rightMargin=28,topMargin=27,bottomMargin=25)
    ancho=letter[0]-56
    mitad=ancho/2
    d=m.datos_equipo or {}
    segundos=m.segundos()
    duracion=f"{segundos//3600:02d}:{segundos%3600//60:02d}:{segundos%60:02d}"
    fecha=lambda f:f.strftime("%d/%m/%Y %H:%M") if f else "—"
    flow=[
        Paragraph("SICODE-UCT",TITULO),
        Paragraph("COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS",CENTRO),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO",CENTRO),
        Spacer(1,5),
        Paragraph("<b>CONSTANCIA DE MANTENIMIENTO — CONTROL 09</b>",TITULO),
        Spacer(1,7),
        tabla([
            ["No. "+m.numero,"Tipo: "+m.tipo,"Estado: "+m.estado],
            ["Inicio: "+fecha(m.iniciado_en),"Cierre: "+fecha(m.cerrado_en),"Duración: "+duracion],
        ],[ancho*.33,ancho*.36,ancho*.31]),
        Spacer(1,5),encabezado("1. IDENTIFICACIÓN DEL EQUIPO",ancho),
        tabla([
            ["SICOIN",d.get("codigo") or "—","Equipo",d.get("nombre") or "—"],
            ["Tipo",d.get("tipo") or "—","Marca / modelo",f"{d.get('marca') or '—'} / {d.get('modelo') or '—'}"],
            ["Serie",d.get("serie") or "—","IP",d.get("ip_estatica") or "—"],
            ["Área",d.get("area") or "—","Ubicación",d.get("ubicacion") or "—"],
            ["Custodio",d.get("custodio") or "—","Usuario habitual",d.get("usuario_habitual") or "—"],
        ],[ancho*.13,ancho*.37,ancho*.17,ancho*.33]),
        Spacer(1,5),encabezado("2. DIAGNÓSTICO INICIAL",ancho),
        tabla([[m.diagnostico or "Sin diagnóstico consignado"]],[ancho]),
        Spacer(1,5),encabezado("3. RESPALDO DE INFORMACIÓN",ancho),
    ]
    respaldo=[f for f in m.checklist if f.get("grupo")=="respaldo"]
    cubiertos=[f["actividad"] for f in respaldo if f.get("resultado")=="CUMPLE"]
    flow.append(tabla([
        ["Verificaciones realizadas",", ".join(cubiertos) or "Sin verificaciones cumplidas"],
        ["Tamaño declarado",f"{m.respaldo_gb} GB" if m.respaldo_gb is not None else "No registrado"],
    ],[ancho*.26,ancho*.74]))
    flow.extend([Spacer(1,5),encabezado("4. TRABAJO REALIZADO — CONSOLIDADO",ancho)])
    grupos={}
    hallazgos=[]
    for fila in m.checklist:
        if fila.get("resultado")=="CUMPLE" and fila.get("grupo")!="respaldo":
            grupos.setdefault(fila["grupo_nombre"],[]).append(fila["actividad"])
        elif fila.get("resultado")=="NO_CUMPLE":
            hallazgos.append(fila)
    filas=[[grupo,", ".join(items)] for grupo,items in grupos.items()]
    if not filas:
        filas=[["Sin actividades cumplidas","No se registraron controles en estado Cumple."]]
    flow.append(tabla(filas,[ancho*.26,ancho*.74]))
    flow.extend([Spacer(1,5),encabezado("5. HALLAZGOS / CONTROLES NO CONFORMES",ancho)])
    if hallazgos:
        flow.append(tabla([[f["actividad"],f.get("observacion") or "Sin detalle"] for f in hallazgos],
                          [ancho*.38,ancho*.62]))
    else:
        flow.append(tabla([["No se registraron controles marcados como No cumple."]],[ancho]))
    if m.trabajo_realizado:
        flow.extend([Spacer(1,5),encabezado("6. OBSERVACIONES ADICIONALES DEL TÉCNICO",ancho),
                     tabla([[m.trabajo_realizado]],[ancho])])
    flow.extend([
        Spacer(1,5),encabezado("7. RESULTADO Y CIERRE",ancho),
        tabla([
            ["Estado final: "+(m.estado_final or "—"),
             "Seguimiento: "+("Sí" if m.requiere_seguimiento else "No"),
             "Boleta: "+(m.boleta.numero_boleta if m.boleta else "Sin boleta")],
        ],[ancho*.35,ancho*.25,ancho*.40]),
        Spacer(1,8),
        tabla([
            ["USUARIO / RESPONSABLE", "TÉCNICO RESPONSABLE"],
            ["",""],
            ["Firma: __________________________", "Firma: __________________________"],
            [d.get("usuario_habitual") or d.get("custodio") or "Nombre: __________________",m.tecnico.nombre],
        ],[mitad,mitad]),
        Spacer(1,5),
        Paragraph("Constancia administrativa generada por SICODE-UCT. La firma se realiza sobre el documento impreso.",CENTRO),
    ])
    # Compacta el contenido para mantener firmas visibles. Si el texto es excepcionalmente largo,
    # se permite paginar en lugar de truncar la evidencia.
    disponibles=letter[1]-27-25-3
    conjunto=KeepInFrame(ancho,disponibles,flow,mode="shrink",hAlign="LEFT",vAlign="TOP")
    documento.build([conjunto])
    buffer.seek(0)
    return buffer
