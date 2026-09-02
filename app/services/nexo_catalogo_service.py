import hashlib
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz, process

    RAPIDFUZZ_DISPONIBLE = True
except ImportError:  # pragma: no cover - respaldo para despliegues sin dependencia actualizada
    fuzz = process = None
    RAPIDFUZZ_DISPONIBLE = False


VALORES_ESPECIALES = {
    "N A",
    "NA",
    "NO APLICA",
    "NO APLICABLE",
    "NINGUNO",
    "NINGUNA",
    "SIN DATO",
    "SIN INFORMACION",
}

HALLAZGOS_CATALOGO_LEGACY = {
    "Nuevos nombres de evento/reporte",
    "Tipos de anexo fuera del catálogo",
    "Tipos documentales no reconocidos por SICODE.IA",
}


def normalizar_catalogo(valor):
    texto = str(valor or "").strip().upper()
    texto = "".join(
        c
        for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _similitud(a, b):
    na = normalizar_catalogo(a)
    nb = normalizar_catalogo(b)
    if not na or not nb:
        return 0.0
    if RAPIDFUZZ_DISPONIBLE:
        return float(fuzz.WRatio(na, nb))
    return round(SequenceMatcher(None, na, nb).ratio() * 100, 2)


def _mejor_coincidencia(valor, catalogo):
    catalogo = [str(item).strip() for item in catalogo if str(item or "").strip()]
    if not catalogo:
        return None, 0.0

    normalizados = {item: normalizar_catalogo(item) for item in catalogo}
    consulta = normalizar_catalogo(valor)

    if RAPIDFUZZ_DISPONIBLE:
        resultado = process.extractOne(
            consulta,
            normalizados,
            scorer=fuzz.WRatio,
            processor=None,
        )
        if resultado:
            _texto_normalizado, score, clave_original = resultado
            return clave_original, float(score)

    mejor = max(catalogo, key=lambda item: _similitud(consulta, normalizados[item]))
    return mejor, _similitud(consulta, normalizados[mejor])


def _parece_texto_libre(valor):
    texto = str(valor or "").strip()
    normal = normalizar_catalogo(texto)
    palabras = normal.split()
    if not normal:
        return False

    conectores = {"SE", "AL", "DEL", "POR", "PARA", "CON", "QUE", "NO", "TENIAN", "TENIA"}
    conectores_presentes = sum(1 for p in palabras if p in conectores)
    return (
        len(texto) >= 58
        or len(palabras) >= 10
        or (len(palabras) >= 7 and conectores_presentes >= 2)
    )


def _resumen_texto_libre(valor, frecuencia):
    normal = normalizar_catalogo(valor)
    return {
        "valor": "[texto libre omitido]",
        "frecuencia": frecuencia,
        "clasificacion": "texto_libre_probable",
        "canonico": None,
        "similitud": 0.0,
        "accion": "mover_a_observaciones",
        "huella": hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16],
        "longitud": len(str(valor or "").strip()),
        "palabras": len(normal.split()),
        "contenido_omitido_privacidad": True,
    }


def _detectar_combinacion(valor, catalogo):
    normal = normalizar_catalogo(valor)
    if " Y " not in f" {normal} " and " / " not in str(valor or ""):
        return []

    partes = [
        p.strip()
        for p in re.split(r"\s+(?:Y|E)\s+|\s*/\s*", normal)
        if p.strip()
    ]
    if len(partes) < 2:
        return []

    coincidencias = []
    for parte in partes[:4]:
        canonico, score = _mejor_coincidencia(parte, catalogo)
        if canonico and score >= 76:
            coincidencias.append({"parte": parte, "canonico": canonico, "similitud": round(score, 1)})

    return coincidencias if len(coincidencias) >= 2 else []


