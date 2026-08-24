import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.services.analisis_documental_inteligencia import (
    IAAnalisisNoDisponible,
    ocr_pagina_multipase,
    resolver_tesseract,
)
from app.services.analisis_documental_service import (
    DocumentoInvalido,
    OCRNoDisponible,
    TIPOS_ANEXO,
    extraer_metadatos,
)


TIPOS_DOCUMENTO_LOTE = (
    "PAGO",
    "PROVIDENCIA",
    "ANEXO",
    "IFT",
    "ACTA",
    "DPI",
    "INSTALACION",
    "DESINSTALACION",
    "MONITOREO",
    "OFICIO",
    "INFORME",
    "RESOLUCION",
    "FORMULARIO",
    "OTRO",
)

TIPOS_OPERATIVOS = {"PAGO", "ANEXO", "INSTALACION", "DESINSTALACION", "MONITOREO"}

# Claves seguras: nunca se persiste el texto OCR como patrón de aprendizaje.
CARACTERISTICAS = {
    "kw_pago": ("PAGO", "BOLETA", "DEPOSITO", "COMPROBANTE DE PAGO", "TOTAL Q", "RECIBO"),
    "kw_providencia": ("PROVIDENCIA",),
    "kw_anexo": ("ANEXO", "PRORROGA", "AMPLIACION DE ZONA", "EXONERACION", "MOVILIZACION"),
    "kw_ift": (" IFT ", "INFORME IFT", "I.F.T."),
    "kw_acta": ("ACTA", "ACTA NUMERO", "ACTA NO"),
    "kw_dpi": ("DOCUMENTO PERSONAL DE IDENTIFICACION", "RENAP", "CODIGO UNICO DE IDENTIFICACION", "REPUBLICA DE GUATEMALA"),
    "kw_instalacion": ("INSTALACION", "INSTALAR", "COLOCACION DE DISPOSITIVO"),
    "kw_desinstalacion": ("DESINSTALACION", "DESINSTALAR", "RETIRO DE DISPOSITIVO"),
    "kw_monitoreo": ("CENTRO DE CONTROL", "MONITOREO", "REPORTE DE EVENTO", "VICTIM PROXIMITY"),
    "kw_oficio": ("OFICIO",),
    "kw_informe": ("INFORME", "INFORME TECNICO"),
    "kw_resolucion": ("RESOLUCION",),
    "kw_formulario": ("FORMULARIO", "FORMATO"),
}

PESO_BASE = {
    "kw_pago": {"PAGO": 4.0},
    "kw_providencia": {"PROVIDENCIA": 5.0},
    "kw_anexo": {"ANEXO": 4.5},
    "kw_ift": {"IFT": 5.0},
    "kw_acta": {"ACTA": 4.8},
    "kw_dpi": {"DPI": 5.0},
    "kw_instalacion": {"INSTALACION": 4.5},
    "kw_desinstalacion": {"DESINSTALACION": 4.8},
    "kw_monitoreo": {"MONITOREO": 4.0},
    "kw_oficio": {"OFICIO": 4.5},
    "kw_informe": {"INFORME": 3.5, "IFT": 1.0},
    "kw_resolucion": {"RESOLUCION": 4.8},
    "kw_formulario": {"FORMULARIO": 4.0},
}

MARCADORES_INICIO = {
    "PROVIDENCIA": ("PROVIDENCIA",),
    "ANEXO": ("ANEXO",),
    "ACTA": ("ACTA",),
    "DPI": ("DOCUMENTO PERSONAL DE IDENTIFICACION",),
    "IFT": (" IFT ", "I.F.T."),
    "OFICIO": ("OFICIO",),
    "RESOLUCION": ("RESOLUCION",),
    "FORMULARIO": ("FORMULARIO",),
    "PAGO": ("BOLETA", "COMPROBANTE DE PAGO", "RECIBO"),
}


def _sin_acentos(valor):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(c)
    )


def _normalizar_texto(texto):
    texto = _sin_acentos(texto).upper().replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto


