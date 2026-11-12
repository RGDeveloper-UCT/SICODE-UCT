"""Validación conservadora del contrato ImportM.IA v3.

ImportM.IA recibe metadatos de Work. No persiste archivos/documentos ni
considera el Excel una autoridad para renumerar anexos o rectificar folios.
"""
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from openpyxl import load_workbook

from app.services.importacion_indice_fileserver_service import (
    COLUMNAS as COLUMNAS_INDICE, leer_excel, planificar,
)

VERSION = "3"
MAX_XLSX = 8 * 1024 * 1024
MAX_DESCOMPRIMIDO = 80 * 1024 * 1024
MAX_FILAS = 12000

HOJAS = {
    "LOTE": {"lote_id", "version_contrato"},
    "INVENTARIO_FILESERVER": {"documento_id", "archivo_id", "sp_observado"},
    "Indice": set(COLUMNAS_INDICE),
    "ANEXOS": {"documento_id", "sp", "numero_anexo_file_server"},
    "PAGOS": {"documento_id", "sp", "banco", "boleta", "monto", "periodo_desde", "periodo_hasta"},
    "ANALISIS_RIESGO": {"documento_id", "sp", "correlativo", "fecha_recepcion"},
    "EXPEDIENTE_COMPLETO": {"documento_id", "sp"},
    "ARCHIVOS": {"archivo_id", "documento_id", "sha256", "referencia_file_server"},
    "RELACIONES": {"documento_id", "archivo_id", "sp"},
    "SNAPSHOT_SICODE": {"fecha_snapshot", "sp"},
    "CONCILIACION": {"documento_id", "sp", "resultado"},
    "INCIDENCIAS": {"lote_id", "documento_id", "codigo_incidencia"},
    "MONITOREO": {"documento_id", "sp"},
    "MOVIMIENTOS": {"documento_id", "sp"},
    "OTROS_DOCUMENTOS": {"documento_id", "sp"},
    "RECEPCION_COLA": {"correlativo_cola_sicode", "lote_id"},
    "FUENTES_CAMPOS": {"documento_id", "campo_destino", "fuente_primaria"},
    "CONFLICTOS_NUMERACION": {"documento_id", "sp"},
    "ESTADO_POR_SP": {"sp"},
    "CATALOGOS": {"catalogo", "codigo"},
    "MAPEO_SICODE": {"hoja", "columna"},
    "MATRIZ_VALIDACION": {"area", "campo"},
    "CONTROL_VERSION": {"elemento", "valor"},
    "INSTRUCCIONES": {"paso", "instruccion"},
}

class ImportMIAInvalido(ValueError):
    pass

def _valor(valor):
    return str(valor).strip() if valor is not None else ""

def _sp(valor):
    from app.services.importacion_indice_fileserver_service import normalizar_sp
    return normalizar_sp(valor)

def validar_libro(datos):
    """Validación de contrato sin confiar en identificadores internos del Excel."""
    if not datos or len(datos) > MAX_XLSX:
        raise ImportMIAInvalido("Archivo ausente o superior a 8 MB.")
    try:
        with ZipFile(BytesIO(datos)) as z:
            elementos = z.infolist()
            if len(elementos) > 1000 or sum(i.file_size for i in elementos) > MAX_DESCOMPRIMIDO:
                raise ImportMIAInvalido("El libro excede los límites de descompresión.")
        libro = load_workbook(BytesIO(datos), read_only=True, data_only=True, keep_links=False)
    except (BadZipFile, ValueError, OSError) as exc:
        raise ImportMIAInvalido("El archivo no es un XLSX válido.") from exc
    except Exception as exc:
        raise ImportMIAInvalido("No se pudo leer el Excel.") from exc

    conteos = {}
    incidencias = []
    try:
        for hoja, requeridas in HOJAS.items():
            if hoja not in libro.sheetnames:
                incidencias.append(f"Falta hoja obligatoria: {hoja}.")
                continue
            iterador = libro[hoja].iter_rows(values_only=True)
            cabecera = next(iterador, None)
            if cabecera is None:
                incidencias.append(f"{hoja}: sin encabezados.")
                continue
            encabezados = [_valor(c) for c in cabecera]
            if len(encabezados) != len(set(encabezados)):
                incidencias.append(f"{hoja}: encabezados repetidos.")
            faltantes = requeridas - set(encabezados)
            if faltantes:
                incidencias.append(f"{hoja}: faltan {', '.join(sorted(faltantes))}.")
            n = 0
            for fila in iterador:
                if any(_valor(c) for c in fila):
                    n += 1
                    if n > MAX_FILAS:
                        incidencias.append(f"{hoja}: supera {MAX_FILAS} filas.")
                        break
            conteos[hoja] = n
        if "LOTE" in libro.sheetnames:
            it = libro["LOTE"].iter_rows(values_only=True)
            header = [_valor(v) for v in next(it, ())]
            lote = dict(zip(header, next(it, ())))
            version = _valor(lote.get("version_contrato"))
            if version and version not in {"3", "v3", "V3", "3.0"}:
                incidencias.append(f"Versión del contrato no soportada: {version}.")
    finally:
        libro.close()
    if incidencias:
        raise ImportMIAInvalido(" | ".join(incidencias[:25]))
    return conteos

def conciliar(datos):
    """Reutiliza el conciliador productivo del índice; el resto solo se reporta."""
    from werkzeug.datastructures import FileStorage
    validar_libro(datos)
    archivo = FileStorage(stream=BytesIO(datos), filename="importmia.xlsx")
    try:
        filas = leer_excel(archivo)
        decisiones, resumen = planificar(filas)
    except Exception as exc:
        if "No hay registros en la hoja Indice" in str(exc):
            filas, decisiones, resumen = [], [], {"NUEVO": 0, "COINCIDE": 0}
        else:
            raise ImportMIAInvalido(str(exc)) from exc

    libro = load_workbook(BytesIO(datos), read_only=True, data_only=True, keep_links=False)
    try:
        metadatos = {}
        for hoja in ("ANEXOS", "PAGOS", "ANALISIS_RIESGO", "MONITOREO", "MOVIMIENTOS",
                     "EXPEDIENTE_COMPLETO", "OTROS_DOCUMENTOS", "INVENTARIO_FILESERVER"):
            sheet = libro[hoja]
            cabecera = [_valor(c) for c in next(sheet.iter_rows(values_only=True))]
            filas_hoja = []
            for indice, valores in enumerate(sheet.iter_rows(min_row=2, values_only=True)):\n                if indice >= MAX_FILAS:\n                    break
                if not any(_valor(c) for c in valores):
                    continue
                registro = dict(zip(cabecera, valores))
                filas_hoja.append(registro)
            metadatos[hoja] = filas_hoja
    finally:
        libro.close()

    # Las hojas especializadas requieren adaptadores de escritura y revisión
    # de reglas; se muestran como pendientes, nunca como importadas.
    pendientes = {nombre: len(filas) for nombre, filas in metadatos.items()}
    return {"decisiones": decisiones, "resumen": resumen,
            "pendientes": pendientes, "filas": filas}
