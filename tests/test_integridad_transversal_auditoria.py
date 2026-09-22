import os

import pytest

from app import create_app, db
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.routes import analisis_documental, lote_documental, sicode_ia
from app.services.integridad_transversal_service import (
    _asegurar_fchmod_compatible,
    _crear_indice_anexo_analisis,
    _crear_indice_lote,
    _crear_indice_sicode_ia,
)


@pytest.fixture()
def app_integridad():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        expediente = Expediente(
            codigo_interno="SICODE-UCT-AUD-001",
            no_sp="901",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add(expediente)
        db.session.commit()
        db.session.add(DocumentoExpediente(
            expediente_id=expediente.id,
            nombre_documento="Cuerpo principal",
            tipo_documento="Documento",
            folio_inicio=1,
            folio_fin=14,
            total_folios=14,
            estado_revision="Verificado",
            es_anexo=False,
            activo=True,
        ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_instalador_usa_las_mismas_reglas_en_los_tres_flujos():
    assert analisis_documental._crear_indice_anexo is _crear_indice_anexo_analisis
    assert lote_documental._crear_indice is _crear_indice_lote
    assert sicode_ia._crear_indice is _crear_indice_sicode_ia


def test_analisis_individual_permite_anexo_con_folios_del_cuerpo_principal(app_integridad):
    with app_integridad.app_context(), app_integridad.test_request_context(
        "/coordinacion/analisis-documental/", method="POST", data={"crear_indice": "1"}
    ):
        expediente = db.session.get(Expediente, 1)
        documento, advertencia = analisis_documental._crear_indice_anexo(
            expediente,
            {"numero_anexo": "7", "titulo_anexo": "Movilización"},
            {"folio_inicio": 1, "folio_fin": 14},
        )
        assert advertencia is None
        assert documento is not None
        assert documento.es_anexo is True
        assert (documento.folio_inicio, documento.folio_fin) == (1, 14)


def test_lote_permite_anexo_repetido_y_bloquea_solape_principal(app_integridad):
    with app_integridad.app_context():
        expediente = db.session.get(Expediente, 1)
        anexo, advertencia = lote_documental._crear_indice(
            expediente,
            "ANEXO",
            {"numero_anexo": "8", "titulo_anexo": "Reemplazo"},
            1,
            14,
        )
        assert advertencia is None
        assert anexo is not None and anexo.es_anexo is True

        principal, advertencia_principal = lote_documental._crear_indice(
            expediente,
            "OFICIO",
            {"nombre_documento": "Oficio duplicado"},
            10,
            20,
        )
        assert principal is None
        assert "se cruza con Cuerpo principal" in advertencia_principal


def test_sicode_ia_permite_anexo_repetido_y_bloquea_solape_principal(app_integridad):
    with app_integridad.app_context():
        expediente = db.session.get(Expediente, 1)
        anexo = sicode_ia._crear_indice(
            expediente,
            "ANEXO",
            {"numero_anexo": "9", "titulo_anexo": "Prórroga"},
            1,
            14,
        )
        assert anexo is not None and anexo.es_anexo is True

        principal = sicode_ia._crear_indice(
            expediente,
            "PROVIDENCIA",
            {"nombre_documento": "Providencia duplicada"},
            5,
            8,
        )
        assert principal is None


def test_compatibilidad_windows_provee_fchmod_si_no_existe(monkeypatch):
    original = getattr(os, "fchmod", None)
    if original is not None:
        monkeypatch.delattr(os, "fchmod")
    _asegurar_fchmod_compatible()
    assert callable(getattr(os, "fchmod", None))
