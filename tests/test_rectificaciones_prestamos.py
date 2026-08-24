from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.anexo_rectificado import AnexoRectificado
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_rectificacion():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Rectificación",
            usuario="rectifica-admin",
            correo="rectifica@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0106",
            no_sp="106",
            nombre_referencia="Persona de Rectificación",
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
def cliente_rectificacion(app_rectificacion):
    cliente = app_rectificacion.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "rectifica-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_panel_sp_muestra_rectificar_folios_y_anexos(cliente_rectificacion):
    respuesta = cliente_rectificacion.get("/expedientes?q=106")
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Rectificar" in texto
    assert ">Folios<" in texto
    assert ">Anexos<" in texto
    assert texto.count("Pendiente") >= 2


def test_prestamo_fisico_y_virtual_bloqueados_hasta_rectificar(cliente_rectificacion):
    fisico = cliente_rectificacion.get("/expedientes/1/prestamos/nuevo", follow_redirects=False)
    virtual = cliente_rectificacion.get("/expedientes/1/traslado-virtual/nuevo", follow_redirects=False)

    assert fisico.status_code == 302
    assert virtual.status_code == 302
    assert "/expedientes/1/rectificar" in fisico.headers["Location"]
    assert "/expedientes/1/rectificar" in virtual.headers["Location"]

    panel = cliente_rectificacion.get("/prestamos").get_data(as_text=True)
    assert "Rectificar antes de prestar" in panel
    assert "Rectificar antes de traslado virtual" in panel


def test_rectificacion_permite_total_de_19_anexos_sin_describirlos(app_rectificacion, cliente_rectificacion):
    respuesta = cliente_rectificacion.post(
        "/expedientes/1/rectificar",
        data={"folios_rectificados": "286", "anexos_rectificados": "19"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_rectificacion.app_context():
        expediente = db.session.get(Expediente, 1)
        assert expediente.folios_rectificados == 286
        assert expediente.anexos_rectificados == 19
        assert expediente.rectificacion_completa is True
        assert expediente.estado_fisico_documental == "Verificado"
        assert expediente.rectificado_por_id is not None
        assert AnexoRectificado.query.filter_by(expediente_id=1, activo=True).count() == 0

    assert cliente_rectificacion.get("/expedientes/1/prestamos/nuevo").status_code == 200
    assert cliente_rectificacion.get("/expedientes/1/traslado-virtual/nuevo").status_code == 200


def test_rectificacion_guarda_un_anexo_independiente_con_titulo_y_modelo_completo(app_rectificacion, cliente_rectificacion):
    respuesta = cliente_rectificacion.post(
        "/expedientes/1/rectificar",
        data={
            "folios_rectificados": "320",
            "anexos_rectificados": "2",
            "anexo_1_titulo": "Resolución de movilización",
            "anexo_1_tipo_anexo": "MOVILIZACION",
            "anexo_1_numero_anexo": "1",
            "anexo_1_fecha_recepcion": "2026-08-24",
            "anexo_1_persona_entrega": "Unidad remitente",
            "anexo_1_rc": "202624183",
            "anexo_1_providencia": "5908-2026",
            "anexo_1_folios": "145-153",
            "anexo_1_escaneado": "1",
            "anexo_1_fecha_escaneado": "2026-08-24",
            "anexo_1_observaciones": "Detalle opcional del anexo.",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_rectificacion.app_context():
        anexos = AnexoRectificado.query.filter_by(expediente_id=1, activo=True).all()
        assert len(anexos) == 1
        anexo = anexos[0]
        assert anexo.titulo == "Resolución de movilización"
        assert anexo.tipo_anexo == "MOVILIZACION"
        assert anexo.numero_anexo == "1"
        assert anexo.fecha_recepcion == date(2026, 8, 24)
        assert anexo.persona_entrega == "Unidad remitente"
        assert anexo.rc == "202624183"
        assert anexo.providencia == "5908-2026"
        assert anexo.folios == "145-153"
        assert anexo.escaneado is True
        assert anexo.fecha_escaneado == date(2026, 8, 24)


def test_constancia_fisica_usa_ruta_pdf_rectificada(app_rectificacion, cliente_rectificacion):
    cliente_rectificacion.post(
        "/expedientes/1/rectificar",
        data={"folios_rectificados": "210", "anexos_rectificados": "4"},
        follow_redirects=False,
    )
    respuesta = cliente_rectificacion.post(
        "/expedientes/1/prestamos/nuevo",
        data={
            "solicitante": "Solicitante de prueba",
            "persona_entrega": "Archivo UCT",
            "persona_recibe": "Analista receptor",
            "fecha_estimada_devolucion": "2026-08-30",
            "observaciones": "Préstamo con expediente rectificado.",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_rectificacion.app_context():
        prestamo = PrestamoExpediente.query.one()
        prestamo_id = prestamo.id

    pdf = cliente_rectificacion.get(
        f"/prestamos/{prestamo_id}/comprobante/pdf",
        follow_redirects=True,
    )
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
