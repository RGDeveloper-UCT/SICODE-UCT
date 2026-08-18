from datetime import date, datetime
from pathlib import Path
import hashlib
import re
import unicodedata

import xlrd

from app import db
from app.models.coordinacion import RegistroCoordinacion, RemisionExpediente
from app.models.expediente import Expediente
from app.models.importacion_portadores import ImportacionPortadores
from app.services.coordinacion_service import recalcular_estado_registro
from app.services.sp_service import normalizar_sp


MAPEO_COLUMNAS = {
    "nombres": "nombres",
    "apellidos": "apellidos",
    "nombre completo": "nombre_referencia",
    "genero": "genero",
    "fecha de nacimiento": "fecha_nacimiento",
    "fecha instalacion": "fecha_instalacion",
    "fecha desinstalacion": "fecha_desinstalacion",
    "expediente organismo judicial": "expediente_oj",
    "delito": "delito",
    "estado": "estado_portador",
    "juez": "juez",
    "juzgado tribunal": "juzgado_tribunal",
    "abogado": "abogado",
    "residencia": "residencia",
    "municipio": "municipio",
    "departamento": "departamento",
    "zona de inclusion": "zona_inclusion",
    "zona de exclusion": "zona_exclusion",
    "zona de prevencion": "zona_prevencion",
    "financiamiento": "financiamiento",
    "lugar de instalacion": "lugar_instalacion",
    "no sujeto portador": "no_sp",
    "estado de monitoreo": "estado_monitoreo",
    "telefono": "telefono",
    "municipio residencia": "municipio_residencia",
    "departamento residencia": "departamento_residencia",
}

CAMPOS_FECHA = {"fecha_nacimiento", "fecha_instalacion", "fecha_desinstalacion"}
CAMPOS_ACTUALIZABLES = [campo for campo in MAPEO_COLUMNAS.values() if campo != "no_sp"]


class ErrorMantaPortadores(ValueError):
    pass


def _normalizar_encabezado(valor):
    texto = str(valor or "").strip().lower().replace("*", "")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    return texto or None


def _valor_fecha(libro, hoja, fila, columna):
    celda = hoja.cell(fila, columna)
    valor = celda.value
    if valor in (None, ""):
        return None

    if celda.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(valor, libro.datemode).date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _valor_celda(libro, hoja, fila, columna, campo):
    if campo in CAMPOS_FECHA:
        return _valor_fecha(libro, hoja, fila, columna)
    return _texto(hoja.cell_value(fila, columna))


