import os
import re
import shutil
import tempfile
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from app.services.analisis_documental_inteligencia import (
    IAAnalisisNoDisponible,
    calcular_calidad_global,
    consultar_ia_local,
    fusionar_reglas_e_ia,
    ocr_pagina_multipase,
    resolver_tesseract,
)


TIPOS_REGISTRO_ADMITIDOS = {"AUTO", "ANEXO", "INSTALACION", "DESINSTALACION", "PAGO", "MONITOREO"}

TIPOS_ANEXO = [
    "REEMPLAZO",
    "MOVILIZACION",
    "AMPLIACION ZONA",
    "EXONERACION",
    "PRORROGA",
    "ZONA DE INCLUSION",
    "CARGADOR",
    "CORREA",
    "CARGADOR Y CORREA",
    "DCT, CARGADOR, CORREA",
    "2 CARGADORES Y CORREA",
    "DOS CARGADORES",
    "CAMBIO JUZGADO",
]

TIPOS_EVENTO = [
    "Prohibido acercarse",
    "Salida de zona de inclusión",
    "Salida",
    "Apertura",
    "Zona de inclusión",
    "Zona de exclusión",
    "Victim Proximity",
    "Seguimiento de proximidad",
    "Batería baja 30%",
    "Batería baja 12%",
    "No comunicación",
    "Ingreso prevención",
]


class DocumentoInvalido(ValueError):
    pass


class OCRNoDisponible(RuntimeError):
    pass


def _sin_acentos(valor):
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caracter)
    )


def _texto_busqueda(texto):
    texto = _sin_acentos(texto).upper().replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto


def _normalizar_sp(valor):
    texto = str(valor or "").strip()
    texto = re.sub(r"^SP\s*[-:#]?\s*", "", texto, flags=re.IGNORECASE).strip()
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return str(int(texto)) if texto.isdigit() else texto.upper()


def _modo_con_confianza(valores, confianza_unico=0.88, confianza_repetido=0.98):
    limpios = [str(valor).strip() for valor in valores if str(valor or "").strip()]
    if not limpios:
        return None, 0.0
    conteo = Counter(limpios)
    valor, repeticiones = conteo.most_common(1)[0]
    return valor, confianza_repetido if repeticiones > 1 else confianza_unico


def _primera_fecha(texto):
    for dia, mes, anio in re.findall(r"\b([0-3]?\d)[/-]([01]?\d)[/-]((?:19|20)\d{2})\b", texto):
        try:
            return date(int(anio), int(mes), int(dia)).isoformat(), 0.86
        except ValueError:
            continue
    return None, 0.0


def _extraer_sp(texto):
    patrones = [
        r"\bS\s*\.?\s*P\s*\.?\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*(\d{1,6})\b",
        r"\bSUJETO\s+PORTADOR\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*(\d{1,6})\b",
    ]
    encontrados = []
    for patron in patrones:
        encontrados.extend(re.findall(patron, texto, flags=re.IGNORECASE))
    encontrados = [_normalizar_sp(valor) for valor in encontrados]
    return _modo_con_confianza(encontrados, 0.92, 0.99)


def _extraer_identificador(texto, etiqueta, maximo=80):
    patron = rf"\b{etiqueta}\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*([A-Z0-9][A-Z0-9./_-]{{1,{maximo}}})"
    encontrados = re.findall(patron, texto, flags=re.IGNORECASE)
    return _modo_con_confianza(encontrados, 0.86, 0.95)


def _extraer_numero_anexo(texto):
    patron = r"\bANEXO\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*([0-9]{1,4}|[IVXLCDM]{1,10})\b"
    return _modo_con_confianza(re.findall(patron, texto, flags=re.IGNORECASE), 0.90, 0.98)


def _extraer_tipo_anexo(texto):
    coincidencias = []
    for tipo in TIPOS_ANEXO:
        if _texto_busqueda(tipo) in texto:
            coincidencias.append(tipo)
    return _modo_con_confianza(coincidencias, 0.78, 0.90)


