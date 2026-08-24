import json
import math
import re
import shutil
import time
from urllib import error as urllib_error
from urllib import request as urllib_request


CAMPOS_IA = (
    "tipo_registro",
    "no_sp",
    "rc",
    "providencia",
    "fecha_recepcion",
    "folios",
    "folio_inicio",
    "folio_fin",
    "total_folios",
    "numero_anexo",
    "titulo_anexo",
    "tipo_anexo",
    "boleta",
    "total",
    "periodo_texto",
    "numero_reporte",
    "tipo_evento",
    "tipo_documento",
    "descripcion",
)

CAMPOS_ENTEROS = {"folio_inicio", "folio_fin", "total_folios"}
CAMPOS_NUMERICOS_TEXTO = {"total"}


class IAAnalisisNoDisponible(RuntimeError):
    pass


def _clamp(valor, minimo=0.0, maximo=1.0):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return minimo
    return max(minimo, min(maximo, numero))


def _limpiar_texto(valor, limite=220):
    if valor is None:
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return texto[:limite] if texto else None


def _normalizado_comparacion(valor):
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = re.sub(r"\s+", "", texto)
    texto = texto.replace("–", "-").replace("—", "-")
    return texto


def resolver_tesseract(configurado=None):
    """Localiza Tesseract incluso cuando systemd expone un PATH mínimo."""
    candidatos = []
    if configurado:
        candidatos.append(str(configurado).strip())
    encontrado = shutil.which("tesseract")
    if encontrado:
        candidatos.append(encontrado)
    candidatos.extend(("/usr/bin/tesseract", "/usr/local/bin/tesseract", "/bin/tesseract"))

    for candidato in candidatos:
        if not candidato:
            continue
        try:
            from pathlib import Path

            ruta = Path(candidato)
            if ruta.is_file():
                return str(ruta)
        except OSError:
            continue
    return None


def _texto_y_confianza_desde_data(datos):
    textos = datos.get("text") or []
    confs = datos.get("conf") or []
    bloques = datos.get("block_num") or [0] * len(textos)
    parrafos = datos.get("par_num") or [0] * len(textos)
    lineas = datos.get("line_num") or list(range(len(textos)))

    grupos = {}
    confianzas = []
    for indice, palabra in enumerate(textos):
        palabra = str(palabra or "").strip()
        if not palabra:
            continue
        try:
            confianza = float(confs[indice])
        except (TypeError, ValueError, IndexError):
            confianza = -1
        clave = (
            bloques[indice] if indice < len(bloques) else 0,
            parrafos[indice] if indice < len(parrafos) else 0,
            lineas[indice] if indice < len(lineas) else indice,
        )
        grupos.setdefault(clave, []).append(palabra)
        if confianza >= 0:
            confianzas.append(confianza)

    texto = "\n".join(" ".join(grupos[clave]) for clave in sorted(grupos))
    confianza_media = sum(confianzas) / len(confianzas) if confianzas else 0.0
    return texto.strip(), confianza_media


def preprocesar_imagen_ocr(imagen):
    """Mejora contraste y nitidez sin conservar una copia de la página."""
    try:
        from PIL import ImageFilter, ImageOps
    except ImportError as exc:
        raise RuntimeError("Falta Pillow para mejorar las páginas antes del OCR.") from exc

    gris = ImageOps.grayscale(imagen)
    gris = ImageOps.autocontrast(gris, cutoff=1)

    ancho, alto = gris.size
    if ancho < 1800:
        factor = min(1.35, 1800 / max(ancho, 1))
        if factor > 1.05:
            gris = gris.resize((int(ancho * factor), int(alto * factor)))

    gris = gris.filter(ImageFilter.UnsharpMask(radius=1.2, percent=165, threshold=3))
    return gris


