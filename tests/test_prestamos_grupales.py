import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.prestamo_grupal import PrestamoGrupo, PrestamoGrupoDetalle
from app.models.usuario import Usuario


@pytest.fixture()
def app_grupal():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Grupal",
            usuario="grupal-admin",
            correo="grupal@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(usuario)
        for numero in range(1, 4):
            db.session.add(Expediente(
                codigo_interno=f"SICODE-UCT-{numero:04d}",
                no_sp=str(numero),
                nombre_referencia=f"Persona SP {numero}",
                estado_administrativo="Activo",
                estado_fisico_documental="Verificado",
                expediente_fisico_registrado=True,
                folios_rectificados=100 + numero,
                anexos_rectificados=numero,
                activo=True,
            ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_grupal(app_grupal):
    cliente = app_grupal.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "grupal-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _datos_grupo(desde=1, hasta=3):
    return {
        "sp_desde": str(desde),
        "sp_hasta": str(hasta),
        "solicitante": "Coordinación solicitante",
        "persona_entrega": "Archivo UCT",
        "persona_recibe": "Analista receptor",
        "fecha_estimada_devolucion": "2026-08-31",
        "observaciones": "Préstamo por rango para prueba.",
    }


def test_prestamo_por_rango_crea_grupo_y_prestamos_individuales(app_grupal, cliente_grupal):
    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo(),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert "/prestamos/grupales/1/constancia/pdf" in respuesta.headers["Location"]

    with app_grupal.app_context():
        grupo = PrestamoGrupo.query.one()
        prestamos = PrestamoExpediente.query.order_by(PrestamoExpediente.expediente_id).all()
        detalles = PrestamoGrupoDetalle.query.order_by(PrestamoGrupoDetalle.orden).all()

        assert grupo.sp_desde == 1
        assert grupo.sp_hasta == 3
        assert grupo.total_expedientes == 3
        assert grupo.total_pendientes == 3
        assert len(prestamos) == 3
        assert len(detalles) == 3
        assert {detalle.expediente.no_sp for detalle in detalles} == {"1", "2", "3"}
        assert len({prestamo.numero_control for prestamo in prestamos}) == 3
        assert all(prestamo.estado == "En préstamo" for prestamo in prestamos)
        assert all(grupo.numero_control in prestamo.numero_control for prestamo in prestamos)
        assert all(prestamo.detalle_grupal.grupo.id == grupo.id for prestamo in prestamos)


def test_constancia_grupal_es_pdf(app_grupal, cliente_grupal):
    cliente_grupal.post("/prestamos/grupales/nuevo", data=_datos_grupo(), follow_redirects=False)
    pdf = cliente_grupal.get("/prestamos/grupales/1/constancia/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")


def test_rango_con_sp_no_rectificado_no_crea_parcial(app_grupal, cliente_grupal):
    with app_grupal.app_context():
        expediente = Expediente.query.filter_by(no_sp="2").one()
        expediente.folios_rectificados = None
        expediente.anexos_rectificados = None
        db.session.commit()

    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo(),
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "SP 2" in texto
    assert "pendientes de rectificación" in texto

    with app_grupal.app_context():
        assert PrestamoGrupo.query.count() == 0
        assert PrestamoExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0


def test_rango_con_sp_faltante_no_crea_parcial(app_grupal, cliente_grupal):
    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo(1, 4),
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "faltan SP dentro del rango" in texto
    assert "4" in texto

    with app_grupal.app_context():
        assert PrestamoGrupo.query.count() == 0
        assert PrestamoExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0


def test_rango_con_prestamo_activo_no_crea_parcial(app_grupal, cliente_grupal):
    with app_grupal.app_context():
        expediente = Expediente.query.filter_by(no_sp="2").one()
        db.session.add(PrestamoExpediente(
            expediente_id=expediente.id,
            numero_control="PRE-EXISTENTE-SP-2",
            solicitante="Solicitante previo",
            persona_entrega="Archivo UCT",
            persona_recibe="Receptor previo",
            estado="En préstamo",
            activo=True,
        ))
        db.session.commit()

    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo(),
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "SP 2" in texto
    assert "préstamo activo" in texto

    with app_grupal.app_context():
        assert PrestamoGrupo.query.count() == 0
        assert PrestamoExpediente.query.count() == 1
        assert PrestamoGrupoDetalle.query.count() == 0
