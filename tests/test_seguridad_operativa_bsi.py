"""Pruebas funcionales del catálogo MINGOB, informes PDF/DOCX y boletas BSI.

Solo emplean SQLite temporal; tests/conftest.py impide probar PostgreSQL productivo.
"""
from io import BytesIO
from zipfile import ZipFile

import pytest
from flask_login import login_user
from pypdf import PdfReader
from openpyxl import load_workbook

from app import create_app, db
from app.models.usuario import Usuario
from app.models.equipo_institucional import EquipoInstitucional
from app.models.seguridad_operativa import InformeSeguridadTI, VulnerabilidadTI, BoletaSeguridadTI
from app.services.catalogo_informes_mingob_2026 import cargar_catalogo_octubre_2026, AVISOS
from app.services.checklist_seguridad import plantilla, VERSION


@pytest.fixture
def entorno():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    @app.get("/__login_bsi_test")
    def login_bsi_test():
        viewer = "visor" in __import__("flask").request.args
        nombre = "visor-bsi" if viewer else "tecnico-bsi"
        login_user(Usuario.query.filter_by(usuario=nombre).one(), fresh=True)
        return "ok"

    with app.app_context():
        db.create_all()
        admin = Usuario(nombre="Técnico BSI", usuario="tecnico-bsi",
                        password_hash="temporal", rol=Usuario.ROL_ADMINISTRADOR, activo=True)
        admin.debe_cambiar_password = False
        visor = Usuario(nombre="Visor BSI", usuario="visor-bsi",
                        password_hash="temporal", rol=Usuario.ROL_VISOR, activo=True)
        visor.debe_cambiar_password = False
        db.session.add_all((admin, visor))
        db.session.flush()
        equipo = EquipoInstitucional(codigo="SICOIN-BSI-1", nombre="PC de ensayo",
                                     tipo="COMPUTADORA", creado_por_id=admin.id)
        db.session.add(equipo)
        db.session.commit()
        try:
            client = app.test_client()
            assert client.get("/__login_bsi_test").status_code == 200
            yield client, equipo.id
        finally:
            db.session.remove()
            db.drop_all()


def _docx_prueba():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zipfile:
        zipfile.writestr("[Content_Types].xml", "<Types />")
        zipfile.writestr("word/document.xml", "<document />")
    buffer.seek(0)
    return buffer


def _registrar_informe(client, cves, nombre="reporte.docx", archivo=None):
    return client.post("/seguridad-informatica/informes/nuevo", data={
        "titulo": "Aviso conjunto del CERT MINGOB",
        "emisor": "Dirección de Informática MINGOB",
        "tecnologia": "JAVA_PYTHON",
        "prioridad": "alta",
        "fecha_informe": "2026-10-30",
        "cves": cves,
        "archivo": (archivo or _docx_prueba(), nombre),
    }, content_type="multipart/form-data")


def test_catalogo_19_cve_documentados_sin_duplicados(entorno):
    client, _ = entorno
    assert sum(map(len, AVISOS.values())) == 19
    resultado = cargar_catalogo_octubre_2026()
    assert resultado["nuevos"] == 19
    assert VulnerabilidadTI.query.count() == 19
    assert cargar_catalogo_octubre_2026()["nuevos"] == 0
    assert VulnerabilidadTI.query.count() == 19
    assert VulnerabilidadTI.query.filter_by(cve="CVE-2026-91395").one().severidad == "MEDIA"
    assert VulnerabilidadTI.query.filter_by(cve="CVE-2026-102633").one().producto == "PYTHON"
    assert VulnerabilidadTI.query.filter_by(cve="CVE-2026-109618").one().explotada is False
    assert b"Seguridad Inform" in client.get("/seguridad-informatica/").data
    assert b"Informes" in client.get("/seguridad-informatica/informes").data


def test_informe_multi_cve_docx_y_descarga_autenticada(entorno):
    client, _ = entorno
    cargar_catalogo_octubre_2026()
    response = _registrar_informe(client, "CVE-2026-91484, CVE-2026-115557")
    assert response.status_code == 302
    informe = InformeSeguridadTI.query.one()
    assert len(informe.vulnerabilidades) == 2
    assert VulnerabilidadTI.query.count() == 19
    descarga = client.get(f"/seguridad-informatica/informes/{informe.id}/archivo")
    assert descarga.status_code == 200
    assert descarga.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert descarga.data.startswith(b"PK")
    # Cualquier intento de duplicar el mismo archivo se rechaza sin nueva notificación.
    assert _registrar_informe(client, "CVE-2026-118306").status_code == 200
    assert InformeSeguridadTI.query.count() == 1