def ocr_pagina_multipase(
    imagen,
    *,
    idioma="spa",
    tesseract_cmd=None,
    segunda_pasada=True,
    timeout=60,
):
    """Ejecuta OCR local y selecciona la pasada con mejor confianza."""
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("Falta pytesseract para analizar páginas escaneadas.") from exc

    comando = resolver_tesseract(tesseract_cmd)
    if not comando:
        raise IAAnalisisNoDisponible("Tesseract OCR no está disponible en el servidor.")
    pytesseract.pytesseract.tesseract_cmd = comando

    procesada = preprocesar_imagen_ocr(imagen)
    configuraciones = [("PSM6", "--oem 3 --psm 6")]
    if segunda_pasada:
        configuraciones.append(("PSM4", "--oem 3 --psm 4"))

    candidatos = []
    try:
        for nombre, configuracion in configuraciones:
            try:
                datos = pytesseract.image_to_data(
                    procesada,
                    lang=idioma,
                    config=configuracion,
                    output_type=Output.DICT,
                    timeout=timeout,
                )
            except RuntimeError:
                continue
            texto, confianza = _texto_y_confianza_desde_data(datos)
            caracteres = len(re.sub(r"\W", "", texto, flags=re.UNICODE))
            # La longitud evita escoger una lectura vacía con confianza engañosa.
            bonificacion = min(caracteres / 700.0, 1.0) * 4.0
            candidatos.append(
                {
                    "texto": texto,
                    "confianza": max(0.0, min(100.0, confianza)),
                    "modo": nombre,
                    "puntaje": confianza + bonificacion,
                    "caracteres": caracteres,
                }
            )
            if confianza >= 86 and caracteres >= 80:
                break
    finally:
        try:
            procesada.close()
        except Exception:
            pass

    if not candidatos:
        return {"texto": "", "confianza": 0.0, "modo": "SIN_LECTURA", "caracteres": 0}
    mejor = max(candidatos, key=lambda item: item["puntaje"])
    mejor.pop("puntaje", None)
    return mejor


def _prompt_ia(tipo_objetivo, datos_reglas, tipos_anexo, tipos_evento):
    candidatos = {campo: datos_reglas.get(campo) for campo in CAMPOS_IA if datos_reglas.get(campo) is not None}
    return f"""Eres un extractor documental local de SICODE-UCT. Analizas texto OCR imperfecto de documentos administrativos. Tu función es interpretar errores de OCR y proponer SOLO metadatos administrativos. No inventes datos. Si un valor no está respaldado por el texto, usa null. No describas personas, delitos ni contenido sensible. Responde únicamente JSON válido.

Tipo esperado por el usuario: {tipo_objetivo}
Candidatos encontrados por reglas determinísticas: {json.dumps(candidatos, ensure_ascii=False)}
Tipos de anexo válidos: {json.dumps(tipos_anexo, ensure_ascii=False)}
Tipos de evento conocidos: {json.dumps(tipos_evento, ensure_ascii=False)}

Formato obligatorio:
{{
  "campos": {{
    "tipo_registro": {{"valor": "ANEXO|INSTALACION|DESINSTALACION|PAGO|MONITOREO|null", "confianza": 0.0}},
    "no_sp": {{"valor": "numero|null", "confianza": 0.0}},
    "rc": {{"valor": "texto|null", "confianza": 0.0}},
    "providencia": {{"valor": "texto|null", "confianza": 0.0}},
    "fecha_recepcion": {{"valor": "YYYY-MM-DD|null", "confianza": 0.0}},
    "folios": {{"valor": "total o rango|null", "confianza": 0.0}},
    "folio_inicio": {{"valor": 0, "confianza": 0.0}},
    "folio_fin": {{"valor": 0, "confianza": 0.0}},
    "total_folios": {{"valor": 0, "confianza": 0.0}},
    "numero_anexo": {{"valor": "texto|null", "confianza": 0.0}},
    "titulo_anexo": {{"valor": "texto|null", "confianza": 0.0}},
    "tipo_anexo": {{"valor": "texto|null", "confianza": 0.0}},
    "boleta": {{"valor": "texto|null", "confianza": 0.0}},
    "total": {{"valor": "numero|null", "confianza": 0.0}},
    "periodo_texto": {{"valor": "texto|null", "confianza": 0.0}},
    "numero_reporte": {{"valor": "texto|null", "confianza": 0.0}},
    "tipo_evento": {{"valor": "texto|null", "confianza": 0.0}},
    "tipo_documento": {{"valor": "PROVIDENCIA|OFICIO|INFORME|null", "confianza": 0.0}},
    "descripcion": {{"valor": "texto|null", "confianza": 0.0}}
  }}
}}

Reglas críticas: una confianza debe estar entre 0 y 1. No conviertas el número de páginas PDF en folios. No completes un SP por semejanza si no aparece en el texto. No corrijas números únicamente porque "parecen" plausibles. La IA solo propone; un usuario validará después."""


