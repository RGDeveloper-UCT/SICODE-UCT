import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.prestamo_grupal import PrestamoGrupo, PrestamoGrupoDetalle
from app.models.traslado_virtual import TrasladoVirtualExpediente
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
        "modalidad": "FISICO",
        "solicitante": "Coordinación solicitante",
        "persona_entrega": "Archivo UCT",
        "persona_recibe": "Analista receptor",
        "fecha_estimada_devolucion": "2026-08-31",
        "plataforma": "",
        "enlace_virtual": "",
        "asunto_virtual": "",
        "observaciones": "Préstamo por rango para prueba.",
    }


def _datos_grupo_virtual(desde=1, hasta=3):
    return {
        "sp_desde": str(desde),
        "sp_hasta": str(hasta),
        "modalidad": "VIRTUAL",
        "solicitante": "Coordinación solicitante",
        "persona_entrega": "Archivo digital UCT",
        "persona_recibe": "Analista destinatario",
        "fecha_estimada_devolucion": "",
        "plataforma": "Google Drive",
        "enlace_virtual": "drive.google.com/expedientes-rango-prueba",
        "asunto_virtual": "Traslado virtual para revisión institucional",
        "observaciones": "Traslado virtual por rango para prueba.",
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

        assert grupo.modalidad == "FISICO"
        assert grupo.es_fisico is True
        assert grupo.plataforma is None
        assert grupo.enlace_virtual is None
        assert grupo.sp_desde == 1
        assert grupo.sp_hasta == 3
        assert grupo.total_expedientes == 3
        assert grupo.total_pendientes == 3
        assert len(prestamos) == 3
        assert TrasladoVirtualExpediente.query.count() == 0
        assert len(detalles) == 3
        assert {detalle.expediente.no_sp for detalle in detalles} == {"1", "2", "3"}
        assert len({prestamo.numero_control for prestamo in prestamos}) == 3
        assert all(prestamo.estado == "En préstamo" for prestamo in prestamos)
        assert all(grupo.numero_control in prestamo.numero_control for prestamo in prestamos)
        assert all(prestamo.detalle_grupal.grupo.id == grupo.id for prestamo in prestamos)
        assert all(detalle.traslado_virtual is None for detalle in detalles)


def test_traslado_virtual_por_rango_guarda_plataforma_y_movimientos_individuales(app_grupal, cliente_grupal):
    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo_virtual(),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert "/prestamos/grupales/1/constancia/pdf" in respuesta.headers["Location"]

    with app_grupal.app_context():
        grupo = PrestamoGrupo.query.one()
        traslados = TrasladoVirtualExpediente.query.order_by(TrasladoVirtualExpediente.expediente_id).all()
        detalles = PrestamoGrupoDetalle.query.order_by(PrestamoGrupoDetalle.orden).all()

        assert grupo.modalidad == "VIRTUAL"
        assert grupo.es_virtual is True
        assert grupo.estado == "Traslado virtual"
        assert grupo.plataforma == "Google Drive"
        assert grupo.enlace_virtual == "https://drive.google.com/expedientes-rango-prueba"
        assert grupo.asunto_virtual == "Traslado virtual para revisión institucional"
        assert grupo.fecha_estimada_devolucion is None
        assert grupo.total_expedientes == 3
        assert grupo.total_pendientes == 0
        assert PrestamoExpediente.query.count() == 0
        assert len(traslados) == 3
        assert len(detalles) == 3
        assert all(detalle.prestamo is None for detalle in detalles)
        assert all(detalle.traslado_virtual is not None for detalle in detalles)
        assert all(traslado.plataforma == "Google Drive" for traslado in traslados)
        assert all(traslado.enlace_corto == grupo.enlace_virtual for traslado in traslados)
        assert all(traslado.detalle_grupal.grupo.id == grupo.id for traslado in traslados)


def test_virtual_no_bloquea_ni_duplica_prestamo_fisico_activo(app_grupal, cliente_grupal):
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
        data=_datos_grupo_virtual(),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_grupal.app_context():
        grupo = PrestamoGrupo.query.one()
        assert grupo.modalidad == "VIRTUAL"
        assert PrestamoExpediente.query.count() == 1
        assert TrasladoVirtualExpediente.query.count() == 3
        expediente = Expediente.query.filter_by(no_sp="2").one()
        assert expediente.disponibilidad == "En préstamo"


def test_virtual_exige_plataforma_enlace_y_asunto(app_grupal, cliente_grupal):
    datos = _datos_grupo_virtual()
    datos.update({"plataforma": "", "enlace_virtual": "", "asunto_virtual": ""})
    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=datos,
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 400
    assert "plataforma" in texto.lower()
    assert "enlace" in texto.lower()
    assert "asunto" in texto.lower()

    with app_grupal.app_context():
        assert PrestamoGrupo.query.count() == 0
        assert PrestamoExpediente.query.count() == 0
        assert TrasladoVirtualExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0


def test_constancia_grupal_fisica_es_pdf(app_grupal, cliente_grupal):
    cliente_grupal.post("/prestamos/grupales/nuevo", data=_datos_grupo(), follow_redirects=False)
    pdf = cliente_grupal.get("/prestamos/grupales/1/constancia/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")


def test_constancia_grupal_virtual_es_pdf(app_grupal, cliente_grupal):
    cliente_grupal.post("/prestamos/grupales/nuevo", data=_datos_grupo_virtual(), follow_redirects=False)
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
        assert TrasladoVirtualExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0


def test_rango_virtual_con_sp_no_rectificado_tampoco_crea_parcial(app_grupal, cliente_grupal):
    with app_grupal.app_context():
        expediente = Expediente.query.filter_by(no_sp="3").one()
        expediente.folios_rectificados = None
        expediente.anexos_rectificados = None
        db.session.commit()

    respuesta = cliente_grupal.post(
        "/prestamos/grupales/nuevo",
        data=_datos_grupo_virtual(),
        follow_redirects=True,
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "SP 3" in texto
    assert "pendientes de rectificación" in texto

    with app_grupal.app_context():
        assert PrestamoGrupo.query.count() == 0
        assert TrasladoVirtualExpediente.query.count() == 0
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
        assert TrasladoVirtualExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0


def test_rango_fisico_con_prestamo_activo_no_crea_parcial(app_grupal, cliente_grupal):
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
        assert TrasladoVirtualExpediente.query.count() == 0
        assert PrestamoGrupoDetalle.query.count() == 0