def _hash_archivo(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _encontrar_encabezado(hoja):
    limite = min(hoja.nrows, 40)
    for fila in range(limite):
        encabezados = [_normalizar_encabezado(hoja.cell_value(fila, col)) for col in range(hoja.ncols)]
        if "no sujeto portador" in encabezados and "nombre completo" in encabezados:
            return fila, encabezados
    raise ErrorMantaPortadores(
        "No se encontró la fila de encabezados esperada. El archivo debe ser la manta 'GT - Wearer List - Sujetos Portadores'."
    )


def leer_manta_portadores(ruta):
    try:
        libro = xlrd.open_workbook(str(ruta), on_demand=True)
    except Exception as error:
        raise ErrorMantaPortadores(f"No fue posible abrir el archivo .xls: {error}") from error

    try:
        if not libro.sheet_names():
            raise ErrorMantaPortadores("El archivo no contiene hojas.")

        hoja = libro.sheet_by_index(0)
        fila_encabezado, encabezados = _encontrar_encabezado(hoja)
        columnas = {}
        for indice, encabezado in enumerate(encabezados):
            campo = MAPEO_COLUMNAS.get(encabezado)
            if campo:
                columnas[campo] = indice

        if "no_sp" not in columnas:
            raise ErrorMantaPortadores("No se encontró la columna 'No. Sujeto Portador'.")

        registros = []
        for fila in range(fila_encabezado + 1, hoja.nrows):
            no_sp = normalizar_sp(_texto(hoja.cell_value(fila, columnas["no_sp"])))
            if not no_sp:
                continue

            datos = {"no_sp": no_sp, "fila_origen": fila + 1}
            for campo, columna in columnas.items():
                if campo != "no_sp":
                    datos[campo] = _valor_celda(libro, hoja, fila, columna, campo)

            if not datos.get("nombre_referencia"):
                nombre = " ".join(
                    valor for valor in [datos.get("nombres"), datos.get("apellidos")] if valor
                ).strip()
                datos["nombre_referencia"] = nombre or None

            registros.append(datos)

        if not registros:
            raise ErrorMantaPortadores("No se encontraron Sujetos Portadores con número de SP en el archivo.")
        return registros
    finally:
        libro.release_resources()


def _mapa_expedientes_existentes():
    mapa = {}
    duplicados = set()
    for expediente in Expediente.query.all():
        clave = normalizar_sp(expediente.no_sp)
        if not clave:
            continue
        if clave in mapa and mapa[clave].id != expediente.id:
            duplicados.add(clave)
            continue
        mapa[clave] = expediente
    return mapa, duplicados


def _campos_con_cambio(expediente, datos):
    cambios = []
    for campo in CAMPOS_ACTUALIZABLES:
        nuevo = datos.get(campo)
        if nuevo is None or (isinstance(nuevo, str) and not nuevo.strip()):
            continue
        if getattr(expediente, campo, None) != nuevo:
            cambios.append(campo)
    return cambios


def analizar_manta(ruta, limite_previsualizacion=100):
    registros = leer_manta_portadores(ruta)
    mapa, duplicados_existentes = _mapa_expedientes_existentes()

    vistos = set()
    duplicados_archivo = set()
    resumen = {
        "total": len(registros),
        "nuevos": 0,
        "actualizados": 0,
        "sin_cambios": 0,
        "omitidos": 0,
        "duplicados": 0,
        "ya_importado": ImportacionPortadores.query.filter_by(archivo_hash=_hash_archivo(ruta)).first() is not None,
        "advertencias": [],
        "previsualizacion": [],
    }

    if duplicados_existentes:
        resumen["advertencias"].append(
            "Existen SP duplicados lógicamente en SICODE: " + ", ".join(sorted(duplicados_existentes)) + ". No se crearán nuevos duplicados."
        )

    for datos in registros:
        no_sp = datos["no_sp"]
        if no_sp in vistos:
            duplicados_archivo.add(no_sp)
            resumen["duplicados"] += 1
            resumen["omitidos"] += 1
            accion = "Duplicado en archivo"
        else:
            vistos.add(no_sp)
            expediente = mapa.get(no_sp)
            if expediente is None:
                resumen["nuevos"] += 1
                accion = "Crear SP"
            else:
                cambios = _campos_con_cambio(expediente, datos)
                if cambios:
                    resumen["actualizados"] += 1
                    accion = "Actualizar"
                else:
                    resumen["sin_cambios"] += 1
                    accion = "Sin cambios"

        if len(resumen["previsualizacion"]) < limite_previsualizacion:
            resumen["previsualizacion"].append({
                "fila": datos["fila_origen"],
                "no_sp": no_sp,
                "nombre": datos.get("nombre_referencia"),
                "estado_monitoreo": datos.get("estado_monitoreo"),
                "fecha_instalacion": datos.get("fecha_instalacion"),
                "accion": accion,
            })

    if duplicados_archivo:
        resumen["advertencias"].append(
            "La manta contiene SP repetidos: " + ", ".join(sorted(duplicados_archivo)) + ". Las repeticiones posteriores se omitirán."
        )
    return resumen


def _generador_codigos():
    usados = {expediente.codigo_interno for expediente in Expediente.query.all()}
    maximo = 0
    patron = re.compile(r"^SICODE-UCT-(\d+)$", re.IGNORECASE)
    for codigo in usados:
        coincidencia = patron.match(codigo or "")
        if coincidencia:
            maximo = max(maximo, int(coincidencia.group(1)))

    def generar(no_sp):
        nonlocal maximo
        if str(no_sp).isdigit():
            candidato = f"SICODE-UCT-{int(no_sp):04d}"
            if candidato not in usados:
                usados.add(candidato)
                maximo = max(maximo, int(no_sp))
                return candidato
        while True:
            maximo += 1
            candidato = f"SICODE-UCT-{maximo:04d}"
            if candidato not in usados:
                usados.add(candidato)
                return candidato
    return generar


def _aplicar_datos(expediente, datos, momento):
    for campo in CAMPOS_ACTUALIZABLES:
        nuevo = datos.get(campo)
        if nuevo is None or (isinstance(nuevo, str) and not nuevo.strip()):
            continue
        setattr(expediente, campo, nuevo)
    expediente.ultima_sincronizacion_portadores = momento


def reconciliar_coordinacion():
    mapa, _ = _mapa_expedientes_existentes()
    vinculados = 0

    pendientes = RegistroCoordinacion.query.filter(
        RegistroCoordinacion.expediente_id.is_(None),
        RegistroCoordinacion.no_sp_referencia.isnot(None),
    ).all()
    for registro in pendientes:
        expediente = mapa.get(normalizar_sp(registro.no_sp_referencia))
        if expediente:
            registro.expediente_id = expediente.id
            registro.estado = recalcular_estado_registro(registro)
            vinculados += 1

    detalles_remision = RemisionExpediente.query.filter(RemisionExpediente.expediente_id.is_(None)).all()
    remisiones_afectadas = set()
    for detalle in detalles_remision:
        expediente = mapa.get(normalizar_sp(detalle.no_sp_referencia))
        if expediente:
            detalle.expediente_id = expediente.id
            remisiones_afectadas.add(detalle.remision_id)
            vinculados += 1

    for detalle in detalles_remision:
        if detalle.remision_id in remisiones_afectadas:
            detalle.remision.registro.estado = recalcular_estado_registro(detalle.remision.registro)
    return vinculados


def importar_manta(ruta, usuario_id, archivo_nombre):
    archivo_hash = _hash_archivo(ruta)
    if ImportacionPortadores.query.filter_by(archivo_hash=archivo_hash).first():
        raise ErrorMantaPortadores("Este mismo archivo ya fue sincronizado anteriormente.")

    registros = leer_manta_portadores(ruta)
    mapa, duplicados_existentes = _mapa_expedientes_existentes()
    generar_codigo = _generador_codigos()
    momento = datetime.utcnow()
    vistos = set()
    resultado = {
        "total": len(registros), "nuevos": 0, "actualizados": 0,
        "sin_cambios": 0, "omitidos": 0, "duplicados": 0,
        "vinculados_coordinacion": 0,
    }

    try:
        for datos in registros:
            no_sp = datos["no_sp"]
            if no_sp in vistos:
                resultado["duplicados"] += 1
                resultado["omitidos"] += 1
                continue
            vistos.add(no_sp)

            if no_sp in duplicados_existentes:
                resultado["omitidos"] += 1
                continue

            expediente = mapa.get(no_sp)
            if expediente is None:
                expediente = Expediente(
                    codigo_interno=generar_codigo(no_sp),
                    no_sp=no_sp,
                    nombre_referencia=datos.get("nombre_referencia"),
                    estado_administrativo="Activo",
                    estado_fisico_documental="Sin expediente físico",
                    expediente_fisico_registrado=False,
                    activo=True,
                )
                _aplicar_datos(expediente, datos, momento)
                db.session.add(expediente)
                db.session.flush()
                mapa[no_sp] = expediente
                resultado["nuevos"] += 1
            else:
                cambios = _campos_con_cambio(expediente, datos)
                _aplicar_datos(expediente, datos, momento)
                if cambios:
                    resultado["actualizados"] += 1
                else:
                    resultado["sin_cambios"] += 1

        db.session.flush()
        resultado["vinculados_coordinacion"] = reconciliar_coordinacion()

        historial = ImportacionPortadores(
            archivo_nombre=archivo_nombre,
            archivo_hash=archivo_hash,
            usuario_id=usuario_id,
            total_filas=resultado["total"],
            nuevos=resultado["nuevos"],
            actualizados=resultado["actualizados"],
            sin_cambios=resultado["sin_cambios"],
            omitidos=resultado["omitidos"],
            duplicados=resultado["duplicados"],
            vinculados_coordinacion=resultado["vinculados_coordinacion"],
        )
        db.session.add(historial)
        db.session.commit()
        return resultado
    except Exception:
        db.session.rollback()
        raise
