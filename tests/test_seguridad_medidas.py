"""Pruebas de modalidad de medidas CERT: misma secuencia BSI y formulario/PDF distintos."""
from io import BytesIO

from openpyxl import load_workbook
from pypdf import PdfReader

from app import db
from app.models.seguridad_operativa import BoletaSeguridadTI
from app.services.checklist_medidas_seguridad import (
    VERSION_MEDIDAS, GRUPOS_MEDIDAS, plantilla_medidas, validar_medidas,
)
from test_seguridad_operativa_bsi import entorno


def _crear(client, equipo_id, url="/seguridad-informatica/boletas/medidas/nueva"):
    r = client.post(url, data={"equipo_id": equipo_id})
    assert r.status_code == 302
    return BoletaSeguridadTI.query.order_by(BoletaSeguridadTI.id.desc()).first()


def test_enlace_de_medidas_debajo_del_lote_cert_y_formulario_separado(entorno):
    client, equipo_id = entorno
    pagina = client.get("/seguridad-informatica/boletas/nueva")
    assert pagina.status_code == 200
    data = pagina.get_data(as_text=True)
    assert data.index("Incluir las 19 vulnerabilidades del CERT") < data.index(
        "Crear boleta de Medidas Prioritarias y Temporales"
    )
    nuevo = client.get(f"/seguridad-informatica/boletas/medidas/nueva?equipo_id={equipo_id}")
    assert nuevo.status_code == 200
    assert b'Medidas prioritarias y temporales' in nuevo.data
    assert f'value="{equipo_id}"'.encode() in nuevo.data


def test_medidas_tienen_apartados_41_y_42_de_los_tres_informes():
    assert VERSION_MEDIDAS == 1
    assert len(GRUPOS_MEDIDAS) == 6
    filas = plantilla_medidas()
    assert len(filas) == 30
    assert len({f["codigo"] for f in filas}) == 30
    for tec in ("chrome", "java_python", "php"):
        assert {f["grupo"].rsplit("_", 1)[-1] for f in filas if f["tecnologia"] == tec} == {"41", "42"}
    assert all(f["resultado"] == "PENDIENTE" for f in filas)
    assert any("session.upload_progress.enabled" in f["actividad"] for f in filas)
    assert any("archivos" in f["actividad"].lower() for f in filas)


def test_correlativo_bsi_es_unico_compartido_y_rutas_distintas(entorno):
    client, equipo_id = entorno
    integral_r = client.post("/seguridad-informatica/boletas/nueva", data={"equipo_id": equipo_id})
    assert integral_r.status_code == 302
    integral = BoletaSeguridadTI.query.order_by(BoletaSeguridadTI.id).first()
    medidas = _crear(client, equipo_id)
    assert integral.tipo_boleta == "INTEGRAL"
    assert medidas.tipo_boleta == "MEDIDAS"
    assert integral.numero == "BSI-000001"
    assert medidas.numero == "BSI-000002"
    assert len(medidas.checklist) == 30
    assert medidas.checklist_version == 1
    assert len(integral.checklist) > 30
    assert client.get(f"/seguridad-informatica/boletas/{medidas.id}/editar").status_code == 302
    assert client.get(f"/seguridad-informatica/boletas/{integral.id}/medidas/editar").status_code == 404
    listado = client.get("/seguridad-informatica/boletas")
    assert listado.status_code == 200
    assert "Medidas prioritarias y temporales" in listado.get_data(as_text=True)


