import re
import uuid
from collections import Counter
from difflib import SequenceMatcher

from app import db
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, ReporteMonitoreo
from app.models.documento_expediente import DocumentoExpediente
from app.services.analisis_documental_service import TIPOS_ANEXO, TIPOS_EVENTO
from app.services.lote_documental_service import TIPOS_DOCUMENTO_LOTE
from app.services.nexo_catalogo_service import evaluar_valor_catalogo, normalizar_catalogo


UMBRAL_AUTOCORRECCION_VISIBLE = 95
ACCION_BITACORA = "NEXO_AUTOCORRECCION_ORTOGRAFICA"
PALABRAS_FUNCIONALES = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "E"}


FUENTES_AUTOCORREGIBLES = (
    {
        "clave": "eventos_monitoreo",
        "etiqueta": "eventos de monitoreo",
        "modelo": ReporteMonitoreo,
        "campo": "tipo_evento",
        "catalogo": TIPOS_EVENTO,
    },
    {
        "clave": "tipos_anexo",
        "etiqueta": "tipos de anexo",
        "modelo": AnexoCoordinacion,
        "campo": "tipo_anexo",
        "catalogo": TIPOS_ANEXO,
    },
    {
        "clave": "tipos_documentales",
        "etiqueta": "tipos documentales",
        "modelo": DocumentoExpediente,
        "campo": "tipo_documento",
        "catalogo": TIPOS_DOCUMENTO_LOTE,
    },
)


def _numeros_significativos(valor):
    """Extrae números que nunca deben cambiar durante una autocorrección."""
    texto = str(valor or "").replace(",", ".")
    return tuple(re.findall(r"\d+(?:\.\d+)?", texto))


def _numeros_compatibles(valor, canonico):
    """Si alguno contiene números, ambos deben contener exactamente los mismos."""
    origen = _numeros_significativos(valor)
    destino = _numeros_significativos(canonico)
    if not origen and not destino:
        return True
    return origen == destino


def _tokens_contenido(valor):
    return [
        token
        for token in normalizar_catalogo(valor).split()
        if token not in PALABRAS_FUNCIONALES
    ]


def _estructura_ortografica_compatible(valor, canonico):
    """Evita confundir una variante ortográfica con un alias semántico.

    Se permiten tildes, mayúsculas, signos, espacios y palabras funcionales. Tras
    retirar esas palabras, ambos valores deben conservar la misma cantidad de
    palabras de contenido y cada par debe ser igual o una variación tipográfica
    razonablemente cercana. Así, "Victim Proximity GPS" no se autocorrige a
    "Victim Proximity" aunque RapidFuzz le otorgue 95%.
    """
    normal_origen = normalizar_catalogo(valor)
    normal_destino = normalizar_catalogo(canonico)
    if normal_origen == normal_destino:
        return True

    origen = _tokens_contenido(valor)
    destino = _tokens_contenido(canonico)
    if not origen or len(origen) != len(destino):
        return False

    diferencias = 0
    for izquierda, derecha in zip(origen, destino):
        if izquierda == derecha:
            continue
        diferencias += 1
        if diferencias > 2:
            return False
        similitud_token = SequenceMatcher(None, izquierda, derecha).ratio()
        if similitud_token < 0.72:
            return False
    return diferencias >= 1


def _evaluacion_equivalente_exacta(valor, canonico, frecuencia):
    return {
        "valor": str(valor or "").strip(),
        "frecuencia": int(frecuencia or 1),
        "clasificacion": "variante_ortografica",
        "canonico": canonico,
        "similitud": 100.0,
        "confianza_visible": 100,
        "accion": "autocorregir_ortografia",
        "motivo": "equivalencia_normalizada_exacta",
    }


def es_correccion_ortografica_segura(evaluacion):
    """Autoriza solo variantes ortográficas reales con confianza visible >=95%."""
    evaluacion = dict(evaluacion or {})
    if evaluacion.get("clasificacion") != "variante_ortografica":
        return False

    valor = str(evaluacion.get("valor") or "").strip()
    canonico = str(evaluacion.get("canonico") or "").strip()
    if not valor or not canonico or valor == canonico:
        return False

    similitud = float(evaluacion.get("similitud") or 0.0)
    confianza_visible = int(round(similitud))
    if confianza_visible < UMBRAL_AUTOCORRECCION_VISIBLE:
        return False
    if not _numeros_compatibles(valor, canonico):
        return False
    return _estructura_ortografica_compatible(valor, canonico)


