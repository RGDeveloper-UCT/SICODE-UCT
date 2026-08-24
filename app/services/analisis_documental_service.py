import os
import re
import shutil
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path


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


def _extraer_texto_pdf(ruta, max_paginas=200, ocr_habilitado=True, ocr_idioma="spa"):
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

    paginas_ocr = 0
    if paginas_para_ocr and ocr_habilitado:
        if not shutil.which("tesseract"):
            if all(not texto.strip() for texto in textos):
                raise OCRNoDisponible(
                    "El PDF parece escaneado y el servidor no tiene Tesseract OCR instalado."
                )
        else:
            try:
                import pypdfium2 as pdfium
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("Faltan las dependencias de OCR de SICODE.") from exc

            documento = pdfium.PdfDocument(str(ruta))
            try:
                for indice in paginas_para_ocr:
                    pagina_pdfium = documento[indice]
                    bitmap = pagina_pdfium.render(scale=2.5, grayscale=True)
                    imagen = bitmap.to_pil()
                    try:
                        texto_ocr = pytesseract.image_to_string(
                            imagen,
                            lang=ocr_idioma,
                            config="--psm 6",
                            timeout=60,
                        )
                    except RuntimeError:
                        texto_ocr = ""
                    if texto_ocr.strip():
                        textos[indice] = texto_ocr
                        paginas_ocr += 1
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
            finally:
                documento.close()

    tiene_texto_nativo = any(texto.strip() for texto in textos) and paginas_ocr < total_paginas
    if paginas_ocr == 0:
        metodo = "TEXTO_PDF"
    elif paginas_ocr == total_paginas:
        metodo = "OCR"
    elif tiene_texto_nativo:
        metodo = "MIXTO"
    else:
        metodo = "OCR"

    return "\n\n".join(textos), total_paginas, paginas_ocr, metodo


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
):
    """Procesa un PDF y lo elimina antes de devolver sus metadatos.

    El archivo se coloca preferentemente en /dev/shm (RAM) cuando existe. El
    texto completo solo vive en memoria durante esta función y nunca se
    devuelve ni se persiste.
    """
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

        texto, paginas_pdf, paginas_ocr, metodo = _extraer_texto_pdf(
            ruta,
            max_paginas=max_paginas,
            ocr_habilitado=ocr_habilitado,
            ocr_idioma=ocr_idioma,
        )
        datos, confianzas, advertencias = extraer_metadatos(
            texto,
            paginas_pdf=paginas_pdf,
            tipo_objetivo=tipo_objetivo,
        )
        if not texto.strip():
            advertencias.append("No se obtuvo texto legible del PDF; complete los campos manualmente.")

        return {
            "datos": datos,
            "confianzas": confianzas,
            "advertencias": advertencias,
            "paginas_pdf": paginas_pdf,
            "paginas_ocr": paginas_ocr,
            "metodo_extraccion": metodo,
        }
    finally:
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