def _sanitizar_valor_ia(campo, valor):
    if valor in (None, "", "null", "NULL"):
        return None
    if campo in CAMPOS_ENTEROS:
        try:
            numero = int(str(valor).strip())
        except (TypeError, ValueError):
            return None
        return numero if numero > 0 else None
    if campo == "tipo_registro":
        texto = str(valor).strip().upper().replace(" ", "_")
        return texto if texto in {"ANEXO", "INSTALACION", "DESINSTALACION", "PAGO", "MONITOREO"} else None
    if campo == "tipo_documento":
        texto = str(valor).strip().upper()
        return texto if texto in {"PROVIDENCIA", "OFICIO", "INFORME"} else None
    limite = 180 if campo in {"titulo_anexo", "tipo_evento", "descripcion"} else 120
    if campo == "no_sp":
        limite = 50
    return _limpiar_texto(valor, limite)


def consultar_ia_local(
    texto,
    datos_reglas,
    *,
    tipo_objetivo="AUTO",
    tipos_anexo=None,
    tipos_evento=None,
    base_url="http://127.0.0.1:11434",
    modelo="qwen3:1.7b",
    timeout=90,
    max_chars=24000,
):
    """Consulta Ollama por loopback y devuelve únicamente campos saneados."""
    inicio = time.perf_counter()
    texto = str(texto or "")
    if not texto.strip():
        raise IAAnalisisNoDisponible("No hay texto OCR suficiente para consultar la IA local.")

    texto_limitado = texto[: max(int(max_chars or 24000), 2000)]
    payload = {
        "model": modelo,
        "messages": [
            {
                "role": "system",
                "content": _prompt_ia(
                    tipo_objetivo,
                    datos_reglas,
                    tipos_anexo or [],
                    tipos_evento or [],
                ),
            },
            {"role": "user", "content": "TEXTO OCR TEMPORAL:\n" + texto_limitado},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    req = urllib_request.Request(
        f"{str(base_url).rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=float(timeout)) as respuesta:
            cuerpo = json.loads(respuesta.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise IAAnalisisNoDisponible("Ollama local no respondió al análisis documental.") from exc

    contenido = ((cuerpo.get("message") or {}).get("content") or "").strip()
    if not contenido:
        raise IAAnalisisNoDisponible("Ollama devolvió una respuesta vacía.")
    try:
        bruto = json.loads(contenido)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise IAAnalisisNoDisponible("Ollama no devolvió JSON válido.") from exc

    campos_brutos = bruto.get("campos") if isinstance(bruto, dict) else None
    if not isinstance(campos_brutos, dict):
        raise IAAnalisisNoDisponible("Ollama no devolvió el esquema documental esperado.")

    campos = {}
    for campo in CAMPOS_IA:
        entrada = campos_brutos.get(campo)
        if isinstance(entrada, dict):
            valor = _sanitizar_valor_ia(campo, entrada.get("valor"))
            confianza = _clamp(entrada.get("confianza"), 0.0, 1.0)
        else:
            valor, confianza = None, 0.0
        if valor is not None:
            campos[campo] = {"valor": valor, "confianza": confianza}

    return {
        "campos": campos,
        "modelo": str(modelo)[:80],
        "duracion_ms": int((time.perf_counter() - inicio) * 1000),
        "texto_enviado_chars": len(texto_limitado),
    }


def fusionar_reglas_e_ia(datos_reglas, confianzas_reglas, resultado_ia=None):
    """Fusiona reglas e IA favoreciendo evidencia determinística y desacuerdos visibles."""
    datos = dict(datos_reglas or {})
    confianzas = {clave: _clamp(valor) for clave, valor in (confianzas_reglas or {}).items()}
    fuentes = {}
    explicaciones = {}
    advertencias = []

    for campo, valor in datos.items():
        if valor is not None and campo in CAMPOS_IA:
            fuentes[campo] = ["OCR + reglas"]
            explicaciones[campo] = "Valor propuesto por extracción determinística del texto leído."

    campos_ia = (resultado_ia or {}).get("campos") or {}
    for campo, entrada in campos_ia.items():
        if campo not in CAMPOS_IA or not isinstance(entrada, dict):
            continue
        valor_ia = entrada.get("valor")
        conf_ia = _clamp(entrada.get("confianza"), 0.0, 0.96)
        if valor_ia is None:
            continue

        valor_regla = datos.get(campo)
        conf_regla = _clamp(confianzas.get(campo, 0.0))
        coincide = valor_regla is not None and _normalizado_comparacion(valor_regla) == _normalizado_comparacion(valor_ia)

        if coincide:
            confianzas[campo] = min(0.99, max(conf_regla, conf_ia) + 0.06)
            fuentes[campo] = ["OCR + reglas", "IA local"]
            explicaciones[campo] = "OCR/reglas e IA local coincidieron en la propuesta."
            continue

        if valor_regla is None:
            # La IA puede recuperar contexto perdido por OCR/reglas, pero nunca recibe confianza plena.
            datos[campo] = valor_ia
            confianzas[campo] = min(0.82, conf_ia * 0.88)
            fuentes[campo] = ["IA local"]
            explicaciones[campo] = "La IA local interpretó el OCR; requiere validación humana."
            continue

        if conf_regla < 0.62 and conf_ia >= 0.88:
            datos[campo] = valor_ia
            confianzas[campo] = min(0.78, conf_ia * 0.86)
            fuentes[campo] = ["IA local", "OCR dudoso"]
            explicaciones[campo] = "La IA local prevaleció sobre una lectura OCR de baja confianza; revise el documento."
        else:
            confianzas[campo] = max(0.20, conf_regla - 0.16)
            fuentes[campo] = ["OCR + reglas", "IA local (difiere)"]
            explicaciones[campo] = "OCR/reglas e IA local produjeron valores distintos; se conservó la lectura determinística para revisión."
        advertencias.append(f"Reglas e IA local difieren en el campo {campo.replace('_', ' ')}; revise ese dato antes de confirmar.")

    inicio = datos.get("folio_inicio")
    fin = datos.get("folio_fin")
    try:
        if inicio is not None and fin is not None and int(inicio) >= 1 and int(fin) >= int(inicio):
            total = int(fin) - int(inicio) + 1
            datos["total_folios"] = total
            if not datos.get("folios"):
                datos["folios"] = str(total)
            conf_rango = min(
                _clamp(confianzas.get("folio_inicio", confianzas.get("folios", 0.0))),
                _clamp(confianzas.get("folio_fin", confianzas.get("folios", 0.0))),
            )
            if conf_rango:
                confianzas["folios"] = max(_clamp(confianzas.get("folios", 0.0)), conf_rango)
    except (TypeError, ValueError):
        pass

    return datos, confianzas, fuentes, explicaciones, advertencias


def campos_relevantes(tipo):
    comunes = ["tipo_registro", "no_sp", "fecha_recepcion", "rc", "providencia", "folios"]
    tipo = str(tipo or "").upper()
    if tipo == "ANEXO":
        return comunes + ["numero_anexo", "titulo_anexo", "tipo_anexo", "folio_inicio", "folio_fin"]
    if tipo == "PAGO":
        return comunes + ["boleta", "total"]
    if tipo == "MONITOREO":
        return comunes + ["numero_reporte", "tipo_evento", "tipo_documento"]
    if tipo in {"INSTALACION", "DESINSTALACION"}:
        return comunes
    return comunes


def calcular_calidad_global(datos, confianzas):
    """Calcula un indicador visual; no sustituye la validación humana."""
    datos = datos or {}
    confianzas = confianzas or {}
    tipo = datos.get("tipo_registro")
    campos = campos_relevantes(tipo)
    pesos = {
        "tipo_registro": 1.0,
        "no_sp": 1.5,
        "fecha_recepcion": 0.7,
        "rc": 0.9,
        "providencia": 1.0,
        "folios": 1.2,
        "folio_inicio": 0.8,
        "folio_fin": 0.8,
        "numero_anexo": 1.0,
        "titulo_anexo": 0.8,
        "tipo_anexo": 0.8,
        "boleta": 0.9,
        "total": 0.9,
        "numero_reporte": 0.9,
        "tipo_evento": 0.8,
        "tipo_documento": 0.6,
    }
    total_peso = 0.0
    suma = 0.0
    for campo in campos:
        peso = pesos.get(campo, 0.7)
        total_peso += peso
        valor = datos.get(campo)
        confianza = _clamp(confianzas.get(campo, 0.0)) if valor not in (None, "") else 0.0
        suma += confianza * peso
    if not total_peso:
        return 0
    return int(round((suma / total_peso) * 100))


def etiqueta_calidad(calidad):
    try:
        valor = int(calidad or 0)
    except (TypeError, ValueError):
        valor = 0
    if valor >= 90:
        return "Alta"
    if valor >= 70:
        return "Media"
    return "Revisión necesaria"
