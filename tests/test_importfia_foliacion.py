"""Contrato IMPORTF.IA: folio individual por ámbito, sin escrituras durante lectura."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook
from werkzeug.datastructures import FileStorage

from app.services.importfia_service import (
    ANEXOS_OBLIGATORIAS, FOLIOS_OBLIGATORIAS, ImportFIAInvalido,
    leer_importfia,
)


def excel(folios, anexos=None):
    libro = Workbook()
    libro.active.title = "CONTROL"
    hoja = libro.create_sheet("FOLIOS")
    hf = sorted(FOLIOS_OBLIGATORIAS)
    hoja.append(hf)
    for r in folios:
        hoja.append([r.get(k) for k in hf])
    an = libro.create_sheet("ANEXOS")
    ha = sorted(ANEXOS_OBLIGATORIAS)
    an.append(ha)
    for r in anexos or []:
        an.append([r.get(k) for k in ha])
    libro.create_sheet("INCIDENCIAS")
    libro.create_sheet("CATALOGO")
    buffer = BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    return FileStorage(stream=buffer, filename="IMPORTFIA_SP_8.xlsx")


def expediente():
    return SimpleNamespace(no_sp="8", codigo_interno="SICODE-UCT-0008")


def folio(seccion="PRINCIPAL", numero=None, n=1, **extras):
    fila = {
        "sp": 8, "codigo_expediente": "SICODE-UCT-0008",
        "seccion": seccion, "numero_anexo": numero, "folio": n,
        "orden": 1, "nombre_documento": "Oficio",
        "tipo_documento": "Oficio", "identificador_documento": "DOC-01",
        "pagina_pdf": n, "referencia_file_server": "SP8/Oficio.pdf",
        "evidencia_folio": "Sello físico legible", "confianza_lectura": "ALTA",
    }
    fila.update(extras)
    return fila


def anexo(numero):
    return {"sp": 8, "numero_anexo": numero, "tipo_codigo": "REPORTE_MONITOREO",
            "titulo": "Reporte de monitoreo", "es_vencido": "DESCONOCIDO",
            "referencia_file_server": f"SP8/Anexo {numero}.pdf"}


def test_principal_y_dos_anexos_pueden_compartir_folio_uno():
    filas, anexos, ambitos = leer_importfia(excel([
        folio(n=1), folio("ANEXO", 1, 1, tipo_documento="Anexo"),
        folio("ANEXO", 2, 1, tipo_documento="Anexo"),
    ], [anexo(1), anexo(2)]), expediente())
    assert len(filas) == 3
    assert set(ambitos) == {0, 1, 2}
    assert set(anexos) == {1, 2}


def test_mismo_folio_repetido_en_principal_se_rechaza():
    with pytest.raises(ImportFIAInvalido, match="repetido"):
        leer_importfia(excel([folio(n=1), folio(n=1)]), expediente())


def test_sp_no_coincidente_rechazado():
    with pytest.raises(ImportFIAInvalido, match="SP distinto"):
        leer_importfia(excel([folio(sp=9)]), expediente())


def test_ocr_baja_confianza_rechazado():
    with pytest.raises(ImportFIAInvalido, match="BAJA"):
        leer_importfia(excel([folio(confianza_lectura="BAJA")]), expediente())


def test_anexo_debe_existir_en_hoja_anexos():
    with pytest.raises(ImportFIAInvalido, match="no está descrito"):
        leer_importfia(excel([folio("ANEXO", 1, 1)]), expediente())


def test_catalogo_no_permite_codigos_inventados():
    with pytest.raises(ImportFIAInvalido, match="catálogo"):
        leer_importfia(excel([folio("ANEXO", 1, 1)], [
            {**anexo(1), "tipo_codigo": "CODIGO_FICTICIO"}
        ]), expediente())


def test_no_toma_verificacion_del_excel():
    fila, _, _ = leer_importfia(excel([
        folio(estado_revision="Verificado")
    ]), expediente())
    assert "estado_revision" not in fila[0]
