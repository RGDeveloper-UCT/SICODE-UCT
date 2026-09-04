from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.checks import folios as check_folios
from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.services.anexos_integridad_service import AnexoDuplicadoError
from app.services.estado_documental_service import calcular_estado_documental


@pytest.fixture()
def app_auditoria():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Auditor Admin",
            usuario="auditor-admin",
            correo="auditoria@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-AUD-001",
            no_sp="901",
            nombre_referencia="Expediente auditoría",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            folios_rectificados=100,
            anexos_rectificados=2,
            activo=True,
        )
        db.session.add_all([usuario, expediente])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_auditoria(app_auditoria):
    cliente = app_auditoria.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "auditor-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _documento(nombre, inicio, fin, *, es_anexo=False, estado="Verificado"):
    return DocumentoExpediente(
        expediente_id=1,
        nombre_documento=nombre,
        tipo_documento="Anexo" if es_anexo else "Documento",
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision=estado,
        es_anexo=es_anexo,
        activo=True,
    )


def test_anexos_con_mismos_folios_no_generan_traslape(app_auditoria):
    with app_auditoria.app_context():
        db.session.add_all([
            _documento("Cuerpo principal", 1, 100),
            _documento("Anexo 1", 1, 10, es_anexo=True),
            _documento("Anexo 2", 1, 10, es_anexo=True),
        ])
        db.session.commit()

        hallazgos = check_folios.ejecutar()
        assert not [item for item in hallazgos if item.codigo == "FOL-TRASLAPE-001"]

        resumen = calcular_estado_documental(db.session.get(Expediente, 1))
        assert resumen["traslapes"] == []
        assert resumen["folios_documentados"] == 100
        assert resumen["ultimo_folio_indice"] == 100
        assert resumen["anexos_indexados"] == 2


def test_detector_no_pierde_traslapes_anidados(app_auditoria):
    with app_auditoria.app_context():
        db.session.add_all([
            _documento("Rango amplio", 1, 100),
            _documento("Rango interno A", 2, 3),
            _documento("Rango interno B", 4, 5),
        ])
        db.session.commit()

        traslapes = [item for item in check_folios.ejecutar() if item.codigo == "FOL-TRASLAPE-001"]
        assert len(traslapes) == 2


