from datetime import date
from types import SimpleNamespace

from app.models.expediente import Expediente
from app.services.pagos_service import calcular_solvencia


def test_exonerado_es_solvente_sin_pagos():
    expediente = Expediente(financiamiento="Exonerado")

    estado = calcular_solvencia(expediente, [], hoy=date(2026, 9, 1))

    assert estado["solvente"] is True
    assert estado["estado"] == "Solvente"
    assert "Exonerado" in estado["motivo"]


def test_pago_vigente_marca_solvente():
    expediente = Expediente(financiamiento="No exonerado - pago propio")
    pago = SimpleNamespace(
        periodo_desde=date(2026, 8, 15),
        periodo_hasta=date(2026, 9, 15),
    )

    estado = calcular_solvencia(expediente, [pago], hoy=date(2026, 9, 1))

    assert estado["solvente"] is True
    assert estado["ultima_cobertura"] == date(2026, 9, 15)


def test_pago_vencido_marca_no_solvente_y_conserva_ultima_cobertura():
    expediente = Expediente(financiamiento="No exonerado")
    pago = SimpleNamespace(
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 8, 31),
    )

    estado = calcular_solvencia(expediente, [pago], hoy=date(2026, 9, 1))

    assert estado["solvente"] is False
    assert estado["estado"] == "No solvente"
    assert estado["ultima_cobertura"] == date(2026, 8, 31)


def test_pago_futuro_no_adelanta_solvencia():
    expediente = Expediente(financiamiento="No exonerado")
    pago = SimpleNamespace(
        periodo_desde=date(2026, 9, 10),
        periodo_hasta=date(2026, 10, 10),
    )

    estado = calcular_solvencia(expediente, [pago], hoy=date(2026, 9, 1))

    assert estado["solvente"] is False
