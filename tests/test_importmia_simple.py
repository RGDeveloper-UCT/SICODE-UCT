"""ImportM.IA v4: pruebas de contrato simple y seguridad de conciliación."""
from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.coordinacion import PagoCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.services.importmia_simple_service import HEADERS, conciliar, leer, ImportMIAInvalido


def _excel(hojas=None):
    hojas = hojas or {}
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("INSTRUCCIONES")
    ws.append(["Paso", "Instrucción"])
    for nombre, columnas in HEADERS.items():
        sh = wb.create_sheet(nombre)
        sh.append(list(columnas))
        for registro in hojas.get(nombre, []):
            sh.append([registro.get(col) for col in columnas])
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()


@pytest.fixture()
def app_importmia():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Usuario(
            nombre="Admin ImportMIA", usuario="importmia-admin",
            correo="importmia@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False, rol="administrador", activo=True,
        ))
        db.session.add(Expediente(
            codigo_interno="UCT-95", no_sp="95", activo=True,
            expediente_fisico_registrado=False,
            anexos_rectificados=0,
        ))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_excel_v4_cuatro_hojas():
    contenido = _excel()
    hojas = leer(contenido)
    assert set(hojas) == {"EXPEDIENTES", "Indice", "ANEXOS", "PAGOS"}


def test_excel_invalido():
    with pytest.raises(ImportMIAInvalido):
        leer(b"excel roto")


def test_expediente_digital_no_cambia_flag_fisico(app_importmia):
    with app_importmia.app_context():
        plan = conciliar(_excel({"EXPEDIENTES": [{
            "sp": "95", "expediente_fisico": "SI",
            "evidencia_recepcion": "Carpeta digital",
        }]}))
        assert plan["grupos"]["EXPEDIENTES"][0]["estado"] == "DIFERENCIA_FISICO"
        assert Expediente.query.filter_by(no_sp="95").one().expediente_fisico_registrado is False


def test_pago_nuevo_y_boleta_incompleta(app_importmia):
    with app_importmia.app_context():
        base = {"sp": "95", "banco": "BANRURAL", "boleta": "B001",
                "monto": 100, "periodo_desde": date(2026, 11, 1),
                "periodo_hasta": date(2026, 11, 30), "tipo_referencia": "RC",
                "numero_referencia": "123", "providencia": "P-123",
                "fecha_recepcion": date(2026, 11, 2)}
        plan = conciliar(_excel({"PAGOS": [base]}))
        assert plan["grupos"]["PAGOS"][0]["estado"] == "NUEVO"
        assert PagoCoordinacion.query.count() == 0
        base["boleta"] = ""
        plan = conciliar(_excel({"PAGOS": [base]}))
        assert plan["grupos"]["PAGOS"][0]["estado"] == "REVISAR"


def test_anexo_sin_rectificacion_no_se_autoriza(app_importmia):
    with app_importmia.app_context():
        expediente = Expediente.query.filter_by(no_sp="95").one()
        expediente.anexos_rectificados = None
        db.session.commit()
        plan = conciliar(_excel({"ANEXOS": [{
            "sp": "95", "numero_anexo": 1,
            "tipo_codigo": "REPORTE_MONITOREO", "titulo": "Reporte de monitoreo",
            "es_vencido": "NO", "fecha_recepcion": date(2026, 11, 2)
        }]}))
        assert plan["grupos"]["ANEXOS"][0]["estado"] == "REVISAR_RECTIFICACION"


def test_ruta_y_control_de_login(app_importmia):
    cliente = app_importmia.test_client()
    assert cliente.post("/importmia/confirmar").status_code == 302
    reglas = {regla.endpoint: regla.rule for regla in app_importmia.url_map.iter_rules()}
    assert reglas["importmia.inicio"] == "/importmia/"
    assert reglas["importmia.confirmar"] == "/importmia/confirmar"

def test_importacion_pago_supervisado_idempotente(app_importmia):
    import re
    datos = _excel({"PAGOS": [{
        "sp": "95", "banco": "BANRURAL", "boleta": "B003",
        "monto": 125.50, "periodo_desde": date(2026, 11, 1),
        "periodo_hasta": date(2026, 11, 30),
        "tipo_referencia": "RC", "numero_referencia": "555",
        "providencia": "P-555", "fecha_recepcion": date(2026, 11, 2),
    }]})
    cliente = app_importmia.test_client()
    respuesta = cliente.post("/login", data={
        "usuario": "importmia-admin", "password": "Password123"
    })
    assert respuesta.status_code == 302

    vista = cliente.post("/importmia/", data={
        "accion": "previsualizar", "archivo": (BytesIO(datos), "carga.xlsx")
    }, content_type="multipart/form-data")
    assert vista.status_code == 200
    assert b"NUEVO" in vista.data
    token = re.search(rb'name="token" value="([^"]+)"', vista.data)
    assert token is not None

    confirmado = cliente.post("/importmia/confirmar", data={
        "token": token.group(1).decode(),
        "archivo": (BytesIO(datos), "carga.xlsx")
    }, content_type="multipart/form-data")
    assert confirmado.status_code == 302
    with app_importmia.app_context():
        assert PagoCoordinacion.query.count() == 1
        assert Expediente.query.filter_by(no_sp="95").one().expediente_fisico_registrado is False

    # Al repetir el Excel se diagnostica COINCIDE, no otro pago.
    with app_importmia.app_context():
        reanalisis = conciliar(datos)
        assert reanalisis["grupos"]["PAGOS"][0]["estado"] == "COINCIDE"
        assert PagoCoordinacion.query.count() == 1

def test_boletas_repetidas_en_excel_bloquean_ambas(app_importmia):
    pago = {
        "sp": "95", "banco": "BANRURAL", "boleta": "B099",
        "monto": 90, "periodo_desde": date(2026, 11, 1),
        "periodo_hasta": date(2026, 11, 30),
        "tipo_referencia": "RC", "numero_referencia": "099",
        "providencia": "PROV-99", "fecha_recepcion": date(2026, 11, 2),
    }
    with app_importmia.app_context():
        r = conciliar(_excel({"PAGOS": [pago, dict(pago)]}))
        assert [x["estado"] for x in r["grupos"]["PAGOS"]] == [
            "DUPLICADO_EXCEL", "DUPLICADO_EXCEL"
        ]


def test_anexos_repetidos_en_excel_bloquean_ambos(app_importmia):
    anexo = {"sp": "95", "numero_anexo": 1,
             "tipo_codigo": "REPORTE_MONITOREO",
             "fecha_recepcion": date(2026, 11, 2),
             "es_vencido": "NO"}
    with app_importmia.app_context():
        r = conciliar(_excel({"ANEXOS": [anexo, dict(anexo)]}))
        assert [x["estado"] for x in r["grupos"]["ANEXOS"]] == [
            "DUPLICADO_EXCEL", "DUPLICADO_EXCEL"
        ]