def _directorio_temporal(configurado=None):
    if configurado:
        ruta = Path(configurado)
    elif Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK):
        ruta = Path("/dev/shm/sicode_document_analysis")
    else:
        ruta = Path(tempfile.gettempdir()) / "sicode_document_analysis"
    ruta.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        ruta.chmod(0o700)
    except OSError:
        pass
    return ruta


def limpiar_temporales(directorio, minutos=30):
    limite = datetime.now() - timedelta(minutes=max(5, int(minutos or 30)))
    for patron in ("sicode_lote_*.pdf", "sicode_doc_*.pdf"):
        for ruta in Path(directorio).glob(patron):
            try:
                if datetime.fromtimestamp(ruta.stat().st_mtime) < limite:
                    ruta.unlink(missing_ok=True)
            except OSError:
                continue


def _leer_paginas(
    ruta,
    *,
    max_paginas=200,
    ocr_habilitado=True,
    ocr_idioma="spa",
    tesseract_cmd=None,
    ocr_segunda_pasada=False,
):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise RuntimeError("Falta pypdf para separar el lote documental.") from exc

    try:
        reader = PdfReader(str(ruta), strict=False)
    except PdfReadError as exc:
        raise DocumentoInvalido("El archivo no es un PDF válido o está dañado.") from exc

    if reader.is_encrypted:
        try:
            abierto = reader.decrypt("")
        except Exception:
            abierto = 0
        if not abierto:
            raise DocumentoInvalido("El PDF está protegido con contraseña.")

    total = len(reader.pages)
    if total < 1:
        raise DocumentoInvalido("El PDF no contiene páginas.")
    if total > int(max_paginas):
        raise DocumentoInvalido(f"El lote contiene {total} páginas y supera el límite de {max_paginas}.")

    paginas = []
    pendientes_ocr = []
    for indice, pagina in enumerate(reader.pages):
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        utiles = len(re.sub(r"\W", "", texto, flags=re.UNICODE))
        paginas.append({"pagina": indice + 1, "texto": texto, "origen": "TEXTO_PDF", "confianza_ocr": None})
        if utiles < 45:
            pendientes_ocr.append(indice)

    paginas_ocr = 0
    if pendientes_ocr and ocr_habilitado:
        comando = resolver_tesseract(tesseract_cmd)
        if not comando:
            if all(not p["texto"].strip() for p in paginas):
                raise OCRNoDisponible("El lote parece escaneado y Tesseract no está disponible.")
        else:
            try:
                import pypdfium2 as pdfium
            except ImportError as exc:
                raise RuntimeError("Falta pypdfium2 para renderizar páginas del lote.") from exc

            documento = pdfium.PdfDocument(str(ruta))
            try:
                for indice in pendientes_ocr:
                    pagina_pdf = documento[indice]
                    bitmap = pagina_pdf.render(scale=2.15)
                    imagen = bitmap.to_pil()
                    try:
                        lectura = ocr_pagina_multipase(
                            imagen,
                            idioma=ocr_idioma,
                            tesseract_cmd=comando,
                            segunda_pasada=ocr_segunda_pasada,
                            timeout=55,
                        )
                    except IAAnalisisNoDisponible:
                        lectura = {"texto": "", "confianza": 0.0, "modo": "SIN_LECTURA"}
                    finally:
                        try:
                            imagen.close()
                            bitmap.close()
                            pagina_pdf.close()
                        except Exception:
                            pass
                    if (lectura.get("texto") or "").strip():
                        paginas[indice]["texto"] = lectura["texto"]
                        paginas[indice]["origen"] = "OCR"
                        paginas[indice]["confianza_ocr"] = int(round(float(lectura.get("confianza") or 0)))
                        paginas_ocr += 1
            finally:
                documento.close()

    return paginas, paginas_ocr


def _caracteristicas(texto):
    normal = f" {_normalizar_texto(texto)} "
    activas = []
    for clave, terminos in CARACTERISTICAS.items():
        if any(_normalizar_texto(termino) in normal for termino in terminos):
            activas.append(clave)
    return activas


