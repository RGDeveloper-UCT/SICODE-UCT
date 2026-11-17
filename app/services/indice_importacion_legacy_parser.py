"""Lector histórico del Excel Indice. Conservado para compatibilidad y pruebas.

La interfaz IMPORTF.IA nueva usa exclusivamente importfia_service.
"""
import csv
import io
import re
from collections import defaultdict
from openpyxl import load_workbook

COLUMNAS = {"sp", "codigo_expediente", "seccion", "numero_anexo", "titulo_anexo",
            "orden", "nombre_documento", "folio_inicial", "folio_final", "estado_revision", "observaciones"}
ESTADOS = {"Pendiente de revisión", "Con observaciones", "Mal foliado", "Anexo pendiente"}
MAX_FILAS = 1500


class ImportacionInvalida(ValueError):
    pass


def _texto(v):
    return str(v).strip() if v is not None else ""


def _entero(v, campo, fila):
    valor = _texto(v)
    if not re.fullmatch(r"[0-9]+(?:\.0)?", valor):
        raise ImportacionInvalida(f"Fila {fila}: {campo} no es entero válido.")
    return int(float(valor))


def _leer(archivo, expediente):
    nombre = (archivo.filename or "").lower()
    contenido = archivo.read(1024 * 1024 + 1)
    if len(contenido) > 1024 * 1024:
        raise ImportacionInvalida("Máximo permitido: 1 MB.")
    if nombre.endswith(".csv"):
        try:
            filas = list(csv.DictReader(io.StringIO(contenido.decode("utf-8-sig"))))
        except (UnicodeError, csv.Error) as error:
            raise ImportacionInvalida("CSV inválido; utilice UTF-8.") from error
    elif nombre.endswith(".xlsx"):
        try:
            libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
            hoja = libro["Indice"] if "Indice" in libro.sheetnames else libro.active
            valores = hoja.iter_rows(values_only=True)
            columnas = [_texto(x).lower() for x in next(valores)]
            filas = [dict(zip(columnas, valores_fila)) for valores_fila in valores if any(v is not None for v in valores_fila)]
            libro.close()
        except Exception as error:
            raise ImportacionInvalida("Excel inválido o sin hoja Indice.") from error
    else:
        raise ImportacionInvalida("Formato no permitido: utilice .xlsx o .csv.")
    if not filas or len(filas) > MAX_FILAS:
        raise ImportacionInvalida("Se requieren entre 1 y 1500 registros.")
    if not COLUMNAS.issubset(set(filas[0])):
        raise ImportacionInvalida("Columnas faltantes: " + ", ".join(sorted(COLUMNAS - set(filas[0]))))
    registros = []
    grupos = defaultdict(list)
    for fila, item in enumerate(filas, 2):
        sp = _entero(item.get("sp"), "sp", fila)
        if str(sp) != str(expediente.no_sp):
            raise ImportacionInvalida(f"Fila {fila}: SP {sp} distinto del expediente abierto.")
        codigo = _texto(item.get("codigo_expediente"))
        if codigo and codigo != expediente.codigo_interno:
            raise ImportacionInvalida(f"Fila {fila}: código interno no coincide.")
        seccion = _texto(item.get("seccion")).upper()
        if seccion not in ("PRINCIPAL", "ANEXO"):
            raise ImportacionInvalida(f"Fila {fila}: sección debe ser PRINCIPAL o ANEXO.")
        numero = _entero(item.get("numero_anexo"), "numero_anexo", fila) if seccion == "ANEXO" else None
        if numero is not None and not 1 <= numero <= 200:
            raise ImportacionInvalida(f"Fila {fila}: anexo fuera del rango 1-200.")
        if seccion == "PRINCIPAL" and _texto(item.get("numero_anexo")):
            raise ImportacionInvalida(f"Fila {fila}: sección principal no debe tener número de anexo.")
        inicio = _entero(item.get("folio_inicial"), "folio_inicial", fila)
        fin = _entero(item.get("folio_final"), "folio_final", fila)
        orden = _entero(item.get("orden"), "orden", fila)
        if inicio < 1 or fin < inicio or orden < 1:
            raise ImportacionInvalida(f"Fila {fila}: rango u orden incorrecto.")
        titulo = _texto(item.get("titulo_anexo")) if numero else ""
        nombre = _texto(item.get("nombre_documento"))
        estado = _texto(item.get("estado_revision")) or "Pendiente de revisión"
        observaciones = _texto(item.get("observaciones"))
        if not nombre or len(nombre) > 180 or len(titulo) > 180 or len(observaciones) > 1000:
            raise ImportacionInvalida(f"Fila {fila}: título, nombre u observaciones inválidos.")
        if estado not in ESTADOS:
            raise ImportacionInvalida(f"Fila {fila}: estado no admitido ({estado}).")
        registro = dict(seccion=seccion, numero=numero, titulo=titulo, orden=orden,
                        nombre=nombre, inicio=inicio, fin=fin, estado=estado, observaciones=observaciones)
        registros.append(registro)
        grupos[numero or 0].append(registro)
    alertas = []
    for numero, registros_grupo in grupos.items():
        vistos = set()
        titulo_anexo = {r["titulo"] for r in registros_grupo} if numero else set()
        if len(titulo_anexo) > 1:
            raise ImportacionInvalida(f"Anexo {numero}: títulos inconsistentes.")
        for r in sorted(registros_grupo, key=lambda x: (x["inicio"], x["fin"])):
            for folio in range(r["inicio"], r["fin"] + 1):
                if folio in vistos:
                    raise ImportacionInvalida(f"{'Principal' if numero == 0 else 'Anexo '+str(numero)}: traslape en folio {folio}.")
                vistos.add(folio)
        if vistos and (min(vistos) != 1 or len(vistos) != max(vistos)):
            alertas.append(f"{'Principal' if numero == 0 else 'Anexo '+str(numero)}: faltan folios en la secuencia.")
    return registros, alertas


