"""Catálogo central de anexos de SICODE-UCT.

No almacena documentos; únicamente define metadatos operativos para simplificar
la captura y permitir que NEXO detecte tipos observados aún no incorporados al
catálogo oficial.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func

from app import db
from app.models.coordinacion import AnexoCoordinacion


CATEGORIAS_ANEXOS = [
    {
        "codigo": "MONITOREO",
        "titulo": "Monitoreo y alertas",
        "descripcion": "Reportes y eventos generados por el seguimiento telemático.",
        "icono": "radar",
        "tipos": [
            ("REPORTE_MONITOREO", "Reporte de monitoreo", "especial"),
            ("REPORTE_SALIDA_ZONA_INCLUSION", "Reporte de salida de zona de inclusión", "generico"),
            ("REPORTE_PROHIBIDO_ACERCARSE", "Reporte de prohibido acercarse", "generico"),
            ("REPORTE_ACCION", "Reporte de acción", "generico"),
            ("REPORTE_INCUMPLIMIENTO", "Reporte de incumplimiento", "generico"),
            ("REPORTE_PROXIMIDAD", "Reporte de proximidad", "generico"),
            ("REPORTE_ZONA_EXCLUSION", "Reporte de zona de exclusión", "generico"),
            ("REPORTE_APERTURA_CORREA", "Reporte de apertura de correa", "generico"),
            ("REPORTE_BATERIA_BAJA_30", "Reporte de batería baja 30%", "generico"),
            ("REPORTE_ZONA_PREVENCION", "Reporte de zona de prevención", "generico"),
            ("REPORTE_BATERIA_BAJA_12", "Reporte de batería baja 12%", "generico"),
            ("NO_COMUNICACION", "No comunicación", "generico"),
        ],
    },
    {
        "codigo": "RIESGO",
        "titulo": "Análisis y comportamiento",
        "descripcion": "Análisis especializados y solicitudes de comportamiento del SP.",
        "icono": "riesgo",
        "tipos": [
            ("ANALISIS_RIESGO", "Análisis de riesgo", "especial"),
            ("SOLICITUD_INFORME_COMPORTAMIENTO", "Solicitud de informe de comportamiento del SP", "generico"),
        ],
    },
    {
        "codigo": "NOTIFICACIONES",
        "titulo": "Notificaciones",
        "descripcion": "Notificaciones administrativas o judiciales relacionadas con el SP.",
        "icono": "notificacion",
        "tipos": [
            ("NOTIFICACION_MOVILIZACION", "Notificación de movilización", "generico"),
            ("NOTIFICACION_EXONERACION_PAGO", "Notificación de exoneración de pago", "generico"),
            ("NOTIFICACION_JUEZ", "Notificación del juez", "generico"),
            ("NOTIFICACION_CAMBIO_RESIDENCIA", "Notificación de cambio de residencia", "generico"),
            ("NOTIFICACION_CAMBIO_ZONAS", "Notificación de cambio de zonas", "generico"),
            ("NOTIFICACION_CAMBIO_JUZGADO", "Notificación de cambio de juzgado", "generico"),
        ],
    },
    {
        "codigo": "ZONAS",
        "titulo": "Zonas y medidas",
        "descripcion": "Cambios o ampliaciones de las zonas asociadas a la medida telemática.",
        "icono": "zona",
        "tipos": [
            ("AMPLIACION_ZONA_INCLUSION", "Ampliación de zona de inclusión", "generico"),
            ("CAMBIO_ZONAS", "Cambio de zonas", "generico"),
        ],
    },
    {
        "codigo": "JUDICIAL",
        "titulo": "Gestiones judiciales",
        "descripcion": "Eventos y gestiones originadas por juzgado o audiencia.",
        "icono": "judicial",
        "tipos": [
            ("CAMBIO_JUZGADO", "Cambio de juzgado", "generico"),
            ("PROGRAMACION_AUDIENCIA", "Programación de audiencia", "generico"),
            ("PRORROGA_DISPOSITIVO", "Prórroga del dispositivo", "generico"),
        ],
    },
    {
        "codigo": "REEMPLAZO",
        "titulo": "Reemplazo de componentes",
        "descripcion": "Registre una sola vez el evento y marque todos los componentes reemplazados.",
        "icono": "dispositivo",
        "tipos": [
            ("REEMPLAZO_COMPONENTES", "Reemplazo de componentes", "componentes"),
        ],
    },
    {
        "codigo": "OTROS",
        "titulo": "Otros anexos",
        "descripcion": "Para anexos válidos que todavía no formen parte del catálogo oficial.",
        "icono": "archivo",
        "tipos": [
            ("OTRO_ANEXO", "Otro tipo de anexo", "libre"),
        ],
    },
]

COMPONENTES_REEMPLAZO = [
    ("DCT", "DCT"),
    ("CORREA", "Correa"),
    ("CARGADOR", "Cargador"),
    ("BASE", "Base de cargador"),
    ("CARGADOR_INALAMBRICO", "Cargador inalámbrico"),
]


def normalizar(texto: str | None) -> str:
    valor = unicodedata.normalize("NFKD", (texto or "").strip().upper())
    valor = "".join(ch for ch in valor if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", valor).strip()


def catalogo_plano():
    salida = {}
    for categoria in CATEGORIAS_ANEXOS:
        for codigo, titulo, modo in categoria["tipos"]:
            salida[codigo] = {
                "codigo": codigo,
                "titulo": titulo,
                "modo": modo,
                "categoria": categoria["codigo"],
                "categoria_titulo": categoria["titulo"],
            }
    return salida


def descubrir_tipos_nexo(limite=12):
    """Detecta etiquetas históricas que NEXO debe proponer para revisión.

    No aprueba ni cambia el catálogo automáticamente: solo devuelve candidatos
    observados en los metadatos existentes y evita que un dato atípico altere el
    flujo institucional sin revisión humana.
    """
    conocidos = {normalizar(item["titulo"]) for item in catalogo_plano().values()}
    filas = (
        db.session.query(AnexoCoordinacion.tipo_anexo, func.count(AnexoCoordinacion.id))
        .filter(AnexoCoordinacion.tipo_anexo.isnot(None))
        .group_by(AnexoCoordinacion.tipo_anexo)
        .order_by(func.count(AnexoCoordinacion.id).desc())
        .limit(200)
        .all()
    )
    candidatos = []
    for etiqueta, cantidad in filas:
        etiqueta = (etiqueta or "").strip()
        if not etiqueta or normalizar(etiqueta) in conocidos:
            continue
        candidatos.append({"titulo": etiqueta, "registros": int(cantidad or 0)})
        if len(candidatos) >= limite:
            break
    return candidatos