def evaluar_valor_catalogo(valor, catalogo, frecuencia=1):
    """Clasifica un valor desconocido antes de sugerir ampliar un catálogo.

    No modifica registros. Devuelve una explicación técnica para que NEXO pueda
    diferenciar errores ortográficos, alias, texto libre, combinaciones y posibles
    categorías institucionales nuevas.
    """
    texto = str(valor or "").strip()
    normal = normalizar_catalogo(texto)
    frecuencia = max(1, int(frecuencia or 1))

    conocidos = {
        normalizar_catalogo(item): str(item).strip()
        for item in catalogo
        if str(item or "").strip()
    }
    if normal in conocidos:
        return {
            "valor": texto,
            "frecuencia": frecuencia,
            "clasificacion": "canonico",
            "canonico": conocidos[normal],
            "similitud": 100.0,
            "accion": "sin_cambio",
        }

    if normal in VALORES_ESPECIALES:
        return {
            "valor": texto,
            "frecuencia": frecuencia,
            "clasificacion": "valor_especial",
            "canonico": None,
            "similitud": 0.0,
            "accion": "no_promover_catalogo",
        }

    if _parece_texto_libre(texto):
        return _resumen_texto_libre(texto, frecuencia)

    combinacion = _detectar_combinacion(texto, catalogo)
    if combinacion:
        return {
            "valor": texto,
            "frecuencia": frecuencia,
            "clasificacion": "combinacion_categorias",
            "canonico": None,
            "similitud": max(x["similitud"] for x in combinacion),
            "accion": "separar_o_definir_regla",
            "componentes": combinacion,
        }

    canonico, score = _mejor_coincidencia(texto, catalogo)
    score = round(float(score or 0), 1)

    if canonico and score >= 93:
        clasificacion = "variante_ortografica"
        accion = "normalizar_a_canonico"
    elif canonico and score >= 82:
        clasificacion = "alias_probable"
        accion = "revisar_alias"
    elif frecuencia >= 5:
        clasificacion = "candidato_nueva_categoria"
        accion = "validar_categoria_institucional"
    else:
        clasificacion = "requiere_revision"
        accion = "revisar_manualmente"

    return {
        "valor": texto,
        "frecuencia": frecuencia,
        "clasificacion": clasificacion,
        "canonico": canonico,
        "similitud": score,
        "accion": accion,
    }


def evaluar_desconocidos(valores, catalogo, limite=12):
    conteo = Counter(str(v).strip() for v in valores if str(v or "").strip())
    evaluaciones = [
        evaluar_valor_catalogo(valor, catalogo, frecuencia=cantidad)
        for valor, cantidad in conteo.most_common(max(1, int(limite or 12)))
    ]
    prioridad = {
        "texto_libre_probable": 0,
        "variante_ortografica": 1,
        "alias_probable": 2,
        "combinacion_categorias": 3,
        "candidato_nueva_categoria": 4,
        "requiere_revision": 5,
        "valor_especial": 6,
        "canonico": 7,
    }
    evaluaciones.sort(
        key=lambda item: (
            prioridad.get(item["clasificacion"], 99),
            -int(item["frecuencia"]),
            item["valor"],
        )
    )
    return evaluaciones


def _hallazgo(categoria, titulo, detalle, recomendacion, prioridad="media", evidencia=None):
    base = f"NEXO_V2|{categoria}|{titulo}|{detalle}|{recomendacion}"
    return {
        "firma": hashlib.sha256(base.encode("utf-8")).hexdigest()[:20],
        "categoria": categoria,
        "titulo": titulo,
        "detalle": detalle,
        "recomendacion": recomendacion,
        "prioridad": prioridad,
        "evidencia": evidencia or {},
    }


def _hallazgos_evaluaciones(etiqueta, evaluaciones):
    salida = []
    normalizables = [
        item for item in evaluaciones
        if item["clasificacion"] in {"variante_ortografica", "alias_probable"}
    ]
    invalidos = [
        item for item in evaluaciones
        if item["clasificacion"] in {"texto_libre_probable", "valor_especial"}
    ]
    combinados = [item for item in evaluaciones if item["clasificacion"] == "combinacion_categorias"]
    candidatos = [
        item for item in evaluaciones
        if item["clasificacion"] in {"candidato_nueva_categoria", "requiere_revision"}
    ]

    if normalizables:
        ejemplos = []
        for item in normalizables[:5]:
            ejemplos.append(
                f"{item['valor']} → {item.get('canonico') or 'revisión'} "
                f"({item['similitud']:.0f}% de similitud)"
            )
        salida.append(_hallazgo(
            "normalizacion",
            f"Variantes y alias detectados en {etiqueta}",
            "NEXO encontró valores que probablemente representan categorías ya existentes: " + "; ".join(ejemplos) + ".",
            "Revisar y, si corresponde, normalizar al valor canónico en lugar de crear categorías duplicadas.",
            "media",
            {"evaluaciones": normalizables[:8]},
        ))

    if invalidos:
        textos_libres = sum(
            int(item["frecuencia"])
            for item in invalidos
            if item["clasificacion"] == "texto_libre_probable"
        )
        especiales = sum(
            int(item["frecuencia"])
            for item in invalidos
            if item["clasificacion"] == "valor_especial"
        )
        partes = []
        if textos_libres:
            partes.append(f"{textos_libres} registro(s) parecen contener texto libre en un campo de catálogo")
        if especiales:
            partes.append(f"{especiales} registro(s) usan valores especiales como 'No aplica'")
        salida.append(_hallazgo(
            "calidad_dato",
            f"Valores que no deben convertirse en categorías en {etiqueta}",
            ". ".join(partes) + ". El contenido libre se omitió de la memoria técnica por privacidad.",
            "Restringir el campo a catálogo/autocompletado y trasladar comentarios operativos al campo Observaciones.",
            "alta" if textos_libres else "media",
            {"evaluaciones": invalidos[:8]},
        ))

    if combinados:
        salida.append(_hallazgo(
            "catalogo",
            f"Combinaciones de categorías detectadas en {etiqueta}",
            f"NEXO encontró {len(combinados)} valor(es) que parecen combinar dos o más categorías existentes.",
            "Definir si deben separarse en varios campos/registros o crear una regla institucional explícita para la combinación.",
            "media",
            {"evaluaciones": combinados[:8]},
        ))

    if candidatos:
        frecuentes = [item for item in candidatos if int(item["frecuencia"]) >= 5]
        nombres = ", ".join(item["valor"] for item in (frecuentes or candidatos)[:6])
        salida.append(_hallazgo(
            "catalogo",
            f"Candidatos reales a ampliar el catálogo de {etiqueta}",
            "Después de descartar variantes, alias y texto libre, permanecen valores para revisión institucional: " + nombres + ".",
            "Validar con el responsable funcional cuáles son categorías oficiales antes de incorporarlas al catálogo y a SICODE.IA.",
            "alta" if sum(int(item["frecuencia"]) for item in frecuentes) >= 10 else "media",
            {"evaluaciones": candidatos[:10]},
        ))

    return salida


