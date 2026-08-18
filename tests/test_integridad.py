from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.alerta import Alerta
from app.models.coordinacion import RegistroCoordinacion, RemisionCoordinacion, RemisionExpediente
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.usuario import Usuario
from app.services.sp_service import normalizar_sp


@pytest.fixture()
def app_integridad():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Admin",
            usuario="admin-integridad",
            correo="integridad@uct.local",
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
        codigo_interno="SICODE-UCT-0001",
        no_sp="SP-001",
        nombre_referencia="Prueba",
        estado_administrativo="Activo",
        estado_fisico_documental="Pendiente de verificación",
        expediente_fisico_registrado=True,
        activo=True,
    )
    datos.update(kwargs)
    expediente = Expediente(**datos)
    db.session.add(expediente)
    db.session.commit()
    return expediente


def _prestamo(expediente, numero):
    return PrestamoExpediente(
        expediente_id=expediente.id,
        numero_control=numero,
        solicitante="Solicitante",
        persona_entrega="Entrega",
        persona_recibe="Recibe",
        estado="En préstamo",
        activo=True,
    )


def test_sp_se_canoniza_en_modelo(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente()
        assert expediente.no_sp == "1"
        assert normalizar_sp("SP01") == normalizar_sp("SP-001") == normalizar_sp("001") == "1"


def test_disponibilidad_no_duplica_estado_administrativo(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente(estado_administrativo="En préstamo")
        assert expediente.estado_administrativo == "Activo"
        assert expediente.disponibilidad == "Disponible"

        prestamo = _prestamo(expediente, "PRE-1")
        db.session.add(prestamo)
        db.session.commit()
        assert expediente.disponibilidad == "En préstamo"
        assert expediente.estado_administrativo == "Activo"


def test_no_se_puede_prestar_sp_sin_expediente_fisico(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente(expediente_fisico_registrado=False, estado_fisico_documental="Sin expediente físico")
        db.session.add(_prestamo(expediente, "PRE-SIN-FISICO"))
        with pytest.raises(ValueError, match="expediente físico"):
            db.session.commit()
        db.session.rollback()


def test_un_solo_prestamo_activo_por_expediente(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente()
        db.session.add(_prestamo(expediente, "PRE-1"))
        db.session.commit()

        db.session.add(_prestamo(expediente, "PRE-2"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_devolucion_corrige_alerta_de_prestamo_vencido(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente()
        prestamo = _prestamo(expediente, "PRE-VENCIDO")
        prestamo.fecha_estimada_devolucion = date.today() - timedelta(days=1)
        alerta = Alerta(
            expediente_id=expediente.id,
            tipo_alerta="PRESTAMO_VENCIDO",
            titulo="Préstamo vencido",
            gravedad="Alta",
            estado="Abierta",
            origen="Automática",
        )
        db.session.add_all([prestamo, alerta])
        db.session.commit()

        prestamo.estado = "Devuelto"
        db.session.commit()
        assert alerta.estado == "Corregida"


def test_db_rechaza_total_folios_inconsistente(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente()
        documento = DocumentoExpediente(
            expediente_id=expediente.id,
            nombre_documento="Documento",
            tipo_documento="Documento",
            folio_inicio=1,
            folio_fin=10,
            total_folios=9,
            estado_revision="Verificado",
            es_anexo=False,
            activo=True,
        )
        db.session.add(documento)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_db_rechaza_foliacion_sin_expediente_fisico(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente(expediente_fisico_registrado=False, estado_fisico_documental="Sin expediente físico")
        documento = DocumentoExpediente(
            expediente_id=expediente.id,
            nombre_documento="Documento",
            tipo_documento="Documento",
            folio_inicio=1,
            folio_fin=1,
            total_folios=1,
            estado_revision="Verificado",
            es_anexo=False,
            activo=True,
        )
        db.session.add(documento)
        with pytest.raises(ValueError, match="expediente físico"):
            db.session.commit()
        db.session.rollback()


def test_no_repite_sp_en_misma_remision(app_integridad):
    with app_integridad.app_context():
        expediente = _expediente()
        usuario = Usuario.query.filter_by(usuario="admin-integridad").one()
        registro = RegistroCoordinacion(tipo="REMISION", usuario_id=usuario.id, estado="Completo")
        db.session.add(registro)
        db.session.flush()
        remision = RemisionCoordinacion(registro_id=registro.id, destino="Archivo/Bodega MINGOB")
        db.session.add(remision)
        db.session.flush()
        db.session.add(RemisionExpediente(remision_id=remision.id, expediente_id=expediente.id, no_sp_referencia="1"))
        db.session.commit()

        db.session.add(RemisionExpediente(remision_id=remision.id, expediente_id=expediente.id, no_sp_referencia="1"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
