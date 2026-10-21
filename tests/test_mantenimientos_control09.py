"""Pruebas del Control 09. Usan SQLite temporal gracias a tests/conftest.py."""
import pytest
from flask_login import login_user
from app import create_app, db
from app.models.usuario import Usuario
from app.models.equipo_institucional import EquipoInstitucional
from app.models.mantenimiento_equipo import MantenimientoEquipo
from app.services.checklist_mantenimiento import plantilla, validar_checklist, validar_cierre


@pytest.fixture
def entorno():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    @app.get("/__login_mantenimiento_test")
    def login_mantenimiento_test():
        login_user(Usuario.query.filter_by(usuario="tecnico-maint-test").one(), fresh=True)
        return "ok"
    with app.app_context():
        db.create_all()
        user = Usuario(nombre="Técnico Pruebas", usuario="tecnico-maint-test",
                       password_hash="temporal", rol=Usuario.ROL_ADMINISTRADOR, activo=True)
        user.debe_cambiar_password = False
        db.session.add(user)
        db.session.flush()
        e = EquipoInstitucional(codigo="SICOIN-MNT-01", tipo="COMPUTADORA",
                                nombre="Computadora de ensayo", creado_por_id=user.id)
        db.session.add(e)
        db.session.commit()
        try:
            client = app.test_client()
            assert client.get("/__login_mantenimiento_test").status_code == 200
            yield client, user.id, e.id
        finally:
            db.session.remove()
            db.drop_all()


def test_checklist_no_incluye_los_dos_controles_retirados():
    labels = [f["actividad"] for f in plantilla()]
    assert len(labels) == 39
    assert "Archivos de correo" not in labels
    assert "Ausencia de extensiones no autorizadas" not in labels
    assert "Extensiones de navegador permitidas" in labels
    assert "Escritorio" in labels


def test_checklist_rechaza_no_cumple_sin_descripcion():
    datos = plantilla()
    datos[0]["resultado"] = "NO_CUMPLE"
    with pytest.raises(ValueError):
        validar_checklist(datos)
    datos[0]["observacion"] = "Se detectó un respaldo incompleto."
    assert validar_checklist(datos)[0]["resultado"] == "NO_CUMPLE"
    with pytest.raises(ValueError):
        validar_cierre(datos)


def test_alta_reutiliza_equipo_y_generacion_pdf(entorno):
    client, _uid, equipo_id = entorno
    r = client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                    data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    assert r.status_code == 302
    m = MantenimientoEquipo.query.one()
    assert m.equipo_id == equipo_id
    assert EquipoInstitucional.query.count() == 1
    assert len(m.checklist) == 39
    assert client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/pdf").status_code == 302

    client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/reloj", data={"accion": "iniciar"})
    client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/reloj", data={"accion": "pausar"})
    db.session.refresh(m)
    assert m.iniciado_en is not None
    assert m.tramo_iniciado_en is None

    form = {"diagnostico": "Revisión inicial", "trabajo_realizado": "Mantenimiento ejecutado",
            "estado_final": "OPERATIVO", "accion": "finalizar"}
    form.update({"resultado_" + fila["codigo"]: "CUMPLE" for fila in m.checklist})
    r = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar", data=form)
    assert r.status_code == 302
    db.session.refresh(m)
    assert m.estado == "FINALIZADO"
    pdf = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")
    assert client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar").status_code == 302


def test_registro_rechaza_equipo_inexistente(entorno):
    client, _uid, _equipo_id = entorno
    r = client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                    data={"equipo_id": "999999", "tipo": "PREVENTIVO"})
    assert r.status_code == 200
    assert MantenimientoEquipo.query.count() == 0


def test_cierre_incompleto_no_se_guarda(entorno):
    client, _uid, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    r = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar",
                    data={"accion": "finalizar", "trabajo_realizado": "Trabajo", "estado_final": "OPERATIVO"})
    assert r.status_code == 200
    db.session.refresh(m)
    assert m.estado == "BORRADOR"


def test_interfaz_secciones_y_opciones_directas(entorno):
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    html = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar").get_data(as_text=True)
    assert 'class="mnt-seccion"' in html
    assert 'type="radio"' in html
    assert 'name="respaldo_mb"' in html
    assert 'name="resultado_respaldo_0"' in html
    assert 'name="resultado_respaldo_0" value="NO_CUMPLE"' in html
    assert '<select name="resultado_respaldo_0"' not in html


def test_resumen_y_respaldo_en_pdf(entorno):
    from io import BytesIO
    from pypdf import PdfReader
    from app.services.resumen_mantenimiento import resumen_trabajo
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/reloj",
                data={"accion": "iniciar"})
    data = {"accion": "finalizar", "trabajo_realizado": "",
            "estado_final": "OBSERVACIONES", "respaldo_mb": "2048.50"}
    data.update({"resultado_" + f["codigo"]: "CUMPLE" for f in m.checklist})
    data["resultado_seguridad_0"] = "NO_CUMPLE"
    data["observacion_seguridad_0"] = "Extensión fuera de la lista autorizada"
    resp = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar", data=data)
    assert resp.status_code == 302
    db.session.refresh(m)
    assert m.estado == "FINALIZADO"
    assert str(m.respaldo_mb) == "2048.50"
    resumen = resumen_trabajo(m.checklist, m.respaldo_mb)
    assert "Extensiones de navegador permitidas" in resumen
    assert "CONTROLES QUE NO CUMPLIERON" in resumen
    assert "2048.50 MB" in resumen
    pdf = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/pdf")
    assert pdf.status_code == 200
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf.data)).pages)
    assert "2048.50 MB" in texto
    assert "Extensión fuera de la lista autorizada" in texto


def test_tamano_respaldo_invalido_rechazado(entorno):
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    for valor in ("-1", "abc", "NaN", "1.999"):
        response = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar",
                               data={"accion": "guardar", "respaldo_mb": valor})
        assert response.status_code == 200
        db.session.refresh(m)
        assert m.respaldo_mb is None
