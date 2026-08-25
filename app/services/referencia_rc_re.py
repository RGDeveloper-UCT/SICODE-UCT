import re
import unicodedata
from collections import Counter


def _sin_acentos(valor):
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caracter)
    )


def _normalizar(texto):
    texto = _sin_acentos(texto).upper().replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto


def _buscar_tipo(texto, tipo):
    # Exige que RC/RE sea una etiqueta independiente. El lookahead evita que
    # "RE" se confunda con palabras como REPORTE, RESOLUCION o RECEPCION.
    letras = r"R\s*\.?\s*C\.?" if tipo == "RC" else r"R\s*\.?\s*E\."
    if tipo == "RE":
        letras = r"R\s*\.?\s*E\.?(?![A-Z])"
    else:
        letras = r"R\s*\.?\s*C\.?(?![A-Z])"
    patron = re.compile(
        rf"(?<![A-Z0-9]){letras}\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*"
        rf"([A-Z0-9][A-Z0-9./_-]{{1,80}})",
        flags=re.IGNORECASE,
    )
    return [(m.start(), m.group(1).strip().upper()) for m in patron.finditer(texto)]


def detectar_referencia_rc_re(texto_original):
    """Detecta si la referencia administrativa visible es RC o RE.

    Devuelve un diccionario pequeño para poder reutilizarlo en SICODE.IA sin
    cambiar el esquema actual de base de datos. El valor continúa viajando en
    el campo histórico ``rc`` por compatibilidad; ``tipo_referencia`` conserva
    si el documento decía RC o RE.
    """
    texto = _normalizar(texto_original)
    candidatos = []
    for tipo in ("RC", "RE"):
        candidatos.extend((pos, tipo, valor) for pos, valor in _buscar_tipo(texto, tipo))

    if not candidatos:
        return {"tipo": None, "valor": None, "confianza": 0.0, "ambigua": False}

    candidatos.sort(key=lambda item: item[0])
    conteo = Counter((tipo, valor) for _, tipo, valor in candidatos)
    tipo, valor = candidatos[0][1], candidatos[0][2]
    repeticiones = conteo[(tipo, valor)]
    tipos_presentes = {item[1] for item in candidatos}
    confianza = 0.98 if repeticiones > 1 else 0.94
    if len(tipos_presentes) > 1:
        confianza = min(confianza, 0.86)

    return {
        "tipo": tipo,
        "valor": valor,
        "confianza": confianza,
        "ambigua": len(tipos_presentes) > 1,
    }


def instalar_deteccion_rc_re():
    """Integra RC/RE sobre los extractores ya cargados sin romper compatibilidad."""
    from app.services import analisis_documental_service as servicio

    if getattr(servicio, "_sicode_rc_re_instalado", False):
        return

    original = servicio.extraer_metadatos

    def extraer_metadatos_rc_re(texto_original, paginas_pdf, tipo_objetivo="AUTO"):
        datos, confianzas, advertencias = original(
            texto_original,
            paginas_pdf,
            tipo_objetivo=tipo_objetivo,
        )
        referencia = detectar_referencia_rc_re(texto_original)
        if referencia["valor"]:
            datos["rc"] = referencia["valor"]
            datos["tipo_referencia"] = referencia["tipo"]
            confianzas["rc"] = max(float(confianzas.get("rc") or 0), referencia["confianza"])
            confianzas["tipo_referencia"] = referencia["confianza"]
            if referencia["ambigua"]:
                advertencias.append(
                    "Se detectaron etiquetas RC y RE en la misma pieza; SICODE.IA tomó la primera referencia visible y requiere revisión humana."
                )
        else:
            datos.setdefault("tipo_referencia", "RC" if datos.get("rc") else None)
            confianzas.setdefault("tipo_referencia", float(confianzas.get("rc") or 0))
        return datos, confianzas, advertencias

    servicio.extraer_metadatos = extraer_metadatos_rc_re
    servicio._sicode_rc_re_instalado = True

    # lote_documental_service importó la función directamente. Si ya está
    # cargado, sustituimos también esa referencia para que SICODE.IA por lotes
    # use la detección nueva de inmediato.
    try:
        from app.services import lote_documental_service as lote
        lote.extraer_metadatos = extraer_metadatos_rc_re
    except Exception:
        pass
