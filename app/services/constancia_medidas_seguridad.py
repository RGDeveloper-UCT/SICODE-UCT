"""Constancia diferenciada de medidas prioritarias y temporales (mismo folio BSI)."""
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
from app.services.constancia_mantenimiento_service import TITULO, CENTRO, encabezado, tabla
from app.services.constancia_seguridad_service import ETIQUETAS, FECHA


def generar_boleta_medidas(b):
    memoria = BytesIO()
    ancho = letter[0] - 56
    documento = SimpleDocTemplate(memoria, pagesize=letter, leftMargin=28,
                                  rightMargin=28, topMargin=27, bottomMargin=25)
    datos = b.datos_equipo or {}
    tiempo = b.segundos()
    duracion = f"{tiempo//3600:02d}:{tiempo%3600//60:02d}:{tiempo%60:02d}"
    cumplidos = sum(f["resultado"] == "CUMPLE" for f in b.checklist)
    pendientes = sum(f["resultado"] == "NO_CUMPLE" for f in b.checklist)
    sin_aplicar = sum(f["resultado"] == "NO_APLICA" for f in b.checklist)
    flujo = [
        Paragraph("SICODE-UCT", TITULO),
        Paragraph("COORDINACIÓN DE SISTEMATIZACIÓN Y ORDENAMIENTO DE DATOS", CENTRO),
        Paragraph("UNIDAD DE CONTROL TELEMÁTICO", CENTRO),
        Spacer(1, 5),
        Paragraph("<b>BOLETA DE MEDIDAS PRIORITARIAS Y TEMPORALES</b>", TITULO),
        Paragraph("Seguridad Informática · recomendaciones CERT/MINGOB · octubre 2026", CENTRO),
        Spacer(1, 7),
        tabla([
            ["Folio: " + b.numero, "Responsable técnico: " + b.tecnico.nombre, "Estado: " + b.estado],
            ["Inicio: " + FECHA(b.iniciado_en), "Cierre: " + FECHA(b.cerrado_en),
             "Duración: " + duracion],
        ], [ancho * .26, ancho * .43, ancho * .31]),
        Spacer(1, 6),
        encabezado("1. IDENTIFICACIÓN DEL EQUIPO INSTITUCIONAL", ancho),
        tabla([
            ["SICOIN", datos.get("codigo") or "—", "Equipo", datos.get("nombre") or "—"],
            ["Tipo", datos.get("tipo") or "—", "Marca / modelo",
             (datos.get("marca") or "—") + " / " + (datos.get("modelo") or "—")],
            ["Área", datos.get("area") or "—", "Responsable",
             datos.get("usuario_habitual") or datos.get("custodio") or "—"],
        ], [ancho*.13, ancho*.35, ancho*.17, ancho*.35]),
        Spacer(1, 6),
        encabezado("2. TECNOLOGÍAS IDENTIFICADAS", ancho),
        tabla([
            [nombre, (b.versiones or {}).get("instalado_" + clave) or "NO_VERIFICADO",
             (b.versiones or {}).get(clave) or "Versión no consignada"]
            for clave, nombre in (("chrome", "Chrome"), ("java", "Java / JavaFX"),
                                  ("python", "Python"), ("php", "PHP"))
        ], [ancho*.27, ancho*.28, ancho*.45]),
        Spacer(1, 6),
        encabezado("3. MOTIVO DE REVISIÓN Y DIAGNÓSTICO", ancho),
        tabla([[b.diagnostico or "Revisión de medidas recomendadas por CERT/MINGOB."]], [ancho]),
        Spacer(1, 6),
    ]
    grupos = []
    por_grupo = {}
    for f in b.checklist:
        clave = f.get("grupo", "otro")
        if clave not in por_grupo:
            grupos.append((clave, f.get("grupo_nombre", "Medidas")))
            por_grupo[clave] = []
        por_grupo[clave].append(f)
    for index, (clave, nombre) in enumerate(grupos, start=4):
        flujo.extend([
            encabezado(f"{index}. {nombre.upper()}", ancho),
            tabla([
                [f.get("actividad") or "—",
                 ETIQUETAS.get(f.get("resultado"), "Pendiente"),
                 f.get("observacion") or "Sin observaciones"]
                for f in por_grupo[clave]
            ], [ancho*.46, ancho*.16, ancho*.38]),
            Spacer(1, 7),
        ])
    flujo.extend([
        encabezado("RESUMEN Y CIERRE DE MEDIDAS", ancho),
        tabla([
            ["Aplicadas/verificadas", str(cumplidos), "Pendientes", str(pendientes)],
            ["No aplica", str(sin_aplicar), "Total medidas", str(len(b.checklist))],
            ["Resultado final", b.resultado_final or "—",
             "Seguimiento", "Sí" if b.requiere_seguimiento else "No"],
        ], [ancho*.28, ancho*.22, ancho*.25, ancho*.25]),
        Spacer(1, 4),
        tabla([["Acciones realizadas y medidas pendientes", b.acciones or "Sin acciones adicionales."]],
              [ancho*.30, ancho*.70]),
        Spacer(1, 8),
        KeepTogether([
            tabla([
                ["USUARIO / RESPONSABLE", "TÉCNICO RESPONSABLE"],
                ["Firma: __________________________", "Firma: __________________________"],
                [datos.get("usuario_habitual") or datos.get("custodio") or "Nombre: ______________",
                 b.tecnico.nombre],
            ], [ancho*.5, ancho*.5]),
            Spacer(1, 4),
            Paragraph("Registro documental de medidas CERT/MINGOB; no equivale a un escaneo "
                      "de vulnerabilidades ni autoriza cambios de servidores sin aprobación.", CENTRO),
        ]),
    ])
    documento.build(flujo)
    memoria.seek(0)
    return memoria
