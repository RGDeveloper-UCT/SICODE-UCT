"""ImportM.IA v4: contrato simple y conciliación de metadatos, nunca PDF."""
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import ZipFile, BadZipFile

from openpyxl import load_workbook
from werkzeug.datastructures import FileStorage

from app import db
from app.models.coordinacion import (
    AnexoCoordinacion, AnalisisRiesgo, PagoCoordinacion, RegistroCoordinacion,
)
from app.models.expediente import Expediente
from app.services.catalogo_anexos_service import catalogo_plano
from app.services.importacion_indice_fileserver_service import (
    COLUMNAS as INDICE_HEADERS, leer_excel, planificar, normalizar, normalizar_sp,
)
from app.routes.monitoreo_anexos import _estado_anexos, _validar_numero

MAX_BYTES = 8 * 1024 * 1024
MAX_EXPANDED = 80 * 1024 * 1024
MAX_ROWS = 12000
HEADERS = {
    "EXPEDIENTES": ("sp", "expediente_fisico", "evidencia_recepcion", "observaciones"),
    "Indice": INDICE_HEADERS,
    "ANEXOS": (
        "sp", "numero_anexo", "tipo_codigo", "titulo", "fecha_recepcion",
        "tipo_referencia", "numero_referencia", "providencia", "persona_entrega",
        "folios_recibidos", "es_vencido", "referencia_file_server",
        "correlativo_analisis", "numero_reporte", "tipo_evento", "componentes",
        "observaciones",
    ),
    "PAGOS": (
        "sp", "banco", "boleta", "monto", "periodo_desde", "periodo_hasta",
        "tipo_referencia", "numero_referencia", "providencia",
        "fecha_recepcion", "referencia_file_server", "observaciones",
    ),
}
VALID_STATES = {"SI", "NO", "DESCONOCIDO"}

class ImportMIAInvalido(ValueError):
    pass

def texto(value, limit=250):
    value = str(value).strip() if value is not None else ""
    if len(value) > limit:
        raise ImportMIAInvalido("Un campo excede su longitud máxima.")
    return value