def test_medidas_sin_software_no_aplican_pero_instalado_exige_verificacion():
    base = plantilla_medidas()
    datos = [{"codigo": f["codigo"], "resultado": "PENDIENTE", "observacion": ""} for f in base]
    versiones = {"instalado_chrome": "NO", "instalado_java": "NO",
                 "instalado_python": "NO", "instalado_php": "SI"}
    salidas = validar_medidas(datos, base, versiones)
    assert all(f["resultado"] == "NO_APLICA" for f in salidas if f["tecnologia"] in ("chrome", "java_python"))
    assert all(f["resultado"] == "PENDIENTE" for f in salidas if f["tecnologia"] == "php")
    datos = [{"codigo": f["codigo"], "resultado": "CUMPLE", "observacion": ""} for f in base]
    versiones = {"instalado_chrome": "NO", "instalado_java": "SI",
                 "instalado_python": "NO", "instalado_php": "SI"}
    salidas = validar_medidas(datos, base, versiones, finalizar=True)
    assert all(f["resultado"] == "CUMPLE" for f in salidas if f["tecnologia"] == "java_python")


def test_guarda_cierra_pdf_diferenciado_y_xlsx(entorno):
    client, equipo_id = entorno
    b = _crear(client, equipo_id)
    editor = client.get(f"/seguridad-informatica/boletas/{b.id}/medidas/editar")
    assert editor.status_code == 200
    assert b'4.1 Acciones prioritarias' in editor.data
    assert b'4.2 Medidas temporales' in editor.data
    data = {
        "accion": "guardar", "diagnostico": "Inspección CERT octubre 2026",
        "acciones": "Actualización revisada por técnico responsable",
        "instalado_chrome": "SI", "version_chrome": "156.0.8078.80",
        "instalado_java": "NO", "instalado_python": "NO", "instalado_php": "NO",
        "resultado_final": "OPERATIVO",
    }
    data.update({"resultado_" + f["codigo"]: "CUMPLE" for f in b.checklist})
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/medidas/editar", data=data).status_code == 302
    db.session.refresh(b)
    assert b.estado == "BORRADOR"
    assert sum(f["resultado"] == "NO_APLICA" for f in b.checklist if f["tecnologia"] in ("java_python", "php")) > 0
    data["accion"] = "finalizar"
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/medidas/editar", data=data).status_code == 200
    assert b.estado == "BORRADOR"
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/reloj", data={"accion": "iniciar"}).status_code == 302
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/medidas/editar", data=data).status_code == 302
    db.session.refresh(b)
    assert b.estado == "FINALIZADO"
    assert b.tipo_boleta == "MEDIDAS"
    pdf = client.get(f"/seguridad-informatica/boletas/{b.id}/pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF-")
    texto = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf.data)).pages)
    assert b.numero in texto
    assert "MEDIDAS PRIORITARIAS Y TEMPORALES" in texto
    assert "Chrome" in texto and "PHP" in texto
    libro = load_workbook(BytesIO(client.get("/seguridad-informatica/boletas/informe.xlsx").data), read_only=True)
    assert libro["Boletas"]["B1"].value == "Modalidad"
    assert "Medidas prioritarias y temporales" in libro["Boletas"]["B2"].value
    assert client.get(f"/seguridad-informatica/boletas/{b.id}/medidas/editar").status_code == 302


def test_anular_medidas_conserva_folio_y_no_exporta(entorno):
    client, equipo_id = entorno
    b = _crear(client, equipo_id)
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/eliminar",
                       data={"motivo": "La computadora elegida no era la correcta"}).status_code == 302
    db.session.refresh(b)
    assert b.estado == "ANULADA"
    assert client.get(f"/seguridad-informatica/boletas/{b.id}/pdf").status_code == 302
    assert client.get(f"/seguridad-informatica/boletas/{b.id}/medidas/editar").status_code == 302
    nuevo = _crear(client, equipo_id)
    assert nuevo.numero != b.numero


def test_visor_no_puede_crear_medidas(entorno):
    client, equipo_id = entorno
    assert client.get("/__login_bsi_test?visor=1").status_code == 200
    assert client.get("/seguridad-informatica/boletas/medidas/nueva").status_code == 403
    assert client.post("/seguridad-informatica/boletas/medidas/nueva",
                       data={"equipo_id": equipo_id}).status_code == 403
