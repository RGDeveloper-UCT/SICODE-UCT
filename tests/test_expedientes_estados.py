from datetime import date

from app.models.expediente import Expediente


def test_estado_sp_clasificado_prioriza_estado_portador():
    activo = Expediente(estado_portador="ACTIVO", activo=False)
    inactivo = Expediente(estado_portador="Inactivo", activo=True)

    assert activo.estado_sp_clasificado == "Activo"
    assert inactivo.estado_sp_clasificado == "Inactivo"


def test_estado_sp_clasificado_detecta_desinstalacion_y_fallback():
    desinstalado = Expediente(estado_portador="", activo=True, fecha_desinstalacion=date(2026, 8, 1))
    sin_estado_activo = Expediente(estado_portador=None, activo=True)
    sin_estado_inactivo = Expediente(estado_portador=None, activo=False)

    assert desinstalado.estado_sp_clasificado == "Inactivo"
    assert sin_estado_activo.estado_sp_clasificado == "Activo"
    assert sin_estado_inactivo.estado_sp_clasificado == "Inactivo"


def test_estado_exoneracion_clasifica_financiamiento_existente():
    exonerado = Expediente(financiamiento="Exonerado")
    no_exonerado = Expediente(financiamiento="No exonerado - pago propio")
    autofinanciado = Expediente(financiamiento="Autofinanciado")
    sin_clasificar = Expediente(financiamiento="Convenio especial")

    assert exonerado.estado_exoneracion == "Exonerado"
    assert exonerado.es_exonerado is True
    assert no_exonerado.estado_exoneracion == "No exonerado"
    assert no_exonerado.es_exonerado is False
    assert autofinanciado.estado_exoneracion == "No exonerado"
    assert sin_clasificar.estado_exoneracion == "Sin clasificar"
    assert sin_clasificar.es_exonerado is None