def test_incidencia_no_se_sobrescribe_con_verificacion_rapida(app_auditoria, cliente_auditoria):
    with app_auditoria.app_context():
        documento = _documento("Documento observado", 1, 2, estado="Con observaciones")
        db.session.add(documento)
        db.session.flush()
        db.session.add(Alerta(
            expediente_id=1,
            documento_id=documento.id,
            tipo_alerta="REVISION_INDICE_DOCUMENTAL",
            titulo="Revisión requerida",
            gravedad="Media",
            estado="Abierta",
            origen="Automática",
        ))
        db.session.commit()
        documento_id = documento.id

    respuesta = cliente_auditoria.post(
        f"/expedientes/1/indice-documental/{documento_id}/verificar",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Debe usar «Resolver incidencia»" in respuesta.get_data(as_text=True)

    with app_auditoria.app_context():
        assert db.session.get(DocumentoExpediente, documento_id).estado_revision == "Con observaciones"
        assert Alerta.query.filter_by(documento_id=documento_id, estado="Abierta").count() == 1


def test_resolver_incidencia_actualiza_documento_alerta_y_bitacora(app_auditoria, cliente_auditoria):
    with app_auditoria.app_context():
        documento = _documento("Documento mal foliado", 10, 12, estado="Mal foliado")
        db.session.add(documento)
        db.session.flush()
        db.session.add(Alerta(
            expediente_id=1,
            documento_id=documento.id,
            tipo_alerta="REVISION_INDICE_DOCUMENTAL",
            titulo="Corregir foliación",
            gravedad="Alta",
            estado="Abierta",
            origen="Automática",
        ))
        db.session.commit()
        documento_id = documento.id

    respuesta = cliente_auditoria.post(
        f"/expedientes/1/indice-documental/{documento_id}/resolver-incidencia",
        data={"motivo_resolucion": "Se verificó físicamente y se corrigió la foliación."},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_auditoria.app_context():
        documento = db.session.get(DocumentoExpediente, documento_id)
        alerta = Alerta.query.filter_by(documento_id=documento_id).one()
        evento = Bitacora.query.filter_by(accion="RESOLVER_INCIDENCIA_INDICE", entidad_id=str(documento_id)).one()
        assert documento.estado_revision == "Verificado"
        assert alerta.estado == "Corregida"
        assert "verificó físicamente" in evento.motivo


def test_anular_anexo_libera_vinculo_para_reincorporacion(app_auditoria, cliente_auditoria):
    with app_auditoria.app_context():
        registro = RegistroCoordinacion(
            tipo="ANEXO",
            expediente_id=1,
            no_sp_referencia="901",
            usuario_id=1,
            estado="Completo",
        )
        db.session.add(registro)
        db.session.flush()
        documento = _documento("Anexo 2", 1, 4, es_anexo=True)
        db.session.add(documento)
        db.session.flush()
        anexo = AnexoCoordinacion(
            registro_id=registro.id,
            documento_expediente_id=documento.id,
            tipo_anexo="OTRO",
            titulo="Anexo 2",
            numero_anexo="2",
        )
        db.session.add(anexo)
        db.session.commit()
        documento_id = documento.id
        anexo_id = anexo.id

    respuesta = cliente_auditoria.post(
        f"/expedientes/1/indice-documental/{documento_id}/anular",
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_auditoria.app_context():
        assert db.session.get(DocumentoExpediente, documento_id).activo is False
        assert db.session.get(AnexoCoordinacion, anexo_id).documento_expediente_id is None


def test_evento_integridad_rechaza_anexo_duplicado(app_auditoria):
    with app_auditoria.app_context():
        registro_1 = RegistroCoordinacion(
            tipo="ANEXO", expediente_id=1, no_sp_referencia="901", usuario_id=1, estado="Completo"
        )
        db.session.add(registro_1)
        db.session.flush()
        db.session.add(AnexoCoordinacion(registro_id=registro_1.id, numero_anexo="1", titulo="Primero"))
        db.session.commit()

        registro_2 = RegistroCoordinacion(
            tipo="ANEXO", expediente_id=1, no_sp_referencia="901", usuario_id=1, estado="Completo"
        )
        db.session.add(registro_2)
        db.session.flush()
        db.session.add(AnexoCoordinacion(registro_id=registro_2.id, numero_anexo="1", titulo="Duplicado"))
        with pytest.raises(AnexoDuplicadoError):
            db.session.commit()
        db.session.rollback()
        assert AnexoCoordinacion.query.filter_by(numero_anexo="1").count() == 1


def test_cabeceras_de_seguridad_en_respuesta_autenticada(cliente_auditoria):
    respuesta = cliente_auditoria.get("/dashboard")
    assert respuesta.status_code == 200
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert respuesta.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in respuesta.headers["Cache-Control"]


def test_logout_no_cambia_sesion_por_get_y_post_si_cierra(cliente_auditoria):
    get_logout = cliente_auditoria.get("/logout")
    assert get_logout.status_code == 405

    respuesta = cliente_auditoria.post("/logout", follow_redirects=False)
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


def test_login_limita_sexto_intento_fallido(app_auditoria):
    cliente = app_auditoria.test_client()
    for _ in range(5):
        respuesta = cliente.post(
            "/login",
            data={"usuario": "auditor-admin", "password": "incorrecta"},
        )
        assert respuesta.status_code == 200

    bloqueado = cliente.post(
        "/login",
        data={"usuario": "auditor-admin", "password": "incorrecta"},
    )
    assert bloqueado.status_code == 429

    with app_auditoria.app_context():
        assert Bitacora.query.filter_by(accion="LOGIN_FALLIDO", entidad_id="auditor-admin").count() == 5
        assert Bitacora.query.filter_by(accion="LOGIN_BLOQUEADO_RATE_LIMIT", entidad_id="auditor-admin").count() == 1
