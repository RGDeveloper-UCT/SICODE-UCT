from io import BytesIO

import pytest
from openpyxl import load_workbook
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.bitacora import Bitacora
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_reportes():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuarios = [
            Usuario(
                nombre="Admin Reportes",
                usuario="reportes-admin",
                correo="reportes-admin@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="administrador",
                activo=True,
            ),
            Usuario(
                nombre="Usuario Reportes",
                usuario="reportes-user",
                correo="reportes-user@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="usuario_autorizado",
                activo=True,
            ),
            Usuario(
                nombre="Visor Reportes",
                usuario="reportes-visor",
                correo="reportes-visor@uct.local",
                password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
                debe_cambiar_password=False,
                rol="visor",
                activo=True,
            ),
        ]
        expediente = Expediente(
            codigo_interno="SICODE-UCT-RPT-001",
            no_sp="777",
            estado_administrativo="Activo",
            estado_fisico_documental="Pendiente de verificación",
            expediente_fisico_registrado=True,
            activo=True,
        )
        db.session.add_all(usuarios + [expediente])
        db.session.flush()
        db.session.add(PrestamoExpediente(
            expediente_id=expediente.id,
            numero_control="PREST-RPT-001",
            solicitante="=2+2",
            persona_entrega="Operador",
            persona_recibe="Receptor",
            estado="En préstamo",
            activo=True,
        ))
        db.session.add(Bitacora(
            usuario_id=usuarios[1].id,
            expediente_id=expediente.id,
            accion="PRUEBA_REPORTE",
            modulo="Pruebas",
            descripcion="=HYPERLINK(\"https://example.invalid\",\"x\")",
        ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _cliente_login(app, usuario):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": usuario, "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_visor_puede_consultar_pero_no_exportar(app_reportes):
    cliente = _cliente_login(app_reportes, "reportes-visor")
    vista = cliente.get("/reportes")
    assert vista.status_code == 200
    assert "Centro de reportes" in vista.get_data(as_text=True)
    assert "rol Visor puede consultar" in vista.get_data(as_text=True)

    descarga = cliente.get("/reportes/exportar?dataset=expedientes&formato=xlsx")
    assert descarga.status_code == 403


def test_consolidado_es_exclusivo_de_administracion(app_reportes):
    cliente_usuario = _cliente_login(app_reportes, "reportes-user")
    assert cliente_usuario.get("/reportes?dataset=consolidado").status_code == 403

    cliente_admin = _cliente_login(app_reportes, "reportes-admin")
    respuesta = cliente_admin.get("/reportes?dataset=consolidado")
    assert respuesta.status_code == 200
    assert "Consolidado administrativo" in respuesta.get_data(as_text=True)


def test_excel_protege_textos_que_parecen_formulas_y_no_se_cachea(app_reportes):
    cliente = _cliente_login(app_reportes, "reportes-user")
    respuesta = cliente.get(
        "/reportes/exportar?dataset=prestamos&formato=xlsx&columnas=solicitante"
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["Cache-Control"] == "no-store, private"
    assert respuesta.headers["Pragma"] == "no-cache"

    libro = load_workbook(BytesIO(respuesta.data), data_only=False)
    hoja = libro.active
    assert hoja["A1"].value == "Solicitante"
    assert hoja["A2"].value == "'=2+2"
    assert hoja["A2"].data_type == "s"


def test_csv_protege_formula_y_usa_utf8_con_bom(app_reportes):
    cliente = _cliente_login(app_reportes, "reportes-user")
    respuesta = cliente.get(
        "/reportes/exportar?dataset=prestamos&formato=csv&columnas=solicitante"
    )
    assert respuesta.status_code == 200
    assert respuesta.data.startswith(b"\xef\xbb\xbf")
    texto = respuesta.data.decode("utf-8-sig")
    assert "'=2+2" in texto


def test_exportacion_legacy_de_bitacora_redirige_al_generador_seguro(app_reportes):
    cliente = _cliente_login(app_reportes, "reportes-user")
    respuesta = cliente.get("/bitacora/exportar/excel?q=PRUEBA", follow_redirects=False)
    assert respuesta.status_code == 302
    assert "/reportes/exportar" in respuesta.headers["Location"]
    assert "dataset=bitacora" in respuesta.headers["Location"]


def test_estado_documental_de_reporte_usa_valor_derivado_actual(app_reportes):
    cliente = _cliente_login(app_reportes, "reportes-user")
    respuesta = cliente.get("/reportes?dataset=expedientes&columnas=estado_documental")
    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert "Estado documental vigente" in texto
    # La columna histórica del fixture dice "Pendiente de verificación", pero
    # al no existir documentos el árbol canónico exige "Pendiente de indexación".
    assert "Pendiente de indexación" in texto