def clasificar_pagina(texto, pesos_aprendidos=None):
    normal = f" {_normalizar_texto(texto)} "
    activas = _caracteristicas(texto)
    puntuacion = {tipo: 0.0 for tipo in TIPOS_DOCUMENTO_LOTE}
    pesos_aprendidos = pesos_aprendidos or {}

    for caracteristica in activas:
        for tipo, base in PESO_BASE.get(caracteristica, {}).items():
            multiplicador = float(pesos_aprendidos.get((tipo, caracteristica), 1.0) or 1.0)
            puntuacion[tipo] += base * max(0.45, min(2.25, multiplicador))

    tipo, puntos = max(puntuacion.items(), key=lambda item: item[1])
    if puntos <= 0:
        tipo, confianza = "OTRO", 0.28
    else:
        segundo = sorted(puntuacion.values(), reverse=True)[1]
        margen = max(0.0, puntos - segundo)
        confianza = min(0.96, 0.52 + min(puntos, 8.0) * 0.045 + min(margen, 5.0) * 0.035)

    inicio_fuerte = False
    for marcador in MARCADORES_INICIO.get(tipo, ()):
        if _normalizar_texto(marcador) in normal[:1800]:
            inicio_fuerte = True
            break

    return {
        "tipo": tipo,
        "confianza": round(confianza, 4),
        "caracteristicas": activas,
        "inicio_fuerte": inicio_fuerte,
    }


def _ollama_json(url, modelo, payload_usuario, prompt_sistema, timeout):
    req = urllib_request.Request(
        f"{str(url).rstrip('/')}/api/chat",
        data=json.dumps({
            "model": modelo,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": payload_usuario},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": 8192},
        }, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=float(timeout)) as respuesta:
            bruto = json.loads(respuesta.read().decode("utf-8"))
        contenido = ((bruto.get("message") or {}).get("content") or "").strip()
        return json.loads(contenido)
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise IAAnalisisNoDisponible("La IA local no respondió con JSON válido.") from exc


def _clasificar_paginas_ia(paginas, *, url, modelo, timeout=70, max_chars_pagina=1800):
    resultados = {}
    prompt = (
        "Eres el separador documental local de SICODE-UCT. Clasifica cada página de un expediente administrativo "
        "en uno de estos tipos: PAGO, PROVIDENCIA, ANEXO, IFT, ACTA, DPI, INSTALACION, DESINSTALACION, MONITOREO, "
        "OFICIO, INFORME, RESOLUCION, FORMULARIO, OTRO. Indica nuevo_documento=true solo si esa página parece iniciar "
        "una nueva pieza documental. No extraigas nombres ni datos personales. No inventes. Devuelve JSON: "
        "{\"paginas\":[{\"pagina\":1,\"tipo\":\"...\",\"confianza\":0.0,\"nuevo_documento\":false}]}"
    )
    for inicio in range(0, len(paginas), 8):
        bloque = paginas[inicio:inicio + 8]
        compacto = []
        for pagina in bloque:
            texto = str(pagina.get("texto") or "")[:max_chars_pagina]
            compacto.append({"pagina": pagina["pagina"], "texto": texto})
        try:
            salida = _ollama_json(url, modelo, json.dumps(compacto, ensure_ascii=False), prompt, timeout)
        except IAAnalisisNoDisponible:
            continue
        for item in salida.get("paginas", []) if isinstance(salida, dict) else []:
            try:
                numero = int(item.get("pagina"))
                tipo = str(item.get("tipo") or "OTRO").upper()
                confianza = max(0.0, min(0.98, float(item.get("confianza") or 0)))
            except (TypeError, ValueError):
                continue
            if tipo not in TIPOS_DOCUMENTO_LOTE:
                tipo = "OTRO"
            resultados[numero] = {
                "tipo": tipo,
                "confianza": confianza,
                "nuevo_documento": bool(item.get("nuevo_documento")),
            }
    return resultados


