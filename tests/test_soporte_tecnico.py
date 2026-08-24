import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.coordinacion import ActividadCoordinacion, RegistroCoordinacion
from app.models.soporte_tecnico import ServicioSoporteTecnico
from app.models.usuario import Usuario


@pytest.fixture()
def app_soporte():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = Usuario(
            nombre="Técnico Prueba",
            usuario="tecnico-prueba",
            correo="tecnico@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(admin)
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente_soporte(app_soporte):
    cliente = app_soporte.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "tecnico-prueba", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _datos_boleta():
    return {
        "fecha_hora_solicitud": "2026-08-24T09:30",
        "usuario_solicitante": "Usuario Atendido",
        "puesto_cargo": "Analista",
        "coordinacion_area": "Dirección",
        "tecnico_asignado": "Técnico Prueba",
        "tipos_servicio": ["SOFTWARE", "REVISION"],
        "software_detalles": ["BACKUP", "SOFTWARE_AUTORIZADO"],
        "revision_detalles": ["RED_INTERNET"],
        "tipo_equipo": "PC",
        "marca_modelo": "Equipo institucional",
        "numero_serie": "SERIE-123",
        "inventario": "SICOIN-456",
        "ip_nombre_equipo": "PC-DIRECCION-01",
        "descripcion_solicitud": "Respaldo de información y revisión de conectividad.",
        "diagnostico_trabajo": "Se verificó conectividad y se realizó el respaldo autorizado.",
        "estado_final": "RESUELTO",
        "seguimiento": "NO",
        "fecha_hora_cierre": "2026-08-24T10:10",
        "tiempo_empleado": "00:40:00",
        "observaciones_cierre": "Pruebas satisfactorias.",
        "nombre_firma_usuario": "Usuario Atendido",
        "fecha_firma_usuario": "2026-08-24",
        "nombre_firma_tecnico": "Técnico Prueba",
        "fecha_firma_tecnico": "2026-08-24",
    }


def test_panel_y_formulario_contienen_boleta_completa(cliente_soporte):
    panel = cliente_soporte.get("/coordinacion/soporte-tecnico/")
    formulario = cliente_soporte.get("/coordinacion/soporte-tecnico/nuevo")
    texto = formulario.get_data(as_text=True)

    assert panel.status_code == 200
    assert "Soporte técnico y servicios TI" in panel.get_data(as_text=True)
    assert formulario.status_code == 200
    assert "Tipo de servicio solicitado" in texto
    assert "Creación / modificación / baja de usuario" in texto
    assert "Backup de archivos de información" in texto
    assert "Revisión y verificación de línea telefónica" in texto
    assert "Identificación del equipo" in texto
    assert "Resultado y cierre del servicio" in texto
    assert "data-soporte-section" in texto
    assert "SICOIN" in texto
    assert "Tiempo de resolución" in texto
    assert "Minimizar y seguir en SICODE" in texto
    assert "data-ticket-soporte-burbuja" in texto
    assert "ticket_soporte.js" in texto


def test_formulario_compacto_cancelacion_y_avisos(cliente_soporte):
    formulario = cliente_soporte.get("/coordinacion/soporte-tecnico/nuevo")
    texto = formulario.get_data(as_text=True)

    assert formulario.status_code == 200
    assert "soporte-layout-compacto" in texto
    assert "soporte-form-compacto" in texto
    assert "Cancelar boleta" in texto
    assert 'data-cancelar-ticket' in texto
    assert texto.count('data-soporte-toast') >= 2
    assert 'data-soporte-toast-cerrar' in texto
    assert "Ticket en atención" in texto
    assert "Registro administrativo" in texto

    javascript = cliente_soporte.get("/static/js/soporte_tecnico.js").get_data(as_text=True)
    estilos = cliente_soporte.get("/static/css/soporte_tecnico.css").get_data(as_text=True)
    assert "60000" in javascript
    assert "window.confirm" in javascript
    assert "ticketApi?.clear()" in javascript
    assert "detalleFuncional.hidden" in javascript
    assert ".soporte-notificaciones" in estilos
    assert "grid-template-columns: repeat(12" in estilos


def test_registrar_soporte_se_integra_con_coordinacion_y_bitacora(app_soporte, cliente_soporte):
    respuesta = cliente_soporte.post(
        "/coordinacion/soporte-tecnico/nuevo",
        data=_datos_boleta(),
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    assert "/coordinacion/soporte-tecnico/boletas/" in respuesta.headers["Location"]

    with app_soporte.app_context():
        boleta = ServicioSoporteTecnico.query.one()
        registro = RegistroCoordinacion.query.one()
        actividad = ActividadCoordinacion.query.one()
        auditoria = Bitacora.query.filter_by(accion="REGISTRAR_SOPORTE_TECNICO").one()

        assert boleta.numero_boleta.startswith("BST-2026-")
        assert boleta.tipos_servicio == ["SOFTWARE", "REVISION"]
        assert "BACKUP" in boleta.software_detalles
        assert boleta.estado_final == "RESUELTO"
        assert boleta.inventario == "SICOIN-456"
        assert boleta.tiempo_empleado == "00:40:00"
        assert registro.tipo == "ACTIVIDAD"
        assert registro.estado == "Completo"
        assert actividad.tipo_actividad == "SOPORTE TI"
        assert actividad.descripcion == boleta.descripcion_solicitud
        assert auditoria.entidad == "ServicioSoporteTecnico"
        assert auditoria.datos_posteriores["estado_final"] == "RESUELTO"


def test_boleta_pdf_es_constancia_imprimible(app_soporte, cliente_soporte):
    cliente_soporte.post(
        "/coordinacion/soporte-tecnico/nuevo",
        data=_datos_boleta(),
        follow_redirects=False,
    )
    with app_soporte.app_context():
        boleta_id = ServicioSoporteTecnico.query.one().id

    respuesta = cliente_soporte.get(f"/coordinacion/soporte-tecnico/boletas/{boleta_id}/pdf")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/pdf"
    assert respuesta.data.startswith(b"%PDF")
    assert "boleta_soporte_BST-2026-" in respuesta.headers["Content-Disposition"]


def test_pdf_limpio_y_ruta_nueva(app_soporte, cliente_soporte):
    cliente_soporte.post(
        "/coordinacion/soporte-tecnico/nuevo",
        data=_datos_boleta(),
        follow_redirects=False,
    )
    with app_soporte.app_context():
        boleta_id = ServicioSoporteTecnico.query.one().id

    detalle = cliente_soporte.get(f"/coordinacion/soporte-tecnico/boletas/{boleta_id}")
    texto_detalle = detalle.get_data(as_text=True)
    assert detalle.status_code == 200
    assert "SICOIN" in texto_detalle
    assert "Tiempo de resolución" in texto_detalle
    assert f"/coordinacion/soporte-tecnico/boletas/{boleta_id}/pdf-limpio" in texto_detalle

    respuesta = cliente_soporte.get(
        f"/coordinacion/soporte-tecnico/boletas/{boleta_id}/pdf-limpio"
    )
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/pdf"
    assert respuesta.data.startswith(b"%PDF")
    assert f"BST-2026-{boleta_id:05d}_soporte_tecnico.pdf" in respuesta.headers["Content-Disposition"]

    with app_soporte.app_context():
        auditoria = Bitacora.query.filter_by(accion="EXPORTAR_BOLETA_SOPORTE_PDF").order_by(Bitacora.id.desc()).first()
        assert auditoria is not None
        assert auditoria.datos_posteriores["modo"] == "solo_campos_con_datos"
