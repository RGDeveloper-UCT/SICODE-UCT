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
        return {
            "valor": texto,
            "frecuencia": frecuencia,
            "clasificacion": "texto_libre_probable",
            "canonico": None,
            "similitud": 0.0,
            "accion": "mover_a_observaciones",
        }

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