def proponer_correcciones_valores(valores, catalogo):
    """Devuelve correcciones seguras sin tocar la base de datos."""
    conteo = Counter(str(v).strip() for v in valores if str(v or "").strip())
    canonicos = {
        normalizar_catalogo(item): str(item).strip()
        for item in catalogo
        if str(item or "").strip()
    }

    propuestas = []
    for valor, frecuencia in conteo.items():
        normal = normalizar_catalogo(valor)
        canonico_exacto = canonicos.get(normal)

        # Misma forma normalizada: corrige mayúsculas, tildes, signos o espacios
        # hacia el valor institucional oficial con confianza 100%.
        if canonico_exacto and valor != canonico_exacto:
            evaluacion = _evaluacion_equivalente_exacta(valor, canonico_exacto, frecuencia)
        elif canonico_exacto:
            continue
        else:
            evaluacion = evaluar_valor_catalogo(valor, catalogo, frecuencia=frecuencia)
            evaluacion["confianza_visible"] = int(round(float(evaluacion.get("similitud") or 0.0)))

        if es_correccion_ortografica_segura(evaluacion):
            propuestas.append(evaluacion)

    propuestas.sort(key=lambda item: (-int(item["frecuencia"]), item["valor"]))
    return propuestas


def vista_previa_autocorreccion():
    """Cuenta qué corregiría NEXO sin modificar registros."""
    salida = []
    total_registros = 0
    for fuente in FUENTES_AUTOCORREGIBLES:
        modelo = fuente["modelo"]
        campo = getattr(modelo, fuente["campo"])
        valores = [
            valor for (valor,) in db.session.query(campo).filter(campo.isnot(None)).all()
        ]
        propuestas = proponer_correcciones_valores(valores, fuente["catalogo"])
        if propuestas:
            registros = sum(int(item["frecuencia"]) for item in propuestas)
            total_registros += registros
            salida.append({
                "clave": fuente["clave"],
                "etiqueta": fuente["etiqueta"],
                "registros": registros,
                "propuestas": propuestas,
            })
    return {
        "umbral_visible": UMBRAL_AUTOCORRECCION_VISIBLE,
        "registros_corregibles": total_registros,
        "catalogos": salida,
    }


def aplicar_autocorreccion_ortografica(usuario_id=None):
    """Normaliza únicamente errores ortográficos seguros y deja trazabilidad.

    No corrige alias, texto libre, categorías nuevas, combinaciones ni valores con
    números distintos. Cada grupo conserva los IDs afectados en Bitácora para que
    la operación sea auditable y técnicamente reversible.
    """
    lote_id = uuid.uuid4().hex[:20]
    correcciones = []
    total = 0

    for fuente in FUENTES_AUTOCORREGIBLES:
        modelo = fuente["modelo"]
        nombre_campo = fuente["campo"]
        columna = getattr(modelo, nombre_campo)
        valores = [
            valor for (valor,) in db.session.query(columna).filter(columna.isnot(None)).all()
        ]
        propuestas = proponer_correcciones_valores(valores, fuente["catalogo"])

        for propuesta in propuestas:
            anterior = propuesta["valor"]
            canonico = propuesta["canonico"]
            filas = modelo.query.filter(columna == anterior).all()
            if not filas:
                continue

            ids = [int(fila.id) for fila in filas]
            for fila in filas:
                setattr(fila, nombre_campo, canonico)

            cantidad = len(ids)
            total += cantidad
            correcciones.append({
                "catalogo": fuente["etiqueta"],
                "campo": nombre_campo,
                "anterior": anterior,
                "canonico": canonico,
                "similitud": float(propuesta.get("similitud") or 0.0),
                "confianza_visible": int(propuesta.get("confianza_visible") or 0),
                "registros": cantidad,
            })

            db.session.add(Bitacora(
                usuario_id=usuario_id,
                accion=ACCION_BITACORA,
                modulo="NEXO",
                descripcion=(
                    f"NEXO corrigió {cantidad} registro(s) de {fuente['etiqueta']}: "
                    f"“{anterior}” → “{canonico}” con confianza visible "
                    f"{int(propuesta.get('confianza_visible') or 0)}%."
                ),
                entidad=modelo.__name__,
                entidad_id=lote_id,
                datos_anteriores={
                    "campo": nombre_campo,
                    "valor": anterior,
                    "ids": ids,
                },
                datos_posteriores={
                    "campo": nombre_campo,
                    "valor": canonico,
                    "similitud": float(propuesta.get("similitud") or 0.0),
                    "confianza_visible": int(propuesta.get("confianza_visible") or 0),
                    "umbral": UMBRAL_AUTOCORRECCION_VISIBLE,
                    "registros": cantidad,
                    "solo_catalogo": True,
                    "estructura_ortografica_validada": True,
                },
                motivo=(
                    "Autocorrección ortográfica NEXO autorizada únicamente para "
                    "variante_ortografica con confianza visible >=95%, números compatibles "
                    "y estructura tipográfica compatible."
                ),
            ))

    if total:
        db.session.commit()

    return {
        "lote_id": lote_id if total else None,
        "registros_corregidos": total,
        "correcciones": correcciones,
        "umbral_visible": UMBRAL_AUTOCORRECCION_VISIBLE,
    }