def _extraer_titulo_anexo(texto_original):
    lineas = [re.sub(r"\s+", " ", linea).strip() for linea in str(texto_original or "").splitlines()]
    for indice, linea in enumerate(lineas):
        if not re.search(r"\bANEXO\b", _sin_acentos(linea), flags=re.IGNORECASE):
            continue
        resto = re.sub(
            r"^.*?\bANEXO\b\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*(?:[0-9]{1,4}|[IVXLCDM]{1,10})?\s*[-:–]?\s*",
            "",
            linea,
            flags=re.IGNORECASE,
        ).strip(" -:–")
        if 5 <= len(resto) <= 180 and not resto.isdigit():
            return resto, 0.82
        for siguiente in lineas[indice + 1: indice + 4]:
            if not siguiente:
                continue
            if 5 <= len(siguiente) <= 180 and not re.fullmatch(r"[0-9./ -]+", siguiente):
                return siguiente, 0.72
    return None, 0.0


def _extraer_folios(texto):
    rangos = []
    patron_rango = (
        r"\bFOLIOS?\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*(\d{1,6})"
        r"\s*(?:AL|A|HASTA|-|–)\s*(\d{1,6})\b"
    )
    for inicio, fin in re.findall(patron_rango, texto, flags=re.IGNORECASE):
        inicio_i, fin_i = int(inicio), int(fin)
        if inicio_i >= 1 and fin_i >= inicio_i and fin_i - inicio_i <= 10000:
            rangos.append((inicio_i, fin_i))

    if rangos:
        inicio, fin = max(rangos, key=lambda item: item[1] - item[0])
        total = fin - inicio + 1
        return {
            "folio_inicio": inicio,
            "folio_fin": fin,
            "total_folios": total,
            "folios": str(total),
            "fuente_folios": "rango_explicito",
        }, 0.96

    patron_individual = r"\bFOLIO\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*(\d{1,6})\b"
    individuales = sorted({int(valor) for valor in re.findall(patron_individual, texto, flags=re.IGNORECASE)})
    if individuales:
        inicio, fin = individuales[0], individuales[-1]
        total = len(individuales)
        return {
            "folio_inicio": inicio,
            "folio_fin": fin,
            "total_folios": total,
            "folios": str(total),
            "fuente_folios": "folios_etiquetados",
        }, 0.88 if total > 1 else 0.70

    return {
        "folio_inicio": None,
        "folio_fin": None,
        "total_folios": None,
        "folios": None,
        "fuente_folios": "no_detectado",
    }, 0.0


def _clasificar(texto, tipo_objetivo):
    tipo = str(tipo_objetivo or "AUTO").upper()
    if tipo in TIPOS_REGISTRO_ADMITIDOS and tipo != "AUTO":
        return tipo, 1.0

    reglas = {
        "ANEXO": ["ANEXO", "AMPLIACION ZONA", "EXONERACION", "PRORROGA"],
        "DESINSTALACION": ["DESINSTALACION", "DESINSTALAR", "RETIRO DE DISPOSITIVO"],
        "INSTALACION": ["INSTALACION", "INSTALAR", "COLOCACION DE DISPOSITIVO"],
        "PAGO": ["PAGO", "BOLETA", "DEPOSITO", "TOTAL Q"],
        "MONITOREO": ["MONITOREO", "CENTRO DE CONTROL", "REPORTE", "EVENTO"],
    }
    puntuaciones = {
        clave: sum(1 for palabra in palabras if palabra in texto)
        for clave, palabras in reglas.items()
    }
    ganador, puntos = max(puntuaciones.items(), key=lambda item: item[1])
    if puntos == 0:
        return "ANEXO", 0.45
    return ganador, min(0.65 + puntos * 0.10, 0.95)


def _extraer_boleta(texto):
    return _extraer_identificador(texto, r"BOLETA", 60)


def _extraer_total(texto):
    patrones = [
        r"\bTOTAL\s*(?:Q|Q\.|GTQ)?\s*[:=-]?\s*([0-9]{1,9}(?:[.,][0-9]{2})?)",
        r"\bQ\.?\s*([0-9]{1,9}(?:[.,][0-9]{2})?)\b",
    ]
    for patron in patrones:
        coincidencias = re.findall(patron, texto, flags=re.IGNORECASE)
        if coincidencias:
            valor = coincidencias[-1].replace(",", ".")
            return valor, 0.82
    return None, 0.0


