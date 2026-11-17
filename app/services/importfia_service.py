"""IMPORTF.IA: contrato de foliación física individual por SP.

El libro no es una constancia de verificación administrativa. Se importa solamente
metadato nuevo, y los existentes nunca se modifican ni se anulan automáticamente.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from openpyxl import load_workbook

from app.services.catalogo_anexos_service import catalogo_plano

HOJAS = ("CONTROL", "FOLIOS", "ANEXOS", "INCIDENCIAS", "CATALOGO")
FOLIOS_OBLIGATORIAS = {
    "sp", "codigo_expediente", "seccion", "numero_anexo", "folio", "orden",
    "nombre_documento", "tipo_documento", "identificador_documento",
    "pagina_pdf", "fecha_documento", "fecha_recepcion", "tipo_referencia",
    "numero_referencia", "providencia", "observaciones", "referencia_file_server",
    "evidencia_folio", "confianza_lectura",
}
ANEXOS_OBLIGATORIAS = {
    "sp", "numero_anexo", "tipo_codigo", "titulo", "fecha_recepcion",
    "tipo_referencia", "numero_referencia", "providencia", "persona_entrega",
    "folios_recibidos", "es_vencido", "numero_reporte", "tipo_evento",
    "correlativo_analisis", "componentes", "observaciones", "referencia_file_server",
}
TIPOS = {"Documento", "Anexo", "Oficio", "Resolución", "Acta", "Informe", "Otro"}
MAX_FOLIOS = 1500
MAX_BYTES = 5 * 1024 * 1024


class ImportFIAInvalido(ValueError):
    pass


def texto(valor, maximo=8192, *, hoja=None, fila=None, campo=None):
    if valor is None:
        return ""
    dato = str(valor).strip()
    if len(dato) > maximo:
        ubicacion = f"{hoja} fila {fila}, columna {campo}" if hoja and fila and campo else "Excel"
        raise ImportFIAInvalido(
            f"{ubicacion}: texto de {len(dato)} caracteres supera el máximo de {maximo}. "
            "Revise la celda; no se truncará evidencia automáticamente."
        )
    return dato


def entero(valor, campo, fila):
    dato = texto(valor)
    if not re.fullmatch(r"[0-9]+(?:\.0)?", dato):
        raise ImportFIAInvalido(f"Fila {fila}: {campo} debe ser entero positivo.")
    n = int(float(dato))
    if n < 1:
        raise ImportFIAInvalido(f"Fila {fila}: {campo} debe ser mayor a cero.")
    return n


def _hoja(libro, nombre, obligatorias):
    hoja = libro[nombre]
    filas = hoja.iter_rows(values_only=True)
    try:
        cabecera = [texto(v, 120).lower() for v in next(filas)]
    except StopIteration as exc:
        raise ImportFIAInvalido(f"La hoja {nombre} está vacía.") from exc
    if len(cabecera) != len(set(cabecera)):
        raise ImportFIAInvalido(f"Encabezados duplicados en {nombre}.")
    faltantes = obligatorias - set(cabecera)
    if faltantes:
        raise ImportFIAInvalido(f"En {nombre} faltan columnas: {', '.join(sorted(faltantes))}.")
    return [(num, dict(zip(cabecera, valores))) for num, valores
            in enumerate(filas, 2) if any(v is not None and str(v).strip() for v in valores)]


def leer_importfia(archivo, expediente):
    if not (archivo.filename or "").lower().endswith(".xlsx"):
        raise ImportFIAInvalido("IMPORTF.IA requiere un archivo .xlsx.")
    contenido = archivo.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise ImportFIAInvalido("Archivo superior a 5 MB.")
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as exc:
        raise ImportFIAInvalido("El Excel no se puede abrir.") from exc
    try:
        faltantes = set(HOJAS) - set(libro.sheetnames)
        if faltantes:
            raise ImportFIAInvalido("Faltan hojas: " + ", ".join(sorted(faltantes)))
        folios_crudos = _hoja(libro, "FOLIOS", FOLIOS_OBLIGATORIAS)
        anexos_crudos = _hoja(libro, "ANEXOS", ANEXOS_OBLIGATORIAS)
        if not 1 <= len(folios_crudos) <= MAX_FOLIOS:
            raise ImportFIAInvalido("Se requieren entre 1 y 1500 filas de folios por expediente.")
        catalogo = catalogo_plano()
        anexos = {}
        for fila, r in anexos_crudos:
            if entero(r.get("sp"), "sp", fila) != int(expediente.no_sp):
                raise ImportFIAInvalido(f"ANEXOS fila {fila}: SP distinto del expediente.")
            numero = entero(r.get("numero_anexo"), "numero_anexo", fila)
            if numero > 200 or numero in anexos:
                raise ImportFIAInvalido(f"ANEXOS fila {fila}: número repetido o fuera de rango.")
            codigo = texto(r.get("tipo_codigo"), 120)
            if codigo not in catalogo:
                raise ImportFIAInvalido(f"ANEXOS fila {fila}: tipo_codigo no existe en catálogo.")
            datos = {campo: texto(r.get(campo), 8192, hoja="ANEXOS", fila=fila, campo=campo) for campo in ANEXOS_OBLIGATORIAS
                     if campo not in {"sp", "numero_anexo"}}
            if datos["es_vencido"].upper() not in {"SI", "NO", "DESCONOCIDO"}:
                raise ImportFIAInvalido(f"ANEXOS fila {fila}: es_vencido inválido.")
            if not datos["titulo"] or len(datos["titulo"]) > 180:
                raise ImportFIAInvalido(f"ANEXOS fila {fila}: título requerido (máximo 180).")
            anexos[numero] = datos
        folios = []
        vistos = set()
        por_ambito = defaultdict(list)
        for fila, r in folios_crudos:
            if entero(r.get("sp"), "sp", fila) != int(expediente.no_sp):
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: SP distinto del expediente.")
            codigo = texto(r.get("codigo_expediente"), 50)
            if codigo != expediente.codigo_interno:
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: código de expediente no coincide.")
            seccion = texto(r.get("seccion"), 20).upper()
            if seccion not in {"PRINCIPAL", "ANEXO"}:
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: sección no válida.")
            numero = entero(r.get("numero_anexo"), "numero_anexo", fila) if seccion == "ANEXO" else None
            if seccion == "PRINCIPAL" and texto(r.get("numero_anexo")):
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: principal no admite número de anexo.")
            if numero is not None and numero not in anexos:
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: el anexo {numero} no está descrito en ANEXOS.")
            folio = entero(r.get("folio"), "folio", fila)
            orden = entero(r.get("orden"), "orden", fila)
            nombre = texto(r.get("nombre_documento"), 180)
            tipo = texto(r.get("tipo_documento"), 80)
            fuente = texto(r.get("referencia_file_server"), 8192, hoja="FOLIOS", fila=fila, campo="referencia_file_server")
            evidencia = texto(r.get("evidencia_folio"), 8192, hoja="FOLIOS", fila=fila, campo="evidencia_folio")
            confianza = texto(r.get("confianza_lectura"), 20).upper()
            faltantes = []
            if not nombre:
                faltantes.append("nombre_documento")
            if not tipo:
                faltantes.append("tipo_documento")
            elif tipo not in TIPOS:
                raise ImportFIAInvalido(
                    f"FOLIOS fila {fila}: tipo_documento '{tipo}' no pertenece al catálogo."
                )
            if not fuente:
                faltantes.append("referencia_file_server")
            if not evidencia:
                faltantes.append("evidencia_folio")
            if faltantes:
                raise ImportFIAInvalido(
                    f"FOLIOS fila {fila}: campos obligatorios vacíos: {', '.join(faltantes)}."
                )
            if confianza not in {"ALTA", "MEDIA"}:
                raise ImportFIAInvalido(
                    f"FOLIOS fila {fila}: lectura BAJA o sin confianza; requiere revisión antes de importar.")
            identidad = (numero or 0, folio)
            if identidad in vistos:
                raise ImportFIAInvalido(f"FOLIOS fila {fila}: folio {folio} repetido en su ámbito.")
            vistos.add(identidad)
            por_ambito[numero or 0].append(folio)
            extras = []
            for campo in ("identificador_documento", "pagina_pdf", "fecha_documento",
                          "fecha_recepcion", "tipo_referencia", "numero_referencia", "providencia"):
                valor = texto(r.get(campo), 8192, hoja="FOLIOS", fila=fila, campo=campo)
                if valor:
                    extras.append(f"{campo}: {valor}")
            if numero:
                a = anexos[numero]
                extras += [f"anexo.{campo}: {valor}" for campo, valor in a.items()
                           if valor and campo != "observaciones"]
            observacion = texto(r.get("observaciones"), 8192, hoja="FOLIOS", fila=fila, campo="observaciones")
            if numero and anexos[numero].get("observaciones"):
                extras.append("anexo.observaciones: " + anexos[numero]["observaciones"])
            extras.append("File Server: " + fuente)
            extras.append("Evidencia de folio: " + evidencia)
            extras.append("Confianza OCR: " + confianza)
            if observacion:
                extras.append("Observaciones: " + observacion)
            folios.append({
                "numero": numero, "folio": folio, "orden": orden,
                "nombre": nombre, "tipo": tipo, "fuente": fuente,
                "evidencia": evidencia, "confianza": confianza,
                "observaciones": "; ".join(extras),
                "titulo": anexos[numero]["titulo"] if numero else "",
                "tipo_codigo": anexos[numero]["tipo_codigo"] if numero else "",
            })
        return folios, anexos, dict(por_ambito)
    finally:
        libro.close()