def _fusionar_clasificaciones(paginas, reglas, ia):
    fusionadas = []
    anterior_tipo = None
    for pagina, regla in zip(paginas, reglas):
        dato_ia = ia.get(pagina["pagina"])
        tipo = regla["tipo"]
        confianza = regla["confianza"]
        fuente = "Reglas UCT"
        nuevo = regla["inicio_fuerte"]
        if dato_ia:
            if dato_ia["tipo"] == tipo and tipo != "OTRO":
                confianza = min(0.99, max(confianza, dato_ia["confianza"]) + 0.05)
                fuente = "Reglas + IA"
            elif dato_ia["confianza"] >= 0.82 and (confianza < 0.70 or tipo == "OTRO"):
                tipo = dato_ia["tipo"]
                confianza = min(0.90, dato_ia["confianza"])
                fuente = "IA local"
            elif dato_ia["tipo"] != tipo and dato_ia["confianza"] >= 0.72:
                confianza = max(0.35, confianza - 0.12)
                fuente = "Reglas / IA difieren"
            nuevo = bool(nuevo or dato_ia.get("nuevo_documento"))
        if anterior_tipo is None:
            nuevo = True
        fusionadas.append({
            **pagina,
            "tipo": tipo,
            "confianza_tipo": round(confianza, 4),
            "fuente_tipo": fuente,
            "nuevo_documento": nuevo,
            "caracteristicas": regla["caracteristicas"],
        })
        anterior_tipo = tipo
    return fusionadas


def _segmentar_paginas(paginas):
    segmentos = []
    actual = None
    for pagina in paginas:
        tipo = pagina["tipo"]
        if actual is None:
            actual = {"paginas": [pagina], "tipo": tipo}
            continue

        previo_tipo = actual["tipo"]
        cambio_fuerte = pagina["nuevo_documento"] and tipo != "OTRO"
        cambio_confiable = tipo != previo_tipo and tipo != "OTRO" and pagina["confianza_tipo"] >= 0.72

        # Una página sin señales claras se considera continuación del documento anterior.
        if cambio_fuerte or cambio_confiable:
            segmentos.append(actual)
            actual = {"paginas": [pagina], "tipo": tipo}
        else:
            actual["paginas"].append(pagina)
            if previo_tipo == "OTRO" and tipo != "OTRO" and pagina["confianza_tipo"] >= 0.65:
                actual["tipo"] = tipo

    if actual:
        segmentos.append(actual)

    # Une falsos cortes de una sola página OTRO con el documento anterior cuando no hay inicio fuerte.
    normalizados = []
    for segmento in segmentos:
        if (
            segmento["tipo"] == "OTRO"
            and len(segmento["paginas"]) == 1
            and normalizados
            and not segmento["paginas"][0]["nuevo_documento"]
        ):
            normalizados[-1]["paginas"].extend(segmento["paginas"])
        else:
            normalizados.append(segmento)
    return normalizados


def _numero_documento_generico(texto, tipo):
    normal = _normalizar_texto(texto)
    etiquetas = {
        "ACTA": "ACTA",
        "IFT": "IFT",
        "OFICIO": "OFICIO",
        "INFORME": "INFORME",
        "RESOLUCION": "RESOLUCION",
        "FORMULARIO": "FORMULARIO",
    }
    etiqueta = etiquetas.get(tipo)
    if not etiqueta:
        return None
    patron = rf"\b{etiqueta}\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*([A-Z0-9][A-Z0-9./_-]{{1,70}})"
    coincidencias = re.findall(patron, normal, flags=re.IGNORECASE)
    return coincidencias[0] if coincidencias else None