def _extraer_numero_reporte(texto):
    patrones = [r"\bREPORTE\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*([A-Z0-9][A-Z0-9./_-]{1,80})"]
    valores = []
    for patron in patrones:
        valores.extend(re.findall(patron, texto, flags=re.IGNORECASE))
    return _modo_con_confianza(valores, 0.82, 0.94)


def _extraer_tipo_evento(texto):
    for evento in TIPOS_EVENTO:
        if _texto_busqueda(evento) in texto:
            return evento, 0.82
    return None, 0.0


def _extraer_tipo_documento(texto):
    for tipo in ("PROVIDENCIA", "OFICIO", "INFORME"):
        if re.search(rf"\b{tipo}\b", texto):
            return tipo, 0.82
    return None, 0.0


def extraer_metadatos(texto_original, paginas_pdf, tipo_objetivo="AUTO"):
    """Extrae solo campos administrativos autorizados del texto temporal."""
    texto = _texto_busqueda(texto_original)
    tipo, confianza_tipo = _clasificar(texto, tipo_objetivo)
    no_sp, confianza_sp = _extraer_sp(texto)
    rc, confianza_rc = _extraer_identificador(texto, r"R\.?\s*C\.?", 60)
    providencia, confianza_providencia = _extraer_identificador(texto, r"PROVIDENCIA", 100)
    fecha_recepcion, confianza_fecha = _primera_fecha(texto)
    folios, confianza_folios = _extraer_folios(texto)

    numero_anexo, confianza_numero_anexo = _extraer_numero_anexo(texto)
    tipo_anexo, confianza_tipo_anexo = _extraer_tipo_anexo(texto)
    titulo_anexo, confianza_titulo = _extraer_titulo_anexo(texto_original)
    boleta, confianza_boleta = _extraer_boleta(texto)
    total, confianza_total = _extraer_total(texto)
    numero_reporte, confianza_reporte = _extraer_numero_reporte(texto)
    tipo_evento, confianza_evento = _extraer_tipo_evento(texto)
    tipo_documento, confianza_tipo_documento = _extraer_tipo_documento(texto)

    datos = {
        "tipo_registro": tipo,
        "no_sp": no_sp,
        "rc": rc,
        "providencia": providencia,
        "fecha_recepcion": fecha_recepcion,
        "persona_entrega": None,
        "folios": folios["folios"],
        "folio_inicio": folios["folio_inicio"],
        "folio_fin": folios["folio_fin"],
        "total_folios": folios["total_folios"],
        "fuente_folios": folios["fuente_folios"],
        "paginas_pdf": int(paginas_pdf or 0),
        "numero_anexo": numero_anexo,
        "titulo_anexo": titulo_anexo,
        "tipo_anexo": tipo_anexo,
        "boleta": boleta,
        "total": total,
        "periodo_texto": None,
        "numero_reporte": numero_reporte,
        "tipo_evento": tipo_evento,
        "tipo_documento": tipo_documento or "PROVIDENCIA",
        "descripcion": "EXPEDIENTE" if tipo in {"INSTALACION", "DESINSTALACION"} else None,
    }

    confianzas = {
        "tipo_registro": confianza_tipo,
        "no_sp": confianza_sp,
        "rc": confianza_rc,
        "providencia": confianza_providencia,
        "fecha_recepcion": confianza_fecha,
        "folios": confianza_folios,
        "folio_inicio": confianza_folios,
        "folio_fin": confianza_folios,
        "total_folios": confianza_folios,
        "numero_anexo": confianza_numero_anexo,
        "titulo_anexo": confianza_titulo,
        "tipo_anexo": confianza_tipo_anexo,
        "boleta": confianza_boleta,
        "total": confianza_total,
        "numero_reporte": confianza_reporte,
        "tipo_evento": confianza_evento,
        "tipo_documento": confianza_tipo_documento,
    }

    advertencias = []
    if not no_sp:
        advertencias.append("No se detectó un No. de SP con confianza suficiente; debe indicarlo manualmente.")
    if folios["total_folios"] is None:
        advertencias.append(
            f"No se detectó foliación explícita. El PDF contiene {paginas_pdf} página(s), pero ese conteo no se asumirá automáticamente como folios."
        )
    elif paginas_pdf and folios["total_folios"] != paginas_pdf:
        advertencias.append(
            f"El PDF contiene {paginas_pdf} página(s) y se detectaron {folios['total_folios']} folio(s). Verifique la diferencia antes de confirmar."
        )
    if tipo == "ANEXO" and not numero_anexo:
        advertencias.append("No se detectó con claridad el número de anexo.")

    return datos, confianzas, advertencias


