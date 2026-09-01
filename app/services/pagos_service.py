from datetime import datetime
from zoneinfo import ZoneInfo

from flask import g, has_request_context
from sqlalchemy import func, or_

from app import db


ZONA_GUATEMALA = ZoneInfo("America/Guatemala")


def ahora_guatemala():
    """Hora institucional de Guatemala usada para registrar y evaluar pagos."""
    return datetime.now(ZONA_GUATEMALA)


def _resultado(estado, motivo, ultima_cobertura=None):
    return {
        "estado": estado,
        "solvente": estado == "Solvente",
        "motivo": motivo,
        "ultima_cobertura": ultima_cobertura,
    }


def calcular_solvencia(expediente, pagos, hoy=None):
    """Calcula la solvencia de un SP con pagos ya cargados en memoria.

    Regla operativa:
    - un SP exonerado se considera solvente sin exigir pago;
    - un SP no exonerado/indeterminado es solvente únicamente si un período
      registrado cubre la fecha actual;
    - en cualquier otro caso se marca como no solvente.
    """
    hoy = hoy or ahora_guatemala().date()

    if expediente.es_exonerado is True:
        return _resultado("Solvente", "Exonerado; no requiere pago vigente.")

    ultima_cobertura = None
    tiene_pago_vigente = False

    for pago in pagos or []:
        desde = getattr(pago, "periodo_desde", None)
        hasta = getattr(pago, "periodo_hasta", None)
        if hasta and (ultima_cobertura is None or hasta > ultima_cobertura):
            ultima_cobertura = hasta
        if hasta and hasta >= hoy and (desde is None or desde <= hoy):
            tiene_pago_vigente = True

    if tiene_pago_vigente:
        return _resultado(
            "Solvente",
            "El período pagado cubre la fecha actual.",
            ultima_cobertura,
        )

    if ultima_cobertura:
        return _resultado(
            "No solvente",
            f"Última cobertura registrada: {ultima_cobertura.strftime('%d/%m/%Y')}.",
            ultima_cobertura,
        )

    return _resultado("No solvente", "No hay un período de pago vigente registrado.")


def _mapa_ultima_cobertura(hoy):
    from app.models.coordinacion import PagoCoordinacion, RegistroCoordinacion

    filas = (
        db.session.query(
            RegistroCoordinacion.expediente_id,
            func.max(PagoCoordinacion.periodo_hasta),
        )
        .join(PagoCoordinacion, PagoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.tipo == "PAGO",
            RegistroCoordinacion.expediente_id.isnot(None),
            PagoCoordinacion.periodo_hasta.isnot(None),
            or_(
                PagoCoordinacion.periodo_desde.is_(None),
                PagoCoordinacion.periodo_desde <= hoy,
            ),
        )
        .group_by(RegistroCoordinacion.expediente_id)
        .all()
    )
    return {expediente_id: cobertura for expediente_id, cobertura in filas}


def _mapa_cobertura_cache(hoy):
    """Evita una consulta por fila en el listado panorámico de expedientes."""
    if not has_request_context():
        return _mapa_ultima_cobertura(hoy)

    cache = getattr(g, "_sicode_pagos_cobertura", None)
    if not cache or cache.get("hoy") != hoy:
        cache = {"hoy": hoy, "mapa": _mapa_ultima_cobertura(hoy)}
        g._sicode_pagos_cobertura = cache
    return cache["mapa"]


def obtener_solvencia_expediente(expediente, hoy=None):
    hoy = hoy or ahora_guatemala().date()

    if expediente.es_exonerado is True:
        return _resultado("Solvente", "Exonerado; no requiere pago vigente.")

    if expediente.id is None:
        return _resultado("No solvente", "El SP todavía no tiene historial de pagos persistido.")

    ultima_cobertura = _mapa_cobertura_cache(hoy).get(expediente.id)
    if ultima_cobertura and ultima_cobertura >= hoy:
        return _resultado(
            "Solvente",
            "El período pagado cubre la fecha actual.",
            ultima_cobertura,
        )
    if ultima_cobertura:
        return _resultado(
            "No solvente",
            f"Última cobertura registrada: {ultima_cobertura.strftime('%d/%m/%Y')}.",
            ultima_cobertura,
        )
    return _resultado("No solvente", "No hay un período de pago vigente registrado.")


def resumen_solvencia_actual(hoy=None):
    from app.models.expediente import Expediente

    hoy = hoy or ahora_guatemala().date()
    expedientes = Expediente.query.filter(Expediente.activo.is_(True)).all()
    cobertura = _mapa_cobertura_cache(hoy)

    solventes = 0
    no_solventes = 0
    for expediente in expedientes:
        if expediente.es_exonerado is True:
            solventes += 1
        elif cobertura.get(expediente.id) and cobertura[expediente.id] >= hoy:
            solventes += 1
        else:
            no_solventes += 1

    return {
        "solventes": solventes,
        "no_solventes": no_solventes,
        "total": solventes + no_solventes,
    }
