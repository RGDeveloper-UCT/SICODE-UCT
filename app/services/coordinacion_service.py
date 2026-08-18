import re
from app.models.expediente import Expediente


def normalizar_sp(valor):
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto:
        return None

    texto = re.sub(r"^SP\s*[-:#]?\s*", "", texto, flags=re.IGNORECASE).strip()

    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]

    # La manta diaria usa valores como SP01, SP02, etc. Para que SP01,
    # SP-001, 001 y 1 representen el mismo sujeto, los SP numéricos se
    # guardan/comparan sin ceros a la izquierda.
    if texto.isdigit():
        return str(int(texto))

    return texto.upper()


def resolver_expediente(valor_sp):
    no_sp = normalizar_sp(valor_sp)
    if not no_sp:
        return None, None

    # Los expedientes nuevos se guardan normalizados, por lo que este es
    # el camino habitual y eficiente.
    expediente = Expediente.query.filter_by(no_sp=no_sp).first()
    if expediente:
        return expediente, no_sp

    # Compatibilidad con expedientes anteriores creados como SP-001, SP01,
    # etc. Esto evita crear duplicados lógicos durante la primera carga.
    for candidato in Expediente.query.all():
        if normalizar_sp(candidato.no_sp) == no_sp:
            return candidato, no_sp

    return None, no_sp


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
        # Si el registro histórico estaba explícitamente pendiente de ser
        # remitido, conservar ese estado aunque todos los SP ya estén ligados.
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
    return resultado
