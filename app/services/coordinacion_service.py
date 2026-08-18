import re

from app.services.sp_service import normalizar_sp, resolver_expediente


# Se reexportan `normalizar_sp` y `resolver_expediente` por compatibilidad con
# importaciones existentes. La implementación canónica vive en sp_service.


def determinar_estado(expediente, no_sp, campos_clave=None, estado_preferido=None):
    if estado_preferido:
        return estado_preferido
    if no_sp and expediente is None:
        return "Pendiente de vincular"
    if campos_clave and any(valor is None or str(valor).strip() == "" for valor in campos_clave):
        return "Información pendiente"
    return "Completo"


def _faltan(*valores):
    return any(valor is None or str(valor).strip() == "" for valor in valores)


def recalcular_estado_registro(registro):
    """Recalcula el estado de un registro después de vincular su SP."""
    if registro.no_sp_referencia and registro.expediente_id is None:
        return "Pendiente de vincular"

    tipo = registro.tipo

    if tipo == "PAGO":
        detalle = registro.pago
        if not detalle or _faltan(registro.providencia, registro.fecha_recepcion, detalle.boleta, detalle.total):
            return "Información pendiente"

    elif tipo in ("INSTALACION", "DESINSTALACION"):
        if _faltan(registro.rc, registro.providencia, registro.fecha_recepcion):
            return "Información pendiente"

    elif tipo == "ANEXO":
        detalle = registro.anexo_coordinacion
        if not detalle or _faltan(registro.rc, registro.providencia, registro.fecha_recepcion, detalle.tipo_anexo):
            return "Información pendiente"
        if detalle.escaneado and detalle.fecha_escaneado is None:
            return "Información pendiente"

    elif tipo == "MONITOREO":
        detalle = registro.reporte_monitoreo
        if not detalle or _faltan(
            registro.rc,
            registro.providencia,
            registro.fecha_recepcion,
            detalle.numero_reporte,
            detalle.tipo_evento,
        ):
            return "Información pendiente"

    elif tipo == "DOCUMENTO_EMITIDO":
        detalle = registro.documento_emitido
        if not detalle or _faltan(detalle.numero_documento, registro.fecha_recepcion):
            return "Información pendiente"

    elif tipo == "ACTIVIDAD":
        detalle = registro.actividad_coordinacion
        if not detalle or _faltan(detalle.descripcion, registro.fecha_recepcion):
            return "Información pendiente"

    elif tipo == "REMISION":
        detalle = registro.remision_coordinacion
        if not detalle or not detalle.expedientes_remitidos:
            return "Pendiente de remisión"
        if any(item.expediente_id is None for item in detalle.expedientes_remitidos):
            return "Pendiente de vincular"
        if registro.estado == "Pendiente de remisión":
            return "Pendiente de remisión"

    return "Completo"


def separar_sp_remision(valor):
    if valor is None:
        return []
    texto = str(valor).upper().strip()
    if not texto:
        return []
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    texto = texto.replace(" Y ", ",").replace(";", ",")
    texto = re.sub(r"\s+", "", texto)
    partes = [p for p in texto.split(",") if p]
    resultado = []
    for parte in partes:
        if "." in parte and all(x.isdigit() for x in parte.split(".") if x):
            resultado.extend([x for x in parte.split(".") if x])
        else:
            resultado.append(parte)
    return [normalizar_sp(item) or item for item in resultado]