def _analizar_segmentos_ia(segmentos, *, url, modelo, timeout=70, max_chars_segmento=4500):
    resultados = {}
    prompt = (
        "Eres el extractor documental local de SICODE-UCT. Cada elemento ya es una pieza documental separada. "
        "Confirma su tipo y extrae SOLO metadatos administrativos: no_sp, rc, providencia, fecha_recepcion, "
        "folio_inicio, folio_fin, numero_anexo, titulo_anexo, tipo_anexo, boleta, total, numero_documento. "
        "Para DPI NO devuelvas nombre, CUI, dirección, fecha de nacimiento ni ningún dato personal: solo confirma tipo=DPI. "
        "No inventes. Devuelve JSON {\"documentos\":[{\"indice\":1,\"tipo\":\"...\",\"confianza_tipo\":0.0,"
        "\"campos\":{\"campo\":{\"valor\":...,\"confianza\":0.0}}}]}"
    )
    for inicio in range(0, len(segmentos), 6):
        bloque = segmentos[inicio:inicio + 6]
        compacto = []
        for offset, segmento in enumerate(bloque, start=inicio + 1):
            texto = "\n".join(p["texto"] for p in segmento["paginas"])
            compacto.append({
                "indice": offset,
                "tipo_preliminar": segmento["tipo"],
                "paginas": f"{segmento['paginas'][0]['pagina']}-{segmento['paginas'][-1]['pagina']}",
                "texto": texto[:max_chars_segmento],
            })
        try:
            salida = _ollama_json(url, modelo, json.dumps(compacto, ensure_ascii=False), prompt, timeout)
        except IAAnalisisNoDisponible:
            continue
        for item in salida.get("documentos", []) if isinstance(salida, dict) else []:
            try:
                indice = int(item.get("indice"))
                tipo = str(item.get("tipo") or "OTRO").upper()
                conf_tipo = max(0.0, min(0.98, float(item.get("confianza_tipo") or 0)))
            except (TypeError, ValueError):
                continue
            if tipo not in TIPOS_DOCUMENTO_LOTE:
                tipo = "OTRO"
            resultados[indice] = {"tipo": tipo, "confianza_tipo": conf_tipo, "campos": item.get("campos") or {}}
    return resultados


def _sanitizar_campo(campo, valor):
    if valor in (None, "", "null", "NULL"):
        return None
    if campo in {"folio_inicio", "folio_fin"}:
        try:
            numero = int(str(valor).strip())
            return numero if numero > 0 else None
        except (TypeError, ValueError):
            return None
    limite = 180 if campo in {"titulo_anexo", "tipo_anexo"} else 120
    return re.sub(r"\s+", " ", str(valor)).strip()[:limite]


