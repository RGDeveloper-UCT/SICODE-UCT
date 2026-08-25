import re
import unicodedata
from pathlib import Path


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def analizar_contexto_usuario(contexto):
    texto = _normalizar(contexto)
    bajo = texto.lower()
    resultado = {"contexto_usuario": str(contexto or "").strip()[:1000]}

    m_sp = re.search(r"\bsp\s*[-:#]?\s*(\d{1,5})\b", bajo)
    if not m_sp:
        m_sp = re.search(r"\b(?:del|de|para)\s+(\d{2,5})\b", bajo)
    if m_sp:
        resultado["no_sp"] = m_sp.group(1)

    m_anexo = re.search(r"\banexo\s*(?:numero|no\.?|#)?\s*(\d+)\b", bajo)
    if m_anexo:
        resultado["numero_anexo"] = m_anexo.group(1)
        resultado["alcance"] = "ANEXO"
    elif "expediente" in bajo:
        resultado["alcance"] = "EXPEDIENTE"
    elif "pago" in bajo or "pagos" in bajo:
        resultado["alcance"] = "PAGOS"

    m_titulo = re.search(r"\banexo\s*(?:numero|no\.?|#)?\s*\d+\s*(?:[-:–—]|de)?\s*(.+?)(?:\.|,|;|$)", texto, re.I)
    if m_titulo:
        titulo = m_titulo.group(1).strip(" -:–—")
        if titulo and not re.fullmatch(r"(?:del|de)\s+(?:sp\s*)?\d+", titulo, re.I):
            resultado["titulo_anexo_contexto"] = titulo[:180]
    return resultado


