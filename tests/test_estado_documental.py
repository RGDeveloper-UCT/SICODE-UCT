from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.models.verificacion import VerificacionExpediente
from app.services.estado_documental_service import calcular_estado_documental


@pytest.fixture()
def app_estado_documental():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin documental",
            usuario="admin-documental",
            correo="documental@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            rol="administrador",
            activo=True,
        )
        db.session.add(usuario)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _expediente(**kwargs):
    datos = dict(
        codigo_interno="SICODE-DOC-1",
        no_sp="901",
        nombre_referencia="Prueba documental",
        estado_administrativo="Activo",
        estado_fisico_documental="Verificado",
        expediente_fisico_registrado=True,
        activo=True,
    )
    datos.update(kwargs)
    expediente = Expediente(**datos)
    db.session.add(expediente)
    db.session.commit()
    return expediente


def _documento(expediente, inicio=1, fin=4, estado="Pendiente de revisión"):
    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=f"Documento {inicio}-{fin}",
        tipo_documento="DOCUMENTO",
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision=estado,
        es_anexo=False,
        activo=True,
    )
    db.session.add(documento)
    db.session.commit()
    return documento


def _verificar(expediente, usuario, resultado="Verificado", tipo="DOCUMENTAL", cuando=None):
    verificacion = VerificacionExpediente(
        expediente_id=expediente.id,
        usuario_id=usuario.id,
        tipo=tipo,
        resultado=resultado,
        folios_verificados=None,
        observaciones=None,
        origen="MANUAL",
        creado_en=cuando or datetime.utcnow(),
    )
    db.session.add(verificacion)
    db.session.commit()
    return verificacion


def test_sin_expediente_fisico_domina_el_arbol(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente(expediente_fisico_registrado=False)
        assert expediente.estado_fisico_documental == "Sin expediente físico"


def test_expediente_fisico_sin_indice_queda_pendiente_de_indexacion(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente()
        assert expediente.estado_fisico_documental == "Pendiente de indexación"
        assert expediente.estado_fisico_documental_legacy == "Verificado"


def test_indice_sin_verificacion_queda_pendiente_de_verificacion(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente()
        _documento(expediente)
        assert expediente.estado_fisico_documental == "Pendiente de verificación"


def test_verificacion_documental_posterior_al_indice_es_vigente(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente()
        documento = _documento(expediente)
        usuario = Usuario.query.filter_by(usuario="admin-documental").first()
        _verificar(
            expediente,
            usuario,
            cuando=(documento.actualizado_en or documento.creado_en) + timedelta(seconds=1),
        )
        db.session.expire_all()
        expediente = Expediente.query.get(expediente.id)
        resumen = calcular_estado_documental(expediente)
        assert resumen["estado"] == "Verificado"
        assert resumen["verificacion_vigente"] is True


def test_cambio_documental_posterior_invalida_verificacion_anterior(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente()
        documento = _documento(expediente)
        usuario = Usuario.query.filter_by(usuario="admin-documental").first()
        verificacion = _verificar(
            expediente,
            usuario,
            cuando=(documento.actualizado_en or documento.creado_en) + timedelta(seconds=1),
        )

        documento.actualizado_en = verificacion.creado_en + timedelta(seconds=1)
        db.session.commit()
        db.session.expire_all()
        expediente = Expediente.query.get(expediente.id)
        assert expediente.estado_fisico_documental == "Verificación desactualizada"


def test_rectificacion_e_indice_se_comparan_sin_reescribir_historico(app_estado_documental):
    with app_estado_documental.app_context():
        expediente = _expediente()
        _documento(expediente, 1, 4)
        expediente.folios_rectificados = 5
        expediente.anexos_rectificados = 0
        expediente.rectificado_en = datetime.utcnow()
        db.session.commit()

        resumen = calcular_estado_documental(expediente)
        assert resumen["coincide_foliacion"] is False
        assert any("Rectificación física" in item for item in resumen["incidencias"])
        assert expediente.estado_fisico_documental_legacy == "Verificado"
