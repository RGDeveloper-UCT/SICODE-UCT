from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.routes.indice_documental import _rango_folios_recepcion


@pytest.fixture()
def app_indice_folios():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.drop_all()
        db.create_all()

        usuario = Usuario(
            nombre="Administrador Índice",
            usuario="indice-admin",
            correo="indice@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0276",
            no_sp="276",
            nombre_referencia="SP prueba foliación",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_indice(app_indice_folios):
    cliente = app_indice_folios.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "indice-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _registrar(cliente, nombre, tipo, inicio, fin, anexo_coordinacion_id=""):
    return cliente.post(
        "/expedientes/1/indice-documental",
        data={
            "anexo_coordinacion_id": anexo_coordinacion_id,
            "nombre_documento": nombre,
            "tipo_documento": tipo,
            "folio_inicio": inicio,
            "folio_fin": fin,
            "estado_revision": "Verificado",
            "observaciones": "",
        },
        follow_redirects=True,
    )


def test_documentos_del_expediente_principal_siguen_bloqueando_traslapes(app_indice_folios, cliente_indice):
    primera = _registrar(cliente_indice, "Documento principal A", "Documento", 1, 14)
    assert primera.status_code == 200
    assert "foliación general del expediente correctamente" in primera.get_data(as_text=True)

    segunda = _registrar(cliente_indice, "Documento principal B", "Oficio", 10, 20)
    texto = segunda.get_data(as_text=True)

    assert segunda.status_code == 200
    assert "dentro de la foliación general del expediente" in texto

    with app_indice_folios.app_context():
        assert DocumentoExpediente.query.filter_by(expediente_id=1, activo=True).count() == 1


def test_anexo_puede_repetir_folios_del_expediente_principal(app_indice_folios, cliente_indice):
    _registrar(cliente_indice, "Cuerpo principal", "Documento", 1, 14)
    respuesta = _registrar(cliente_indice, "Anexo 1 - PRUEBA", "Anexo", 1, 14)
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Anexo agregado correctamente con foliación independiente" in texto

    with app_indice_folios.app_context():
        documentos = DocumentoExpediente.query.order_by(DocumentoExpediente.id.asc()).all()
        assert len(documentos) == 2
        assert documentos[0].es_anexo is False
        assert documentos[1].es_anexo is True
        assert (documentos[0].folio_inicio, documentos[0].folio_fin) == (1, 14)
        assert (documentos[1].folio_inicio, documentos[1].folio_fin) == (1, 14)


def test_anexos_distintos_pueden_tener_el_mismo_rango(app_indice_folios, cliente_indice):
    _registrar(cliente_indice, "Anexo 8 - REEMPLAZO", "Anexo", 1, 14)
    respuesta = _registrar(cliente_indice, "Anexo 7 - MOVILIZACIÓN", "Anexo", 1, 14)

    assert respuesta.status_code == 200
    assert "Anexo agregado correctamente con foliación independiente" in respuesta.get_data(as_text=True)

    with app_indice_folios.app_context():
        anexos = DocumentoExpediente.query.filter_by(expediente_id=1, es_anexo=True, activo=True).all()
        assert len(anexos) == 2
        assert {(anexo.folio_inicio, anexo.folio_fin) for anexo in anexos} == {(1, 14)}


def test_incorporacion_desde_coordinacion_usa_foliacion_propia_y_vincula_anexo(app_indice_folios, cliente_indice):
    with app_indice_folios.app_context():
        registro = RegistroCoordinacion(
            tipo="ANEXO",
            expediente_id=1,
            no_sp_referencia="276",
            rc="20254238",
            fecha_recepcion=date(2026, 8, 3),
            folios_recepcion="3",
            usuario_id=1,
            estado="Completo",
        )
        db.session.add(registro)
        db.session.flush()
        anexo = AnexoCoordinacion(
            registro_id=registro.id,
            tipo_anexo="MOVILIZACION",
            numero_anexo="7",
            folios="3",
        )
        db.session.add(anexo)
        db.session.commit()
        anexo_id = anexo.id

    respuesta_get = cliente_indice.get(f"/expedientes/1/indice-documental?anexo_id={anexo_id}")
    texto_get = respuesta_get.get_data(as_text=True)
    assert respuesta_get.status_code == 200
    assert "los folios que registre a continuación pertenecen únicamente a este anexo" in texto_get

    respuesta = _registrar(
        cliente_indice,
        "Anexo 7 - MOVILIZACION",
        "Anexo",
        1,
        3,
        anexo_coordinacion_id=str(anexo_id),
    )
    assert respuesta.status_code == 200
    assert "Anexo agregado correctamente con foliación independiente" in respuesta.get_data(as_text=True)

    with app_indice_folios.app_context():
        anexo = db.session.get(AnexoCoordinacion, anexo_id)
        documento = db.session.get(DocumentoExpediente, anexo.documento_expediente_id)
        assert documento is not None
        assert documento.es_anexo is True
        assert (documento.folio_inicio, documento.folio_fin) == (1, 3)


def test_sugerencia_de_folios_interpreta_total_y_rango():
    assert _rango_folios_recepcion("3") == (1, 3)
    assert _rango_folios_recepcion("325-330") == (325, 330)
    assert _rango_folios_recepcion("12 – 18") == (12, 18)
    assert _rango_folios_recepcion("sin dato") == (None, None)
