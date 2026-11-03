"""Boleta BSI con el mismo lenguaje visual que la constancia de mantenimiento."""
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

from app.services.constancia_mantenimiento_service import TITULO, CENTRO, encabezado, tabla

FECHA = lambda valor: valor.strftime("%d/%m/%Y %H:%M") if valor else "—"
ETIQUETAS = {"CUMPLE": "Cumple", "NO_CUMPLE": "No cumple",
             "NO_APLICA": "No aplica", "PENDIENTE": "Pendiente"}


def generar_boleta_seguridad(b):
    """Cada control y CVE quedan en el PDF, con observaciones y firmas."""
    memoria = BytesIO()
    documento = SimpleDocTemplate(memoria, pagesize=letter, leftMargin=28,
                                  rightMargin=28, topMargin=27, bottomMargin=25)
    ancho = letter[0] - 56
    d = b.datos_equipo or {}
    segundos = b.segundos()
    duracion = f"{segundos//3600:02d}:{segundos%3600//60:02d}:{segundos%60:02d}"
    contenidos = [
        Paragraph("SICODE-UCT", TITULO),
        Paragraph("COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS", CENTRO),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", CENTRO),
        Spacer(1, 5),
        Paragraph("<b>BOLETA DE SEGURIDAD INFORMÁTICA - CONTROL DE EQUIPO</b>", TITULO),
        Spacer(1, 7),
        tabla([
            ["Boleta: " + b.numero, "Técnico: " + b.tecnico.nombre, "Estado: " + b.estado],
            ["Inicio: " + FECHA(b.iniciado_en), "Cierre: " + FECHA(b.cerrado_en),
             "Duración: " + duracion],
        ], [ancho * .30, ancho * .39, ancho * .31]),
        Spacer(1, 5),
        encabezado("1. IDENTIFICACIÓN DEL EQUIPO", ancho),
        tabla([
            ["SICOIN", d.get("codigo") or "—", "Equipo", d.get("nombre") or "—"],
            ["Hostname", (b.versiones or {}).get("hostname") or "No registrado", "Fecha revisión", FECHA(b.creado_en)],
            ["Tipo", d.get("tipo") or "—", "Marca / modelo", (d.get("marca") or "—") + " / " + (d.get("modelo") or "—")],
            ["Serie", d.get("serie") or "—", "IP", d.get("ip_estatica") or "—"],
            ["Dependencia", d.get("area") or "—", "Ubicación", d.get("ubicacion") or "—"],
            ["Custodio", d.get("custodio") or "—", "Usuario habitual", d.get("usuario_habitual") or "—"],
        ], [ancho * .15, ancho * .35, ancho * .17, ancho * .33]),
        Spacer(1, 6),
        encabezado("VERSIONES Y TECNOLOGÍAS VERIFICADAS", ancho),
        tabla([
            [nombre, (b.versiones or {}).get("instalado_" + clave, "—"),
             (b.versiones or {}).get(clave) or "No registrada"]
            for clave, nombre in (
                ("sistema", "Sistema operativo"),
                ("chrome", "Google Chrome"), ("java", "Java / JavaFX"),
                ("python", "Python"), ("php", "PHP"), ("antivirus", "Antivirus"),
            )
        ], [ancho * .28, ancho * .20, ancho * .52]),
        Spacer(1, 6),
        encabezado("2. DIAGNÓSTICO / MOTIVO DE INSPECCIÓN", ancho),
        tabla([[b.diagnostico or "Sin diagnóstico adicional."]], [ancho]),
        Spacer(1, 7),
    ]
    grupos = {}
    orden = []
    for f in b.checklist:
        clave = f.get("grupo", "otro")
        if clave not in grupos:
            grupos[clave] = []
            orden.append((clave, f.get("grupo_nombre") or "Controles"))
        grupos[clave].append(f)
    for indice, (clave, nombre) in enumerate(orden, start=3):
        contenidos.append(encabezado(f"{indice}. {nombre.upper()}", ancho))
        filas = []
        for f in grupos[clave]:
            titulo = f.get("actividad") or "—"
            estado = ETIQUETAS.get(f.get("resultado"), "Pendiente")
            observacion = f.get("observacion") or "Sin observaciones."
            filas.append([titulo, estado, observacion])
        contenidos.append(tabla(filas, [ancho * .46, ancho * .16, ancho * .38]))
        contenidos.append(Spacer(1, 7))
    contenidos.extend([
        encabezado("RESULTADO FINAL Y ACCIONES", ancho),
        tabla([
            ["Resultado:", b.resultado_final or "—"],
            ["Requiere seguimiento:", "Sí" if b.requiere_seguimiento else "No"],
            ["Acciones realizadas:", b.acciones or "Sin acciones adicionales."],
        ], [ancho * .24, ancho * .76]),
        Spacer(1, 10),
        KeepTogether([
            tabla([
                ["USUARIO / RESPONSABLE", "TÉCNICO RESPONSABLE"],
                ["Firma: _________________________", "Firma: _________________________"],
                [d.get("usuario_habitual") or d.get("custodio") or "Nombre: _____________",
                 b.tecnico.nombre],
            ], [ancho / 2, ancho / 2]),
            Spacer(1, 5),
            Paragraph("Constancia administrativa generada por SICODE-UCT. "
                      "La verificación documenta resultados declarados por el técnico; "
                      "no equivale a un escaneo automático de vulnerabilidades.", CENTRO),
        ]),
    ])
    documento.build(contenidos)
    memoria.seek(0)
    return memoria