def _directorio_temporal(configurado=None):
    if configurado:
        directorio = Path(configurado)
    elif Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK):
        directorio = Path("/dev/shm/sicode_document_analysis")
    else:
        directorio = Path(tempfile.gettempdir()) / "sicode_document_analysis"
    directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directorio.chmod(0o700)
    except OSError:
        pass
    return directorio


def limpiar_temporales_antiguos(directorio, minutos=30):
    limite = datetime.now() - timedelta(minutes=max(int(minutos or 30), 5))
    for ruta in Path(directorio).glob("sicode_doc_*.pdf"):
        try:
            if datetime.fromtimestamp(ruta.stat().st_mtime) < limite:
                ruta.unlink(missing_ok=True)
        except OSError:
            continue


def _extraer_texto_pdf(
    ruta,
    max_paginas=200,
    ocr_habilitado=True,
    ocr_idioma="spa",
    tesseract_cmd=None,
    ocr_segunda_pasada=True,
):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise RuntimeError("Falta la dependencia pypdf para analizar documentos.") from exc

    try:
        reader = PdfReader(str(ruta), strict=False)
    except PdfReadError as exc:
        raise DocumentoInvalido("El archivo no es un PDF válido o está dañado.") from exc

    if reader.is_encrypted:
        try:
            desbloqueado = reader.decrypt("")
        except Exception:
            desbloqueado = 0
        if not desbloqueado:
            raise DocumentoInvalido("El PDF está protegido con contraseña y no puede analizarse temporalmente.")

    total_paginas = len(reader.pages)
    if total_paginas < 1:
        raise DocumentoInvalido("El PDF no contiene páginas.")
    if total_paginas > int(max_paginas):
        raise DocumentoInvalido(
            f"El PDF contiene {total_paginas} páginas y supera el límite de {max_paginas} páginas por análisis."
        )

    textos = []
    paginas_para_ocr = []
    for indice, pagina in enumerate(reader.pages):
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""
        textos.append(texto)
        caracteres_utiles = len(re.sub(r"\W", "", texto, flags=re.UNICODE))
        if caracteres_utiles < 35:
            paginas_para_ocr.append(indice)

    diagnostico_ocr = {
        "necesario": bool(paginas_para_ocr),
        "disponible": True,
        "confianza_media": None,
        "paginas": [],
        "segunda_pasada": bool(ocr_segunda_pasada),
    }
    paginas_ocr = 0

    if paginas_para_ocr and ocr_habilitado:
        comando = resolver_tesseract(tesseract_cmd)
        if not comando:
            diagnostico_ocr["disponible"] = False
            if all(not texto.strip() for texto in textos):
                raise OCRNoDisponible(
                    "El PDF parece escaneado y Tesseract OCR no está disponible para el servicio de SICODE."
                )
        else:
            try:
                import pypdfium2 as pdfium
            except ImportError as exc:
                raise RuntimeError("Falta pypdfium2 para renderizar páginas escaneadas.") from exc

            documento = pdfium.PdfDocument(str(ruta))
            try:
                for indice in paginas_para_ocr:
                    pagina_pdfium = documento[indice]
                    bitmap = pagina_pdfium.render(scale=2.5)
                    imagen = bitmap.to_pil()
                    try:
                        lectura = ocr_pagina_multipase(
                            imagen,
                            idioma=ocr_idioma,
                            tesseract_cmd=comando,
                            segunda_pasada=ocr_segunda_pasada,
                            timeout=60,
                        )
                    except IAAnalisisNoDisponible as exc:
                        if all(not texto.strip() for texto in textos):
                            raise OCRNoDisponible(str(exc)) from exc
                        lectura = {"texto": "", "confianza": 0.0, "modo": "SIN_LECTURA", "caracteres": 0}
                    finally:
                        try:
                            imagen.close()
                        except Exception:
                            pass
                        try:
                            bitmap.close()
                        except Exception:
                            pass
                        try:
                            pagina_pdfium.close()
                        except Exception:
                            pass

                    texto_ocr = lectura.get("texto") or ""
                    if texto_ocr.strip():
                        textos[indice] = texto_ocr
                        paginas_ocr += 1
                    diagnostico_ocr["paginas"].append(
                        {
                            "pagina": indice + 1,
                            "confianza": int(round(float(lectura.get("confianza") or 0))),
                            "modo": lectura.get("modo") or "OCR",
                            "caracteres": int(lectura.get("caracteres") or 0),
                        }
                    )
            finally:
                documento.close()

    if diagnostico_ocr["paginas"]:
        diagnostico_ocr["confianza_media"] = int(
            round(sum(item["confianza"] for item in diagnostico_ocr["paginas"]) / len(diagnostico_ocr["paginas"]))
        )

    tiene_texto_nativo = any(texto.strip() for texto in textos) and paginas_ocr < total_paginas
    if paginas_ocr == 0:
        metodo = "TEXTO_PDF"
    elif paginas_ocr == total_paginas:
        metodo = "OCR"
    elif tiene_texto_nativo:
        metodo = "MIXTO"
    else:
        metodo = "OCR"

    return "\n\n".join(textos), total_paginas, paginas_ocr, metodo, diagnostico_ocr


