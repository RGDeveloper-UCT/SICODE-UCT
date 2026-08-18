import re

from app.models.expediente import Expediente


def normalizar_sp(valor):
    """Devuelve la representación administrativa canónica del No. de SP."""
    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto:
        return None

    texto = re.sub(r"^SP\s*[-:#]?\s*", "", texto, flags=re.IGNORECASE).strip()
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]

    if texto.isdigit():
        return str(int(texto))

    return texto.upper()


def buscar_expediente_por_sp(valor_sp, excluir_id=None):
    """Busca por SP lógico, incluyendo formatos históricos como SP-001/001/1."""
    clave = normalizar_sp(valor_sp)
    if not clave:
        return None, None

    consulta = Expediente.query
    if excluir_id is not None:
        consulta = consulta.filter(Expediente.id != excluir_id)

    expediente = consulta.filter(Expediente.no_sp == clave).first()
    if expediente:
        return expediente, clave

    # Compatibilidad temporal con datos históricos aún no canonizados.
    for candidato in consulta.all():
        if normalizar_sp(candidato.no_sp) == clave:
            return candidato, clave

    return None, clave


def resolver_expediente(valor_sp):
    return buscar_expediente_por_sp(valor_sp)