def analizar_nombre_pdf(nombre):
    original = Path(str(nombre or "documento.pdf")).name
    base = re.sub(r"\.pdf$", "", original, flags=re.I).strip()
    limpio = _normalizar(base)
    resultado = {
        "archivo_origen": original[:240],
        "nombre_documento": base[:180],
        "titulo_documento": base[:180],
        "fuente": "NOMBRE_ARCHIVO",
        "confianza_nombre": 0.45,
    }

    # Los archivos UCT suelen iniciar con folio o rango: 13-14 Acta..., 2-3 ITR..., 5 - Providencia.
    m_rango = re.match(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*[-_ ]*\s*(.*)$", limpio)
    m_unico = re.match(r"^\s*(\d+)\s*[-_. ]+\s*(.*)$", limpio)
    resto = limpio
    if m_rango:
        ini, fin = int(m_rango.group(1)), int(m_rango.group(2))
        if fin >= ini:
            resultado.update({"folio_inicio": ini, "folio_fin": fin, "total_folios": fin - ini + 1})
            resto = m_rango.group(3).strip()
            resultado["confianza_nombre"] = 0.96
    elif m_unico:
        folio = int(m_unico.group(1))
        resultado.update({"folio_inicio": folio, "folio_fin": folio, "total_folios": 1})
        resto = m_unico.group(2).strip()
        resultado["confianza_nombre"] = 0.94

    if resto:
        resultado["titulo_documento"] = resto[:180]
        resultado["nombre_documento"] = resto[:180]

    bajo = resto.lower()
    reglas = (
        (r"\bprovidencia\b", "PROVIDENCIA", 0.99),
        (r"\boficio\b", "OFICIO", 0.98),
        (r"\bacta\b", "ACTA", 0.98),
        (r"\bitr\b", "ITR", 0.99),
        (r"\bift\b", "IFT", 0.99),
        (r"\bformulario\b|\bformato\b", "FORMULARIO", 0.98),
        (r"\bresolucion\b", "RESOLUCION", 0.98),
        (r"\binforme\b", "INFORME", 0.96),
        (r"\borden\s+de\s+instalacion\b", "ORDEN", 0.99),
        (r"\binstalacion\b", "INSTALACION", 0.93),
        (r"\bdesinstalacion\b", "DESINSTALACION", 0.93),
        (r"\bboleta\b|\bpago\b|\brecibo\b", "PAGO", 0.91),
        (r"\banexo\b", "ANEXO", 0.88),
    )
    for patron, tipo, conf in reglas:
        if re.search(patron, bajo, re.I):
            resultado["tipo_documento_lote"] = tipo
            resultado["confianza_tipo_nombre"] = conf
            resultado["confianza_nombre"] = max(resultado["confianza_nombre"], conf)
            break

    # Extrae números documentales evidentes del propio nombre.
    patrones_numero = (
        ("ITR", r"\bitr\s*[-:#]?\s*([0-9][0-9./_-]*(?:-\d{2,4})?)"),
        ("IFT", r"\bift\s*[-:#]?\s*([0-9][0-9./_-]*(?:-\d{2,4})?)"),
        ("OFICIO", r"\boficio(?:\s+\w+){0,3}\s*[-:#]?\s*([0-9]+(?:-\d{2,4})?)"),
        ("FORMULARIO", r"\bformulario(?:\s+\w+){0,3}\s*[-:#]?\s*([0-9]+(?:-\d{2,4})?)"),
    )
    tipo = resultado.get("tipo_documento_lote")
    for esperado, patron in patrones_numero:
        if tipo == esperado:
            m = re.search(patron, bajo, re.I)
            if m:
                resultado["numero_documento"] = m.group(1)[:120]
            break
    return resultado


def aplicar_contexto_y_nombre(resultado_analisis, nombre_archivo, contexto):
    """Fusiona evidencia prioritaria sin inventar datos.

    En SICODE.IA el usuario conoce el SP/anexo y la nomenclatura de archivo ya
    expresa normalmente folios y tipo. OCR/IA queda como complemento para campos
    que no pueden conocerse por esas dos fuentes.
    """
    contexto_info = analizar_contexto_usuario(contexto)
    nombre_info = analizar_nombre_pdf(nombre_archivo)
    docs = list(resultado_analisis.get("documentos") or [])
    if not docs:
        return resultado_analisis

    tipo_nombre = nombre_info.get("tipo_documento_lote")
    folio_ini = nombre_info.get("folio_inicio")
    folio_fin = nombre_info.get("folio_fin")
    fuerte = float(nombre_info.get("confianza_nombre") or 0) >= 0.90

    # Si el propio archivo expresa un rango/tipo fuerte, se considera una pieza documental.
    # Evita que un OCR imperfecto fragmente "13-14 Acta...pdf" en varios documentos falsos.
    if fuerte and (tipo_nombre or folio_ini):
        base = dict(docs[0])
        datos = dict(base.get("datos") or {})
        discrepancias = []
        for d in docs:
            discrepancias.extend(d.get("discrepancias") or [])
        base["pagina_inicio"] = min(d.get("pagina_inicio", 1) for d in docs)
        base["pagina_fin"] = max(d.get("pagina_fin", 1) for d in docs)
        base["discrepancias"] = list(dict.fromkeys(discrepancias))
        docs = [base]

    for doc in docs:
        datos = dict(doc.get("datos") or {})
        fuentes = dict(doc.get("fuentes_campos") or {})
        conf = dict(doc.get("confianzas") or {})

        if contexto_info.get("no_sp"):
            datos["no_sp"] = contexto_info["no_sp"]
            conf["no_sp"] = 0.99
            fuentes["no_sp"] = ["Contexto del usuario"]
        if contexto_info.get("numero_anexo"):
            datos["numero_anexo"] = contexto_info["numero_anexo"]
            conf["numero_anexo"] = 0.99
            fuentes["numero_anexo"] = ["Contexto del usuario"]
        if contexto_info.get("titulo_anexo_contexto"):
            datos["titulo_anexo"] = contexto_info["titulo_anexo_contexto"]
            conf["titulo_anexo"] = 0.96
            fuentes["titulo_anexo"] = ["Contexto del usuario"]

        if folio_ini is not None and folio_fin is not None:
            datos["folio_inicio"] = folio_ini
            datos["folio_fin"] = folio_fin
            datos["total_folios"] = folio_fin - folio_ini + 1
            datos["folios"] = str(datos["total_folios"])
            conf["folio_inicio"] = conf["folio_fin"] = 0.99
            fuentes["folio_inicio"] = fuentes["folio_fin"] = ["Nombre del PDF"]
        if nombre_info.get("titulo_documento"):
            datos["nombre_documento"] = nombre_info["titulo_documento"]
            if contexto_info.get("alcance") == "ANEXO" and not datos.get("titulo_anexo"):
                datos["titulo_anexo"] = nombre_info["titulo_documento"]
                fuentes["titulo_anexo"] = ["Nombre del PDF"]
                conf["titulo_anexo"] = 0.90
        if nombre_info.get("numero_documento"):
            datos["numero_documento"] = nombre_info["numero_documento"]
            conf["numero_documento"] = 0.96
            fuentes["numero_documento"] = ["Nombre del PDF"]
        if tipo_nombre:
            anterior = doc.get("tipo") or datos.get("tipo_documento_lote")
            if anterior and anterior != tipo_nombre:
                doc.setdefault("discrepancias", []).append(
                    f"OCR/IA propuso {anterior}, pero el nombre del PDF identifica {tipo_nombre}. Se priorizó el nombre del archivo."
                )
            doc["tipo"] = tipo_nombre
            datos["tipo_documento_lote"] = tipo_nombre
            if tipo_nombre in {"PAGO", "ANEXO", "INSTALACION", "DESINSTALACION", "MONITOREO"}:
                datos["tipo_registro"] = tipo_nombre
            conf["tipo_documento_lote"] = float(nombre_info.get("confianza_tipo_nombre") or 0.95)
            fuentes["tipo_documento_lote"] = ["Nombre del PDF", "OCR/IA como verificación"]

        datos["archivo_origen"] = nombre_info["archivo_origen"]
        datos["contexto_usuario"] = contexto_info.get("contexto_usuario")
        datos["alcance_contexto"] = contexto_info.get("alcance")
        doc["datos"] = datos
        doc["confianzas"] = conf
        doc["fuentes_campos"] = fuentes
        relevantes = [float(v) for k, v in conf.items() if datos.get(k) not in (None, "") and isinstance(v, (int, float))]
        if relevantes:
            doc["calidad_global"] = max(doc.get("calidad_global") or 0, int(round(sum(relevantes) / len(relevantes) * 100)))

    resultado_analisis["documentos"] = docs
    resultado_analisis["documentos_total"] = len(docs)
    resultado_analisis["calidad_global"] = int(round(sum(d.get("calidad_global", 0) for d in docs) / max(len(docs), 1)))
    resultado_analisis["contexto_interpretado"] = contexto_info
    resultado_analisis["nombre_interpretado"] = nombre_info
    resultado_analisis.setdefault("pipeline", []).insert(0, {
        "clave": "contexto_nombre",
        "nombre": "Contexto + nombre de archivo",
        "estado": "completada",
        "detalle": "SP/anexo se orientaron con el texto del usuario; tipo, título y folios se priorizaron desde el nombre del PDF cuando fueron explícitos.",
    })
    return resultado_analisis
