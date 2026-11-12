"""Pruebas del contrato ImportM.IA v3 y control de acceso."""
from io import BytesIO

import pytest
from openpyxl import Workbook

from app import create_app
from app.services.importmia_service import HOJAS, ImportMIAInvalido, validar_libro


def libro_v3(*, hoja_faltante=None, sin_indice=False):
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, requeridas in HOJAS.items():
        if nombre == hoja_faltante:
            continue
        hoja = libro.create_sheet(nombre)
        hoja.append(sorted(requeridas))
        if nombre == "LOTE":
            hoja.append(["V3" if campo == "version_contrato" else "IMP-TEST"
                         for campo in sorted(requeridas)])
        elif nombre == "Indice" and not sin_indice:
            hoja.append(["95" if campo == "sp" else "PRINCIPAL" if campo == "seccion"
                         else 1 if campo == "orden" else "Oficio" if campo == "nombre_documento"
                         else None for campo in sorted(requeridas)])
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_contrato_v3_valido():
    resumen = validar_libro(libro_v3())
    assert resumen["LOTE"] == 1
    assert resumen["Indice"] == 1


def test_rechaza_hoja_faltante():
    with pytest.raises(ImportMIAInvalido, match="ANEXOS"):
        validar_libro(libro_v3(hoja_faltante="ANEXOS"))


def test_rechaza_excel_corrupto():
    with pytest.raises(ImportMIAInvalido):
        validar_libro(b"esto no es xlsx")


def test_rutas_importmia_registradas():
    app = create_app()
    reglas = {r.endpoint: r.rule for r in app.url_map.iter_rules()}
    assert reglas["importmia.inicio"] == "/importmia/"
    assert reglas["importmia.confirmar_indice"] == "/importmia/confirmar-indice"


def test_formulario_no_requiere_bd_para_importar_pdf():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    cliente = app.test_client()
    # Visitante no puede visualizar ni confirmar un lote.
    resp = cliente.post("/importmia/confirmar-indice", data={})
    assert resp.status_code in (302, 401, 403)