def _fusionar_datos_segmento(segmento, indice, ia_segmentos):
    texto = "\n".join(p["texto"] for p in segmento["paginas"])
    tipo_lote = segmento["tipo"]
    tipo_objetivo = tipo_lote if tipo_lote in TIPOS_OPERATIVOS else "AUTO"
    datos, confianzas, advertencias = extraer_metadatos(texto, len(segmento["paginas"]), tipo_objetivo=tipo_objetivo)
    datos["tipo_documento_lote"] = tipo_lote
    datos["pagina_inicio_pdf"] = segmento["paginas"][0]["pagina"]
    datos["pagina_fin_pdf"] = segmento["paginas"][-1]["pagina"]
    datos["numero_documento"] = _numero_documento_generico(texto, tipo_lote)
    if tipo_lote not in TIPOS_OPERATIVOS:
        datos["tipo_registro"] = None
        datos["tipo_documento"] = tipo_lote
    if tipo_lote == "DPI":
        # Privacidad: se clasifica el documento sin persistir identidad personal.
        for campo in ("no_sp", "rc", "providencia", "numero_documento", "titulo_anexo"):
            datos[campo] = None
            confianzas[campo] = 0.0
        advertencias.append("DPI identificado: los datos personales no se persisten; solo se registra la presencia/tipo documental.")

    conf_tipo = sum(p["confianza_tipo"] for p in segmento["paginas"]) / max(len(segmento["paginas"]), 1)
    confianzas["tipo_documento_lote"] = conf_tipo
    fuentes = {"tipo_documento_lote": list(dict.fromkeys(p["fuente_tipo"] for p in segmento["paginas"]))}

    ia = ia_segmentos.get(indice)
    ia_utilizada = False
    discrepancias = list(advertencias)
    if ia:
        ia_utilizada = True
        tipo_ia = ia["tipo"]
        if tipo_ia == tipo_lote:
            confianzas["tipo_documento_lote"] = min(0.99, max(conf_tipo, ia["confianza_tipo"]) + 0.05)
            fuentes["tipo_documento_lote"].append("IA local")
        elif ia["confianza_tipo"] >= 0.86 and conf_tipo < 0.68:
            tipo_lote = tipo_ia
            datos["tipo_documento_lote"] = tipo_lote
            datos["tipo_registro"] = tipo_lote if tipo_lote in TIPOS_OPERATIVOS else None
            datos["tipo_documento"] = tipo_lote
            confianzas["tipo_documento_lote"] = min(0.88, ia["confianza_tipo"])
            fuentes["tipo_documento_lote"] = ["IA local"]
        elif tipo_ia != tipo_lote and ia["confianza_tipo"] >= 0.70:
            confianzas["tipo_documento_lote"] = max(0.35, conf_tipo - 0.14)
            discrepancias.append(f"Clasificador e IA difieren: {tipo_lote} / {tipo_ia}. Revise el tipo antes de confirmar.")

        if tipo_lote != "DPI":
            for campo, entrada in (ia.get("campos") or {}).items():
                if campo not in {"no_sp", "rc", "providencia", "fecha_recepcion", "folio_inicio", "folio_fin", "numero_anexo", "titulo_anexo", "tipo_anexo", "boleta", "total", "numero_documento"}:
                    continue
                if not isinstance(entrada, dict):
                    continue
                valor = _sanitizar_campo(campo, entrada.get("valor"))
                try:
                    confianza_ia = max(0.0, min(0.96, float(entrada.get("confianza") or 0)))
                except (TypeError, ValueError):
                    confianza_ia = 0.0
                if valor is None:
                    continue
                existente = datos.get(campo)
                conf_existente = float(confianzas.get(campo) or 0)
                if existente in (None, "") and confianza_ia >= 0.58:
                    datos[campo] = valor
                    confianzas[campo] = min(0.84, confianza_ia * 0.90)
                    fuentes[campo] = ["IA local"]
                elif str(existente).strip().upper() == str(valor).strip().upper():
                    confianzas[campo] = min(0.99, max(conf_existente, confianza_ia) + 0.05)
                    fuentes[campo] = ["OCR + reglas", "IA local"]
                elif confianza_ia >= 0.80:
                    confianzas[campo] = max(0.25, conf_existente - 0.12)
                    discrepancias.append(f"IA y reglas difieren en {campo.replace('_', ' ')}; se conservó la lectura determinística.")

    inicio = datos.get("folio_inicio")
    fin = datos.get("folio_fin")
    if inicio and fin and int(fin) >= int(inicio):
        datos["total_folios"] = int(fin) - int(inicio) + 1
        datos["folios"] = str(datos["total_folios"])

    relevantes = [v for k, v in confianzas.items() if datos.get(k) not in (None, "") and isinstance(v, (int, float))]
    relevantes.append(float(confianzas.get("tipo_documento_lote") or 0))
    calidad = int(round(sum(relevantes) / max(len(relevantes), 1) * 100))
    calidad = max(5, min(99, calidad))

    return {
        "tipo": tipo_lote,
        "pagina_inicio": segmento["paginas"][0]["pagina"],
        "pagina_fin": segmento["paginas"][-1]["pagina"],
        "datos": datos,
        "confianzas": confianzas,
        "fuentes_campos": fuentes,
        "discrepancias": list(dict.fromkeys(discrepancias)),
        "caracteristicas": sorted({c for p in segmento["paginas"] for c in p["caracteristicas"]}),
        "calidad_global": calidad,
        "ia_utilizada": ia_utilizada,
    }