def test_informe_con_identificadores_invalidos_no_se_guarda(entorno):
    client, _ = entorno
    assert _registrar_informe(client, "CVE-2026-91484, inventado").status_code == 200
    assert InformeSeguridadTI.query.count() == 0
    assert VulnerabilidadTI.query.count() == 0


def test_informe_php_admite_pdf(entorno):
    client, _ = entorno
    response = _registrar_informe(client, "CVE-2026-109618\nCVE-2026-109619",
                                  "informe.pdf", BytesIO(b"%PDF-1.4\nbody\n%%EOF\n"))
    assert response.status_code == 302
    assert InformeSeguridadTI.query.count() == 1
    assert VulnerabilidadTI.query.count() == 2


def test_checklist_cubre_los_tres_informes():
    actividades = [fila["actividad"].lower() for fila in plantilla()]
    assert VERSION >= 2
    assert any("chrome" in nombre for nombre in actividades)
    assert any("java" in nombre for nombre in actividades)
    assert any("python" in nombre for nombre in actividades)
    assert any("php" in nombre for nombre in actividades)
    assert any("antivirus" in nombre for nombre in actividades)
    assert any("firewall" in nombre for nombre in actividades)


def test_boleta_con_cve_cierre_pdf_y_xlsx(entorno):
    client, equipo_id = entorno
    cargar_catalogo_octubre_2026()
    v = VulnerabilidadTI.query.filter_by(cve="CVE-2026-76024").one()
    respuesta = client.post("/seguridad-informatica/boletas/nueva",
                            data={"equipo_id": equipo_id, "vulnerabilidad_ids": str(v.id)})
    assert respuesta.status_code == 302
    b = BoletaSeguridadTI.query.one()
    assert b.numero == "BSI-000001"
    assert b.equipo_id == equipo_id
    assert len([f for f in b.checklist if f["codigo"].startswith("cve_")]) == 1
    assert EquipoInstitucional.query.count() == 1
    assert client.get(f"/seguridad-informatica/boletas/{b.id}/pdf").status_code == 302

    form = {"accion": "finalizar", "resultado_final": "OPERATIVO",
            "version_sistema": "Windows 11 24H2", "version_chrome": "156.0.8078.80",
            "instalado_chrome": "SI"}
    form.update({"resultado_" + f["codigo"]: "CUMPLE" for f in b.checklist})
    # Un cierre sin iniciar cronómetro debe rechazarse.
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/editar", data=form).status_code == 200
    assert b.estado == "BORRADOR"
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/reloj",
                       data={"accion": "iniciar"}).status_code == 302
    form["resultado_cve_" + str(v.id)] = "NO_CUMPLE"
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/editar", data=form).status_code == 200
    assert b.estado != "FINALIZADO"
    form["observacion_cve_" + str(v.id)] = "Chrome se actualizará en siguiente ventana."
    form["resultado_final"] = "CON_HALLAZGOS"
    assert client.post(f"/seguridad-informatica/boletas/{b.id}/editar", data=form).status_code == 302
    db.session.refresh(b)
    assert b.estado == "FINALIZADO"
    assert b.versiones["chrome"] == "156.0.8078.80"
    pdf = client.get(f"/seguridad-informatica/boletas/{b.id}/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-")
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf.data)).pages)
    assert b.numero in texto
    assert "CVE-2026-76024" in texto
    assert "156.0.8078.80" in texto
    assert client.get(f"/seguridad-informatica/boletas/{b.id}/editar").status_code == 302

    excel = client.get("/seguridad-informatica/boletas/informe.xlsx")
    assert excel.status_code == 200
    libro = load_workbook(BytesIO(excel.data), read_only=True)
    assert set(libro.sheetnames) == {"Boletas", "Hallazgos", "Por equipo"}
    assert libro["Boletas"].max_row == 2
    assert libro["Hallazgos"].max_row == 2
    assert libro["Por equipo"].max_row == 2


def test_visor_puede_consultar_pero_no_registrar(entorno):
    client, _ = entorno
    assert client.get("/__login_bsi_test?visor=1").status_code == 200
    assert client.get("/seguridad-informatica/").status_code == 200
    assert client.get("/seguridad-informatica/informes").status_code == 200
    assert client.get("/seguridad-informatica/boletas/nueva").status_code == 403
    assert client.post("/seguridad-informatica/informes/nuevo", data={}).status_code == 403
