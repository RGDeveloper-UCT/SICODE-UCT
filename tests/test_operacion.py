from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.alerta import Alerta
from app.models.coordinacion import (
    AnexoCoordinacion,
    MovimientoDispositivo,
    PagoCoordinacion,
    RegistroCoordinacion,
)
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.models.verificacion import VerificacionExpediente


@pytest.fixture()
def app_operacion():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Admin Operación",
            usuario="admin-op",
            correo="admin-op@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0100",
            no_sp="100",
            nombre_referencia="Sujeto Operación",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all([admin, expediente])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente(app_operacion):
    cliente = app_operacion.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "admin-op", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_recepcion_integra_quien_entrega_folios_y_quien_recibe(app_operacion, cliente):
    respuesta = cliente.post(
        "/coordinacion/registrar/monitoreo",
        data={
            "no_sp": "100",
            "rc": "RC-100",
            "providencia": "PROV-100",
            "fecha_recepcion": date.today().isoformat(),
            "persona_entrega": "Centro de Control y Monitoreo",
            "folios": "1-8",
            "tipo_documento": "PROVIDENCIA",
            "numero_reporte": "REP-100",
            "tipo_evento": "No comunicación",
            "observaciones": "Prueba de recepción",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_operacion.app_context():
        registro = RegistroCoordinacion.query.filter_by(rc="RC-100").one()
        assert registro.persona_entrega == "Centro de Control y Monitoreo"
        assert registro.folios_recepcion == "1-8"
        assert registro.usuario.nombre == "Admin Operación"
        assert registro.expediente.no_sp == "100"


def test_verificacion_con_observaciones_actualiza_estado_y_alerta(app_operacion, cliente):
    respuesta = cliente.post(
        "/expedientes/1/verificaciones",
        data={
            "tipo": "INTEGRAL",
            "resultado": "Con observaciones",
            "folios_verificados": "25",
            "observaciones": "Falta revisar anexo.",
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_operacion.app_context():
        expediente = db.session.get(Expediente, 1)
        verificacion = VerificacionExpediente.query.one()
        assert expediente.estado_fisico_documental == "Con observaciones"
        assert verificacion.folios_verificados == 25
        assert Alerta.query.filter_by(tipo_alerta="REVISION_EXPEDIENTE", estado="Abierta").count() == 1


def test_verificacion_correcta_resuelve_alertas_de_revision(app_operacion, cliente):
    with app_operacion.app_context():
        db.session.add(Alerta(
            expediente_id=1,
            tipo_alerta="REVISION_EXPEDIENTE",
            titulo="Revisión pendiente",
            gravedad="Media",
            estado="Abierta",
            origen="Automática",
        ))
        db.session.commit()

    respuesta = cliente.post(
        "/expedientes/1/verificaciones",
        data={"tipo": "DOCUMENTAL", "resultado": "Verificado", "folios_verificados": "25"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302

    with app_operacion.app_context():
        alerta = Alerta.query.filter_by(tipo_alerta="REVISION_EXPEDIENTE").one()
        assert alerta.estado == "Corregida"
        assert db.session.get(Expediente, 1).estado_fisico_documental == "Verificado"


def test_listado_coordinacion_usa_paginacion(app_operacion, cliente):
    with app_operacion.app_context():
        usuario = Usuario.query.filter_by(usuario="admin-op").one()
        for numero in range(80):
            db.session.add(RegistroCoordinacion(
                tipo="ACTIVIDAD",
                fecha_recepcion=date.today(),
                usuario_id=usuario.id,
                usuario_origen=usuario.nombre,
                estado="Completo",
                origen_registro="MANUAL",
                observaciones=f"Registro {numero}",
            ))
        db.session.commit()

    respuesta = cliente.get("/coordinacion/registros")
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Mostrando <strong>75</strong>" in texto
    assert "Página 1 de 2" in texto


def test_listado_coordinacion_prioriza_campos_relevantes_por_tipo(app_operacion, cliente):
    with app_operacion.app_context():
        usuario = Usuario.query.filter_by(usuario="admin-op").one()

        pago = RegistroCoordinacion(
            tipo="PAGO",
            no_sp_referencia="100",
            rc="RC-PAGO",
            providencia="PROV-PAGO",
            fecha_recepcion=date(2026, 8, 3),
            folios_recepcion="3",
            usuario_id=usuario.id,
            usuario_origen=usuario.nombre,
            estado="Completo",
            origen_registro="MANUAL",
        )
        db.session.add(pago)
        db.session.flush()
        db.session.add(PagoCoordinacion(
            registro_id=pago.id,
            folios="3",
            periodo_desde=date(2026, 6, 27),
            periodo_hasta=date(2026, 7, 26),
            boleta="36157837",
            total=1500,
        ))

        instalacion = RegistroCoordinacion(
            tipo="INSTALACION",
            no_sp_referencia="100",
            rc="RC-INST",
            providencia="PROV-INST",
            fecha_recepcion=date(2026, 8, 4),
            usuario_id=usuario.id,
            usuario_origen=usuario.nombre,
            estado="Completo",
            origen_registro="IMPORTACION_EXCEL",
        )
        db.session.add(instalacion)
        db.session.flush()
        db.session.add(MovimientoDispositivo(
            registro_id=instalacion.id,
            movimiento="INSTALACION",
            descripcion="EXPEDIENTE",
        ))

        anexo = RegistroCoordinacion(
            tipo="ANEXO",
            no_sp_referencia="100",
            rc="RC-ANEXO",
            providencia="PROV-ANEXO",
            fecha_recepcion=date(2026, 8, 5),
            folios_recepcion="3",
            usuario_id=usuario.id,
            usuario_origen=usuario.nombre,
            estado="Completo",
            origen_registro="IMPORTACION_EXCEL",
        )
        db.session.add(anexo)
        db.session.flush()
        db.session.add(AnexoCoordinacion(
            registro_id=anexo.id,
            tipo_anexo="MOVILIZACION",
            folios="3",
            numero_anexo="4",
            escaneado=True,
            fecha_escaneado=date(2026, 8, 6),
        ))
        db.session.commit()

    respuesta_pago = cliente.get("/coordinacion/registros?tipo=PAGO")
    texto_pago = respuesta_pago.get_data(as_text=True)
    assert respuesta_pago.status_code == 200
    assert ">Período<" in texto_pago
    assert ">Boleta<" in texto_pago
    assert ">Total<" in texto_pago
    assert "27/06/2026 al 26/07/2026" in texto_pago
    assert "36157837" in texto_pago
    assert "Q 1500.00" in texto_pago

    respuesta_inst = cliente.get("/coordinacion/registros?tipo=INSTALACION")
    texto_inst = respuesta_inst.get_data(as_text=True)
    assert respuesta_inst.status_code == 200
    assert ">Fecha<" in texto_inst
    assert ">RC<" in texto_inst
    assert ">Providencia<" in texto_inst
    assert ">Descripción<" in texto_inst
    assert "RC-INST" in texto_inst
    assert "PROV-INST" in texto_inst
    assert "EXPEDIENTE" in texto_inst
    assert ">Boleta<" not in texto_inst
    assert ">Total<" not in texto_inst

    respuesta_anexo = cliente.get("/coordinacion/registros?tipo=ANEXO")
    texto_anexo = respuesta_anexo.get_data(as_text=True)
    assert respuesta_anexo.status_code == 200
    assert ">Fecha<" in texto_anexo
    assert ">RC<" in texto_anexo
    assert ">Providencia<" in texto_anexo
    assert ">Tipo de anexo<" in texto_anexo
    assert ">Anexo No.<" in texto_anexo
    assert ">Escaneado<" in texto_anexo
    assert "05/08/2026" in texto_anexo
    assert "RC-ANEXO" in texto_anexo
    assert "PROV-ANEXO" in texto_anexo
    assert "MOVILIZACION" in texto_anexo
    assert ">Boleta<" not in texto_anexo
    assert ">Total<" not in texto_anexo
