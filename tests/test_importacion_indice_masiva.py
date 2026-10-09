"""Pruebas de formato de importación de índice documental."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import FileStorage
from openpyxl import Workbook

from app.routes.indice_documental_importacion import _leer, ImportacionInvalida


HEADERS = ["sp", "codigo_expediente", "seccion", "numero_anexo", "titulo_anexo",
           "orden", "nombre_documento", "folio_inicial", "folio_final", "estado_revision", "observaciones"]


def _archivo(filas):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Indice"
    hoja.append(HEADERS)
    for fila in filas:
        hoja.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    return FileStorage(stream=buffer, filename="indice.xlsx")


def _expediente():
    return SimpleNamespace(no_sp="95", codigo_interno="SICODE-UCT-0095")


def test_misma_foliacion_en_anexos_distintos_es_valida():
    filas = [
        [95, "SICODE-UCT-0095", "PRINCIPAL", None, None, 1, "Inicio", 1, 2, "Pendiente de revisión", None],
        [95, "SICODE-UCT-0095", "ANEXO", 1, "Reemplazo", 1, "Acta", 1, 2, "Pendiente de revisión", None],
        [95, "SICODE-UCT-0095", "ANEXO", 2, "Destrucción", 1, "Informe", 1, 2, "Pendiente de revisión", None],
    ]
    registros, alertas = _leer(_archivo(filas), _expediente())
    assert len(registros) == 3
    assert not alertas


def test_traslape_mismo_anexo_es_rechazado():
    filas = [
        [95, "SICODE-UCT-0095", "ANEXO", 1, "Reemplazo", 1, "Acta", 1, 3, "Pendiente de revisión", None],
        [95, "SICODE-UCT-0095", "ANEXO", 1, "Reemplazo", 2, "Oficio", 3, 4, "Pendiente de revisión", None],
    ]
    with pytest.raises(ImportacionInvalida, match="traslape"):
        _leer(_archivo(filas), _expediente())


def test_sp_incorrecto_es_rechazado():
    filas = [[96, "SICODE-UCT-0095", "PRINCIPAL", None, None, 1, "Inicio", 1, 1, "Pendiente de revisión", None]]
    with pytest.raises(ImportacionInvalida, match="distinto"):
        _leer(_archivo(filas), _expediente())
