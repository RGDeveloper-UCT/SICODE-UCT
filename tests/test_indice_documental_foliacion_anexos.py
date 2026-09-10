from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
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


def _registrar(
    cliente,
    nombre,
    tipo,
    inicio,
    fin,
    anexo_coordinacion_id="",
    estado_revision="Verificado",
):
    return cliente.post(
        "/expedientes/1/indice-documental",
        data={
            "anexo_coordinacion_id": anexo_coordinacion_id,
            "nombre_documento": nombre,
            "tipo_documento": tipo,
            "folio_inicio": inicio,
            "folio_fin": fin,
            "estado_revision": estado_revision,
            "observaciones": "",
        },
        follow_redirects=True,
    )


def _crear_anexo_coordinacion(app, numero, tipo="REPORTE DE MONITOREO", folios="5", rc=None):
    with app.app_context():
        registro = RegistroCoordinacion(
            tipo="ANEXO",
            expediente_id=1,
            no_sp_referencia="276",
            rc=rc or f"RC-{numero}",
            fecha_recepcion=date(2026, 9, 2),
            folios_recepcion=folios,
            usuario_id=1,
            estado="Completo",
        )
        db.session.add(registro)
        db.session.flush()
        anexo = AnexoCoordinacion(
            registro_id=registro.id,
            tipo_anexo=tipo,
            numero_anexo=str(numero),
            folios=folios,
        )
        db.session.add(anexo)
        db.session.commit()
        return anexo.id


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


def test_numero_anexo_se_puede_corregir_desde_indice_y_sincroniza_titulo(app_indice_folios, cliente_indice):
    anexo_id = _crear_anexo_coordinacion(app_indice_folios, 2)
    _registrar(
        cliente_indice,
        "Anexo 2 - REPORTE DE MONITOREO",
        "Anexo",
        1,
        5,
        anexo_coordinacion_id=str(anexo_id),
    )

    with app_indice_folios.app_context():
        anexo = db.session.get(AnexoCoordinacion, anexo_id)
        documento_id = anexo.documento_expediente_id

    panel = cliente_indice.get("/expedientes/1/indice-documental")
    texto_panel = panel.get_data(as_text=True)
    assert f"/expedientes/1/indice-documental/{documento_id}/editar-numero-anexo" in texto_panel
    assert 'name="numero_anexo"' in texto_panel

    respuesta = cliente_indice.post(
        f"/expedientes/1/indice-documental/{documento_id}/editar-numero-anexo",
        data={"numero_anexo": "3"},
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Número actualizado correctamente: Anexo 3." in texto

    with app_indice_folios.app_context():
        anexo = db.session.get(AnexoCoordinacion, anexo_id)
        documento = db.session.get(DocumentoExpediente, documento_id)
        assert anexo.numero_anexo == "3"
        assert documento.nombre_documento == "Anexo 3 - REPORTE DE MONITOREO"

        evento = Bitacora.query.filter_by(
            accion="EDITAR_NUMERO_ANEXO_INDICE",
            expediente_id=1,
        ).one()
        assert evento.datos_anteriores["numero_anexo"] == "2"
        assert evento.datos_posteriores["numero_anexo"] == "3"


def test_numero_anexo_no_permite_duplicado_en_mismo_sp(app_indice_folios, cliente_indice):
    anexo_2_id = _crear_anexo_coordinacion(app_indice_folios, 2, rc="RC-2")
    anexo_4_id = _crear_anexo_coordinacion(app_indice_folios, 4, rc="RC-4")
    _registrar(cliente_indice, "Anexo 2 - REPORTE A", "Anexo", 1, 2, anexo_coordinacion_id=str(anexo_2_id))
    _registrar(cliente_indice, "Anexo 4 - REPORTE B", "Anexo", 1, 2, anexo_coordinacion_id=str(anexo_4_id))

    with app_indice_folios.app_context():
        documento_id = db.session.get(AnexoCoordinacion, anexo_2_id).documento_expediente_id

    respuesta = cliente_indice.post(
        f"/expedientes/1/indice-documental/{documento_id}/editar-numero-anexo",
        data={"numero_anexo": "4"},
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "ese número ya está registrado para este SP" in texto

    with app_indice_folios.app_context():
        assert db.session.get(AnexoCoordinacion, anexo_2_id).numero_anexo == "2"
        assert Bitacora.query.filter_by(accion="EDITAR_NUMERO_ANEXO_INDICE").count() == 0


def test_verificacion_individual_marca_documento_y_deja_trazabilidad(app_indice_folios, cliente_indice):
    _registrar(
        cliente_indice,
        "Solicitud de informe",
        "Documento",
        1,
        2,
        estado_revision="Pendiente de revisión",
    )

    respuesta = cliente_indice.post(
        "/expedientes/1/indice-documental/1/verificar",
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Documento verificado: Solicitud de informe." in texto

    with app_indice_folios.app_context():
        documento = db.session.get(DocumentoExpediente, 1)
        assert documento.estado_revision == "Verificado"

        evento = Bitacora.query.filter_by(
            accion="VERIFICAR_DOCUMENTO_INDICE",
            expediente_id=1,
        ).one()
        assert evento.entidad == "DocumentoExpediente"
        assert evento.datos_anteriores["estado_revision"] == "Pendiente de revisión"
        assert evento.datos_posteriores["estado_revision"] == "Verificado"


def test_verificar_todos_solo_confirma_pendientes_y_respeta_incidencias(app_indice_folios, cliente_indice):
    _registrar(
        cliente_indice,
        "Documento pendiente",
        "Documento",
        1,
        2,
        estado_revision="Pendiente de revisión",
    )
    _registrar(
        cliente_indice,
        "Documento con observaciones",
        "Oficio",
        3,
        4,
        estado_revision="Con observaciones",
    )
    _registrar(
        cliente_indice,
        "Anexo pendiente de revisión",
        "Anexo",
        1,
        2,
        estado_revision="Pendiente de revisión",
    )

    respuesta = cliente_indice.post(
        "/expedientes/1/indice-documental/verificar-todos",
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Se verificaron 2 documentos pendientes" in texto
    assert "observaciones o incidencias no fueron modificados" in texto

    with app_indice_folios.app_context():
        documentos = {
            documento.nombre_documento: documento.estado_revision
            for documento in DocumentoExpediente.query.order_by(DocumentoExpediente.id.asc()).all()
        }
        assert documentos["Documento pendiente"] == "Verificado"
        assert documentos["Documento con observaciones"] == "Con observaciones"
        assert documentos["Anexo pendiente de revisión"] == "Verificado"

        evento = Bitacora.query.filter_by(
            accion="VERIFICAR_TODOS_DOCUMENTOS_INDICE",
            expediente_id=1,
        ).one()
        assert evento.datos_posteriores["cantidad"] == 2


def test_panel_muestra_verificacion_masiva_e_individual(app_indice_folios, cliente_indice):
    _registrar(
        cliente_indice,
        "Documento pendiente UI",
        "Documento",
        1,
        1,
        estado_revision="Pendiente de revisión",
    )

    respuesta = cliente_indice.get("/expedientes/1/indice-documental")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Verificar todos" in texto
    assert "/expedientes/1/indice-documental/verificar-todos" in texto
    assert "/expedientes/1/indice-documental/1/verificar" in texto


def test_sugerencia_de_folios_interpreta_total_y_rango():
    assert _rango_folios_recepcion("3") == (1, 3)
    assert _rango_folios_recepcion("325-330") == (325, 330)
    assert _rango_folios_recepcion("12 – 18") == (12, 18)
    assert _rango_folios_recepcion("sin dato") == (None, None)