def analizar_lote_temporal(
    archivo,
    *,
    temp_dir=None,
    max_mb=40,
    max_paginas=200,
    ocr_habilitado=True,
    ocr_idioma="spa",
    limpieza_minutos=30,
    tesseract_cmd=None,
    ocr_segunda_pasada=False,
    ia_habilitada=True,
    ollama_url="http://127.0.0.1:11434",
    ollama_model="qwen3:1.7b",
    ollama_timeout=75,
    pesos_aprendidos=None,
):
    inicio_total = time.perf_counter()
    directorio = _directorio_temporal(temp_dir)
    limpiar_temporales(directorio, limpieza_minutos)
    descriptor, nombre = tempfile.mkstemp(prefix="sicode_lote_", suffix=".pdf", dir=str(directorio))
    ruta = Path(nombre)
    try:
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "wb") as destino:
            shutil.copyfileobj(archivo.stream, destino, length=1024 * 1024)
        if ruta.stat().st_size < 5:
            raise DocumentoInvalido("El PDF está vacío.")
        if ruta.stat().st_size > int(max_mb) * 1024 * 1024:
            raise DocumentoInvalido(f"El PDF supera el límite de {max_mb} MB.")
        with ruta.open("rb") as lector:
            if lector.read(5) != b"%PDF-":
                raise DocumentoInvalido("El archivo no tiene una cabecera PDF válida.")

        paginas, paginas_ocr = _leer_paginas(
            ruta,
            max_paginas=max_paginas,
            ocr_habilitado=ocr_habilitado,
            ocr_idioma=ocr_idioma,
            tesseract_cmd=tesseract_cmd,
            ocr_segunda_pasada=ocr_segunda_pasada,
        )
        reglas = [clasificar_pagina(p["texto"], pesos_aprendidos) for p in paginas]
        ia_paginas = {}
        if ia_habilitada:
            ia_paginas = _clasificar_paginas_ia(
                paginas,
                url=ollama_url,
                modelo=ollama_model,
                timeout=ollama_timeout,
            )
        paginas_fusionadas = _fusionar_clasificaciones(paginas, reglas, ia_paginas)
        segmentos_brutos = _segmentar_paginas(paginas_fusionadas)

        ia_segmentos = {}
        if ia_habilitada and segmentos_brutos:
            ia_segmentos = _analizar_segmentos_ia(
                segmentos_brutos,
                url=ollama_url,
                modelo=ollama_model,
                timeout=ollama_timeout,
            )
        documentos = [
            _fusionar_datos_segmento(segmento, indice, ia_segmentos)
            for indice, segmento in enumerate(segmentos_brutos, start=1)
        ]

        calidad_lote = int(round(sum(d["calidad_global"] for d in documentos) / max(len(documentos), 1)))
        return {
            "paginas_pdf": len(paginas),
            "paginas_ocr": paginas_ocr,
            "documentos": documentos,
            "documentos_total": len(documentos),
            "calidad_global": calidad_lote,
            "ia_utilizada": bool(ia_paginas or ia_segmentos),
            "ia_modelo": str(ollama_model)[:80] if ia_habilitada else None,
            "duracion_ms": int((time.perf_counter() - inicio_total) * 1000),
            "pipeline": [
                {"clave": "paginas", "nombre": "Lectura por página", "estado": "completada", "detalle": f"{len(paginas)} página(s) evaluadas; {paginas_ocr} mediante OCR."},
                {"clave": "clasificacion", "nombre": "Clasificación documental", "estado": "completada", "detalle": f"{len(documentos)} pieza(s) documentales detectadas."},
                {"clave": "ia", "nombre": "IA local", "estado": "completada" if (ia_paginas or ia_segmentos) else "advertencia", "detalle": "Ollama apoyó límites, tipo y metadatos." if (ia_paginas or ia_segmentos) else "El lote se resolvió con OCR, reglas y aprendizaje acumulado."},
                {"clave": "humano", "nombre": "Confirmación humana", "estado": "pendiente", "detalle": "Cada documento debe revisarse antes de crear registros."},
            ],
        }
    finally:
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
