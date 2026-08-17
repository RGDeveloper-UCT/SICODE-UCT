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
    return texto


def resolver_expediente(valor_sp):
    no_sp = normalizar_sp(valor_sp)
    if not no_sp:
        return None, None
    expediente = Expediente.query.filter_by(no_sp=no_sp).first()
    return expediente, no_sp


def determinar_estado(expediente, no_sp, campos_clave=None, estado_preferido=None):
    if estado_preferido:
        return estado_preferido
    if no_sp and expediente is None:
        return "Pendiente de vincular"
    if campos_clave and any(valor is None or str(valor).strip() == "" for valor in campos_clave):
        return "Información pendiente"
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