def fecha(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(texto(value, 30))
    except ValueError:
        raise ImportMIAInvalido("Fecha inválida; utilice AAAA-MM-DD.")

def numero(value):
    try:
        v = int(texto(value, 16))
    except (ValueError, TypeError):
        return None
    return v if 1 <= v <= 200 else None

def importe(value):
    try:
        n = Decimal(texto(value, 30))
        if not n.is_finite() or n <= 0 or n > Decimal("9999999999.99"):
            return None
        return n.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None

def referencia(row):
    tipo = texto(row.get("tipo_referencia"), 5).upper()
    num = texto(row.get("numero_referencia"), 76)
    if tipo not in {"RC", "RE"} or not num:
        return None
    import re
    num = re.sub(r"^(RC|RE)\s*[-:/]?\s*", "", num, flags=re.IGNORECASE).strip()
    return f"{tipo} {num}" if num else None

def leer(datos):
    if not datos or len(datos) > MAX_BYTES:
        raise ImportMIAInvalido("El Excel está vacío o supera 8 MB.")
    try:
        with ZipFile(BytesIO(datos)) as zipped:
            info = zipped.infolist()
            if len(info) > 1000 or sum(i.file_size for i in info) > MAX_EXPANDED:
                raise ImportMIAInvalido("Excel demasiado grande al descomprimirse.")
        book = load_workbook(BytesIO(datos), read_only=True, data_only=True, keep_links=False)
    except (BadZipFile, ValueError, OSError) as exc:
        raise ImportMIAInvalido("Debe subir un libro Excel .xlsx válido.") from exc
    except ImportMIAInvalido:
        raise
    except Exception as exc:
        raise ImportMIAInvalido("No se puede leer el libro Excel.") from exc
    out = {}
    try:
        for name, required in HEADERS.items():
            if name not in book.sheetnames:
                raise ImportMIAInvalido(f"Falta la hoja {name}.")
            it = book[name].iter_rows(values_only=True)
            raw = next(it, ())
            headers = [texto(v, 100) for v in raw]
            if len(headers) != len(set(headers)) or not set(required).issubset(headers):
                raise ImportMIAInvalido(f"Encabezados faltantes o repetidos en {name}.")
            rows = []
            for i, values in enumerate(it, 2):
                if any(v is not None and str(v).strip() for v in values):
                    if len(rows) >= MAX_ROWS:
                        raise ImportMIAInvalido(f"{name}: máximo {MAX_ROWS} filas.")
                    d = dict(zip(headers, values))
                    d["_fila"] = i
                    rows.append(d)
            out[name] = rows
    finally:
        book.close()
    return out

def _estado(result, estado, detalle):
    result["estado"] = estado
    result["detalle"] = detalle
    return result

def conciliar(datos):
    hojas = leer(datos)
    expedientes = {e.no_sp: e for e in Expediente.query.all()}
    resultados = {"EXPEDIENTES": [], "Indice": [], "ANEXOS": [], "PAGOS": []}
    for r in hojas["EXPEDIENTES"]:
        sp = normalizar_sp(r.get("sp"))
        e = expedientes.get(sp)
        decision = {"fila": r["_fila"], "sp": sp, "expediente": e,
                    "original": r}
        valor = texto(r.get("expediente_fisico"), 20).upper()
        if not e:
            _estado(decision, "SP_NO_EXISTE", "No se crea un SP desde File Server.")
        elif valor not in {"SI", "NO", "NO_CONSTA"}:
            _estado(decision, "REVISAR", "Use SI, NO o NO_CONSTA.")
        elif valor == "NO_CONSTA":
            _estado(decision, "SOLO_INFORMATIVO", "Sin evidencia de recepción física.")
        elif (valor == "SI") != bool(e.expediente_fisico_registrado):
            _estado(decision, "DIFERENCIA_FISICO",
                    "No se cambia la recepción física desde un escaneo. Revisión institucional.")
        else:
            _estado(decision, "COINCIDE", "Indicador físico actual conservado.")
        resultados["EXPEDIENTES"].append(decision)
    if hojas["Indice"]:
        archivo = FileStorage(stream=BytesIO(datos), filename="importmia-simple.xlsx")
        try:
            filas = leer_excel(archivo)
            decisiones, _ = planificar(filas)
        except Exception as exc:
            raise ImportMIAInvalido(f"Hoja Indice: {exc}") from exc
        for d in decisiones:
            resultados["Indice"].append({
                "fila": d["fila"], "sp": d["sp"], "estado": d["estado"],
                "detalle": d.get("detalle", ""), "original": d,
            })
    catalogo = catalogo_plano()
    vistos_anexos = set()
    correlativos_lote = set()
    nuevos_ordenados = defaultdict(list)
    for r in hojas["ANEXOS"]:
        sp = normalizar_sp(r.get("sp"))
        e = expedientes.get(sp)
        n = numero(r.get("numero_anexo"))
        codigo = texto(r.get("tipo_codigo"), 100).upper()
        venc = texto(r.get("es_vencido"), 20).upper()
        d = {"fila": r["_fila"], "sp": sp, "numero": n, "original": r}
        key = (sp, n)
        if not e or not e.activo:
            _estado(d, "SP_NO_EXISTE", "SP inexistente o inactivo.")
        elif n is None or codigo not in catalogo or codigo == "ANALISIS_RIESGO_MASIVO":
            _estado(d, "REVISAR", "Número (1–200) o tipo de anexo no válido.")
        elif venc not in VALID_STATES or venc == "DESCONOCIDO":
            _estado(d, "REVISAR", "Debe confirmarse si el anexo está vencido.")
        elif key in vistos_anexos:
            _estado(d, "DUPLICADO_EXCEL", "Número repetido en el mismo lote.")
        else:
            vistos_anexos.add(key)
            existente = (AnexoCoordinacion.query.join(RegistroCoordinacion)
                .filter(RegistroCoordinacion.expediente_id == e.id).all())
            numeros = [a for a in existente if numero(a.numero_anexo) == n]
            if numeros:
                a = numeros[0]
                nombre = normalizar(a.tipo_anexo or a.titulo or "")
                nombre_nuevo = normalizar(catalogo[codigo]["titulo"])
                if len(numeros) == 1 and (nombre == nombre_nuevo or normalizar(a.titulo or "") == normalizar(texto(r.get("titulo"), 180))) and bool(a.es_vencido) == (venc == "SI"):
                    _estado(d, "COINCIDE", "Anexo ya registrado; se conserva.")
                else:
                    _estado(d, "DIFERENCIA_ANEXO", "Existe un anexo con ese número: comparar clasificación, fecha y vencimiento.")
            elif not fecha(r.get("fecha_recepcion")):
                _estado(d, "REVISAR", "Falta fecha de recepción acreditada.")
            elif codigo == "ANALISIS_RIESGO" and not texto(r.get("correlativo_analisis"), 120):
                _estado(d, "REVISAR", "Falta correlativo de análisis de riesgo.")
            elif codigo == "ANALISIS_RIESGO" and texto(r.get("correlativo_analisis"), 120).casefold() in correlativos_lote:
                _estado(d, "DUPLICADO_EXCEL", "Correlativo de análisis repetido en el lote.")
            elif codigo == "ANALISIS_RIESGO" and (db.session.query(AnalisisRiesgo.id)
                .filter(db.func.lower(AnalisisRiesgo.correlativo) ==
                        texto(r.get("correlativo_analisis"), 120).lower()).first()):
                _estado(d, "DUPLICADO", "Correlativo de análisis ya existe.")
            else:
                _estado(d, "PENDIENTE_SECUENCIA", "Se revisará la secuencia del SP.")
                nuevos_ordenados[sp].append(d)
                if codigo == "ANALISIS_RIESGO":
                    correlativos_lote.add(texto(r.get("correlativo_analisis"), 120).casefold())
        resultados["ANEXOS"].append(d)
    for sp, candidatos in nuevos_ordenados.items():
        e = expedientes[sp]
        estado = _estado_anexos(e)
        esperable = estado.get("siguiente_anexo")
        for d in sorted(candidatos, key=lambda x: x["numero"]):
            venc = texto(d["original"].get("es_vencido"), 20).upper() == "SI"
            if estado["requiere_rectificacion"]:
                _estado(d, "REVISAR_RECTIFICACION", "Rectificar anexos del SP antes de importar.")
            elif venc:
                _, error = _validar_numero(e, d["numero"], True)
                _estado(d, "NUEVO" if not error else "REVISAR_SECUENCIA", error or "Histórico verificado.")
            elif d["numero"] == esperable:
                _estado(d, "NUEVO", "Nuevo anexo vigente en secuencia.")
                esperable += 1
            else:
                _estado(d, "REVISAR_SECUENCIA",
                        f"Anexo fuera de secuencia. Siguiente esperado: {esperable}.")
    vistos_pago = set()
    for r in hojas["PAGOS"]:
        sp = normalizar_sp(r.get("sp"))
        e = expedientes.get(sp)
        banco = texto(r.get("banco"), 120)
        boleta = texto(r.get("boleta"), 120)
        monto = importe(r.get("monto"))
        try:
            desde, hasta = fecha(r.get("periodo_desde")), fecha(r.get("periodo_hasta"))
        except ImportMIAInvalido:
            desde = hasta = None
        d = {"fila": r["_fila"], "sp": sp, "original": r}
        clave = (banco.casefold(), boleta.casefold())
        if not e or not e.activo:
            _estado(d, "SP_NO_EXISTE", "SP inexistente o inactivo.")
        elif not (banco and boleta and monto and desde and hasta and hasta >= desde
                  and referencia(r) and texto(r.get("providencia"), 120)
                  and fecha(r.get("fecha_recepcion"))):
            _estado(d, "REVISAR", "Pago incompleto: banco, boleta, monto, período, RC/RE, providencia o fecha de recepción.")
        elif clave in vistos_pago:
            _estado(d, "DUPLICADO_EXCEL", "Boleta y banco repetidos en Excel.")
        else:
            vistos_pago.add(clave)
            registro = (PagoCoordinacion.query.join(RegistroCoordinacion)
                .filter(db.func.lower(PagoCoordinacion.banco) == banco.lower(),
                        db.func.lower(PagoCoordinacion.boleta) == boleta.lower()).first())
            if registro:
                anterior = registro.registro
                coincide = (anterior.expediente_id == e.id and
                            registro.total == monto and registro.periodo_desde == desde
                            and registro.periodo_hasta == hasta)
                _estado(d, "COINCIDE" if coincide else "DIFERENCIA_PAGO",
                        "Boleta existente; no se duplica." if coincide else "Boleta existente con datos contradictorios.")
            else:
                _estado(d, "NUEVO", "Pago acreditado que podrá registrarse.")
        resultados["PAGOS"].append(d)
    resumen = Counter(d["estado"] for grupo in resultados.values() for d in grupo)
    return {"grupos": resultados, "resumen": dict(resumen),
            "total": sum(len(g) for g in resultados.values())}