def enriquecer_analisis_catalogos(resultado):
    """Reemplaza hallazgos genéricos de catálogo por diagnósticos explicables.

    Esta función solo lee valores agregados del sistema. Nunca corrige datos de
    forma automática y omite de la salida cualquier texto libre probable.
    """
    from app import db
    from app.models.coordinacion import AnexoCoordinacion, ReporteMonitoreo
    from app.models.documento_expediente import DocumentoExpediente
    from app.services.analisis_documental_service import TIPOS_ANEXO, TIPOS_EVENTO
    from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE

    resultado = dict(resultado or {})
    hallazgos = [
        item
        for item in list(resultado.get("hallazgos") or [])
        if item.get("titulo") not in HALLAZGOS_CATALOGO_LEGACY
    ]

    fuentes = [
        (
            "eventos de monitoreo",
            [
                valor for (valor,) in db.session.query(ReporteMonitoreo.tipo_evento)
                .filter(ReporteMonitoreo.tipo_evento.isnot(None)).all()
            ],
            TIPOS_EVENTO,
        ),
        (
            "tipos de anexo",
            [
                valor for (valor,) in db.session.query(AnexoCoordinacion.tipo_anexo)
                .filter(AnexoCoordinacion.tipo_anexo.isnot(None)).all()
            ],
            TIPOS_ANEXO,
        ),
        (
            "tipos documentales",
            [
                valor for (valor,) in db.session.query(DocumentoExpediente.tipo_documento)
                .filter(DocumentoExpediente.tipo_documento.isnot(None)).all()
            ],
            TIPOS_DOCUMENTO_LOTE,
        ),
    ]

    resumen_catalogos = {}
    for etiqueta, valores, catalogo in fuentes:
        conocidos = {normalizar_catalogo(item) for item in catalogo}
        desconocidos = [
            valor for valor in valores
            if normalizar_catalogo(valor) not in conocidos
        ]
        evaluaciones = evaluar_desconocidos(desconocidos, catalogo, limite=14)
        resumen_catalogos[etiqueta] = {
            "valores_revisados": len(valores),
            "desconocidos": len(desconocidos),
            "evaluaciones": evaluaciones,
        }
        hallazgos.extend(_hallazgos_evaluaciones(etiqueta, evaluaciones))

    prioridad_peso = {"alta": 3, "media": 2, "baja": 1}
    hallazgos.sort(
        key=lambda item: (
            -prioridad_peso.get(item.get("prioridad"), 0),
            item.get("categoria") or "",
            item.get("titulo") or "",
        )
    )
    resultado["hallazgos"] = hallazgos[:20]
    resultado["hallazgos_total"] = len(resultado["hallazgos"])
    resultado["catalogos_inteligentes"] = resumen_catalogos
    resultado["motor_catalogos"] = resumen_motor_catalogos()
    if any(item.get("prioridad") == "alta" for item in resultado["hallazgos"]):
        resultado["estado"] = "requiere_revision"
    return resultado


def resumen_motor_catalogos():
    return {
        "nombre": "RapidFuzz" if RAPIDFUZZ_DISPONIBLE else "difflib",
        "modo": "normalización y similitud local",
        "disponible": True,
        "acelerado": RAPIDFUZZ_DISPONIBLE,
        "nota": (
            "RapidFuzz activo para detectar variantes, alias y errores ortográficos."
            if RAPIDFUZZ_DISPONIBLE
            else "Modo de compatibilidad activo; instale RapidFuzz para mayor precisión y rendimiento."
        ),
    }