def analizar_pdf_temporal(
    archivo,
    *,
    tipo_objetivo="AUTO",
    temp_dir=None,
    max_mb=40,
    max_paginas=200,
    ocr_habilitado=True,
    ocr_idioma="spa",
    limpieza_minutos=30,
    tesseract_cmd=None,
    ocr_segunda_pasada=True,
    ia_habilitada=True,
    ollama_url="http://127.0.0.1:11434",
    ollama_model="qwen3:1.7b",
    ollama_timeout=90,
    ia_max_chars=24000,
):
    """Procesa un PDF, usa OCR/IA local y lo elimina antes de devolver metadatos.

    El archivo se coloca preferentemente en /dev/shm. El PDF, las imágenes y
    el texto OCR completo se destruyen antes de retornar. Ollama recibe texto
    únicamente por loopback y SICODE solo persiste metadatos de lista blanca.
    """
    inicio_total = time.perf_counter()
    tipo_objetivo = str(tipo_objetivo or "AUTO").upper()
    if tipo_objetivo not in TIPOS_REGISTRO_ADMITIDOS:
        tipo_objetivo = "AUTO"

    directorio = _directorio_temporal(temp_dir)
    limpiar_temporales_antiguos(directorio, limpieza_minutos)

    descriptor, nombre_temporal = tempfile.mkstemp(prefix="sicode_doc_", suffix=".pdf", dir=str(directorio))
    ruta = Path(nombre_temporal)
    try:
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "wb") as destino:
            shutil.copyfileobj(archivo.stream, destino, length=1024 * 1024)

        tamano = ruta.stat().st_size
        if tamano < 5:
            raise DocumentoInvalido("El archivo PDF está vacío.")
        if tamano > int(max_mb) * 1024 * 1024:
            raise DocumentoInvalido(f"El PDF supera el límite de {max_mb} MB permitido por análisis.")
        with ruta.open("rb") as lector:
            if lector.read(5) != b"%PDF-":
                raise DocumentoInvalido("El archivo seleccionado no tiene una cabecera PDF válida.")

        texto, paginas_pdf, paginas_ocr, metodo, diagnostico_ocr = _extraer_texto_pdf(
            ruta,
            max_paginas=max_paginas,
            ocr_habilitado=ocr_habilitado,
            ocr_idioma=ocr_idioma,
            tesseract_cmd=tesseract_cmd,
            ocr_segunda_pasada=ocr_segunda_pasada,
        )

        datos_reglas, confianzas_reglas, advertencias = extraer_metadatos(
            texto,
            paginas_pdf=paginas_pdf,
            tipo_objetivo=tipo_objetivo,
        )
        if not texto.strip():
            advertencias.append("No se obtuvo texto legible del PDF; complete los campos manualmente.")

        resultado_ia = None
        ia_diagnostico = {
            "habilitada": bool(ia_habilitada),
            "utilizada": False,
            "modelo": str(ollama_model)[:80] if ia_habilitada else None,
            "estado": "omitida" if not ia_habilitada else "pendiente",
            "duracion_ms": None,
        }
        if ia_habilitada and texto.strip():
            try:
                resultado_ia = consultar_ia_local(
                    texto,
                    datos_reglas,
                    tipo_objetivo=tipo_objetivo,
                    tipos_anexo=TIPOS_ANEXO,
                    tipos_evento=TIPOS_EVENTO,
                    base_url=ollama_url,
                    modelo=ollama_model,
                    timeout=ollama_timeout,
                    max_chars=ia_max_chars,
                )
                ia_diagnostico.update(
                    utilizada=True,
                    estado="completada",
                    modelo=resultado_ia.get("modelo"),
                    duracion_ms=resultado_ia.get("duracion_ms"),
                )
            except IAAnalisisNoDisponible:
                ia_diagnostico["estado"] = "no_disponible"
                advertencias.append(
                    "La IA local no estuvo disponible en este análisis; la propuesta se generó con OCR y reglas determinísticas."
                )

        datos, confianzas, fuentes, explicaciones, discrepancias_ia = fusionar_reglas_e_ia(
            datos_reglas,
            confianzas_reglas,
            resultado_ia,
        )
        advertencias.extend(discrepancias_ia)
        calidad = calcular_calidad_global(datos, confianzas)
        duracion_total = int((time.perf_counter() - inicio_total) * 1000)

        if paginas_ocr:
            detalle_ocr = f"{paginas_ocr} de {paginas_pdf} página(s) procesadas con OCR local"
            if diagnostico_ocr.get("confianza_media") is not None:
                detalle_ocr += f" · confianza OCR media {diagnostico_ocr['confianza_media']}%"
            estado_ocr = "completada"
        elif diagnostico_ocr.get("necesario") and not diagnostico_ocr.get("disponible"):
            detalle_ocr = "Tesseract no estuvo disponible; se conservó el texto nativo existente"
            estado_ocr = "advertencia"
        else:
            detalle_ocr = "El PDF aportó texto nativo suficiente; no fue necesario OCR"
            estado_ocr = "omitida"

        if ia_diagnostico["estado"] == "completada":
            detalle_ia = f"IA local {ia_diagnostico.get('modelo') or ''} interpretó el OCR sin conexión externa"
            estado_ia = "completada"
        elif ia_diagnostico["estado"] == "no_disponible":
            detalle_ia = "Ollama no respondió; el flujo continuó sin bloquearse"
            estado_ia = "advertencia"
        else:
            detalle_ia = "IA documental deshabilitada por configuración"
            estado_ia = "omitida"

        diagnostico = {
            "etapas": [
                {"clave": "pdf", "nombre": "PDF temporal", "estado": "completada", "detalle": f"{paginas_pdf} página(s) recibidas; archivo descartado al terminar"},
                {"clave": "ocr", "nombre": "Lectura y OCR", "estado": estado_ocr, "detalle": detalle_ocr},
                {"clave": "reglas", "nombre": "Reglas documentales", "estado": "completada", "detalle": "Se aplicaron patrones de SP, RC, providencia, anexos, fechas y foliación"},
                {"clave": "ia", "nombre": "IA local", "estado": estado_ia, "detalle": detalle_ia},
            ],
            "ocr": diagnostico_ocr,
            "ia": ia_diagnostico,
            "duracion_total_ms": duracion_total,
            "privacidad": "PDF, imágenes y texto OCR completo no persistidos",
        }

        return {
            "datos": datos,
            "confianzas": confianzas,
            "fuentes_campos": fuentes,
            "explicaciones_campos": explicaciones,
            "calidad_global": calidad,
            "advertencias": list(dict.fromkeys(advertencias)),
            "paginas_pdf": paginas_pdf,
            "paginas_ocr": paginas_ocr,
            "metodo_extraccion": metodo,
            "pipeline_diagnostico": diagnostico,
            "ia_utilizada": bool(ia_diagnostico.get("utilizada")),
            "ia_modelo": ia_diagnostico.get("modelo") if ia_diagnostico.get("utilizada") else None,
            "duracion_ms": duracion_total,
        }
    finally:
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
