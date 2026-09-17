from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.coordinacion import AnalisisRiesgo, AnexoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.usuario import Usuario


@pytest.fixture()
def app_riesgo_masivo():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Administrador Masivo",
            usuario="riesgo-masivo-admin",
            correo="riesgo-masivo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        expediente = Expediente(
            codigo_interno="SICODE-UCT-0044",
            no_sp="44",
            nombre_referencia="SP riesgo masivo",
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
def cliente_riesgo_masivo(app_riesgo_masivo):
    cliente = app_riesgo_masivo.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "riesgo-masivo-admin", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def _rectificar(cliente, total):
    respuesta = cliente.post(
        "/coordinacion/monitoreo/rectificar-anexos",
        json={"expediente_id": 1, "total_anexos": total},
    )
    assert respuesta.status_code == 200


def _fila(correlativo="AR-2026-100", fecha="2026-09-17", **extra):
    fila = {
        "id": extra.pop("id", correlativo),
        "fecha_recepcion": fecha,
        "correlativo": correlativo,
        "no_sp": extra.pop("no_sp", "44"),
    }
    fila.update(extra)
    return fila


def test_catalogo_muestra_registro_masivo_en_analisis(cliente_riesgo_masivo):
    respuesta = cliente_riesgo_masivo.get("/coordinacion/anexos/nuevo")
    texto = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Registro masivo de análisis de riesgo" in texto
    assert "/coordinacion/anexos/analisis-riesgo/masivo" in texto


def test_masivo_pide_rectificacion_antes_de_proponer_anexo(cliente_riesgo_masivo):
    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/validar",
        json={"filas": [_fila()]},
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["validos"] == 0
    assert datos["rectificaciones"] == 1
    assert datos["resultados"][0]["estado"] == "rectificacion"


def test_masivo_propone_secuencia_consecutiva_para_mismo_sp(cliente_riesgo_masivo):
    _rectificar(cliente_riesgo_masivo, 3)

    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/validar",
        json={"filas": [
            _fila("AR-2026-101", id="a"),
            _fila("AR-2026-102", id="b"),
        ]},
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["validos"] == 2
    assert [fila["numero_anexo"] for fila in datos["resultados"]] == [4, 5]
    assert all(fila["condicion"] == "Nuevo / vigente" for fila in datos["resultados"])


def test_masivo_guarda_como_analisis_y_anexo_y_avanza_secuencia(
    app_riesgo_masivo,
    cliente_riesgo_masivo,
):
    _rectificar(cliente_riesgo_masivo, 3)
    filas = [
        _fila("AR-2026-201", fecha="2026-09-15", id="a"),
        _fila("AR-2026-202", fecha="2026-09-16", id="b"),
    ]

    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/guardar",
        json={"filas": filas, "confirmacion_file_server": True},
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["registrados"] == 2
    assert datos["rechazados"] == 0

    with app_riesgo_masivo.app_context():
        registros = (
            RegistroCoordinacion.query
            .filter_by(tipo="ANALISIS_RIESGO")
            .order_by(RegistroCoordinacion.id.asc())
            .all()
        )
        assert len(registros) == 2
        assert all(registro.origen_registro == "MASIVO" for registro in registros)
        assert len({registro.lote_importacion for registro in registros}) == 1

        analisis = AnalisisRiesgo.query.order_by(AnalisisRiesgo.id.asc()).all()
        assert [item.correlativo for item in analisis] == ["AR-2026-201", "AR-2026-202"]

        anexos = AnexoCoordinacion.query.order_by(AnexoCoordinacion.id.asc()).all()
        assert [item.numero_anexo for item in anexos] == ["4", "5"]
        assert all(item.tipo_anexo == "ANÁLISIS DE RIESGO" for item in anexos)
        assert all(item.es_vencido is False for item in anexos)

        expediente = db.session.get(Expediente, 1)
        assert expediente.anexos_rectificados == 5
        assert registros[0].fecha_recepcion == date(2026, 9, 15)


def test_masivo_historico_conserva_secuencia_vigente(
    app_riesgo_masivo,
    cliente_riesgo_masivo,
):
    _rectificar(cliente_riesgo_masivo, 7)

    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/guardar",
        json={
            "filas": [
                _fila(
                    "AR-HIST-2026-002",
                    fecha="2026-06-10",
                    es_vencido=True,
                    numero_anexo=2,
                )
            ],
            "confirmacion_file_server": True,
        },
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["registrados"] == 1

    with app_riesgo_masivo.app_context():
        expediente = db.session.get(Expediente, 1)
        anexo = AnexoCoordinacion.query.one()
        assert expediente.anexos_rectificados == 7
        assert anexo.numero_anexo == "2"
        assert anexo.es_vencido is True


def test_masivo_detecta_correlativo_repetido_y_sp_inexistente(cliente_riesgo_masivo):
    _rectificar(cliente_riesgo_masivo, 0)
    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/validar",
        json={
            "filas": [
                _fila("AR-DUP-001", id="a"),
                _fila("AR-DUP-001", id="b"),
                _fila("AR-OTRO-001", id="c", no_sp="99999"),
            ]
        },
    )
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["validos"] == 1
    assert "repetido dentro de este lote" in datos["resultados"][1]["mensaje"]
    assert "no existe" in datos["resultados"][2]["mensaje"]


def test_masivo_no_guarda_sin_confirmacion_file_server(
    app_riesgo_masivo,
    cliente_riesgo_masivo,
):
    _rectificar(cliente_riesgo_masivo, 0)
    respuesta = cliente_riesgo_masivo.post(
        "/coordinacion/anexos/analisis-riesgo/masivo/guardar",
        json={"filas": [_fila()], "confirmacion_file_server": False},
    )

    assert respuesta.status_code == 400
    with app_riesgo_masivo.app_context():
        assert RegistroCoordinacion.query.filter_by(tipo="ANALISIS_RIESGO").count() == 0
