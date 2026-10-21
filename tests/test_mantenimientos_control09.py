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
    assert len(labels) == 41
    assert "Archivos de correo" not in labels
    assert "Ausencia de extensiones no autorizadas" not in labels
    assert "Extensiones de navegador permitidas" in labels
    assert "Escritorio" in labels
    assert "Verificación del funcionamiento del antivirus" in labels
    assert "Verificación de los controles del Firewall de Windows" in labels
    assert plantilla()[-1]["grupo"] == "final"


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
    assert len(m.checklist) == 41
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
    assert 'name="respaldo_gb"' in html
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
            "estado_final": "OBSERVACIONES", "respaldo_gb": "48.75"}
    data.update({"resultado_" + f["codigo"]: "CUMPLE" for f in m.checklist})
    data["resultado_seguridad_0"] = "NO_CUMPLE"
    data["observacion_seguridad_0"] = "Extensión fuera de la lista autorizada"
    resp = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar", data=data)
    assert resp.status_code == 302
    db.session.refresh(m)
    assert m.estado == "FINALIZADO"
    assert str(m.respaldo_gb) == "48.75"
    resumen = resumen_trabajo(m.checklist, m.respaldo_gb)
    assert "Extensiones de navegador permitidas" in resumen
    assert "CONTROLES QUE NO CUMPLIERON" in resumen
    pdf = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/pdf")
    assert pdf.status_code == 200
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf.data)).pages)
    assert "48.75 GB" in texto
    assert len(PdfReader(BytesIO(pdf.data)).pages) == 1
    assert "Extensión fuera de la lista autorizada" in texto


def test_tamano_respaldo_invalido_rechazado(entorno):
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo",
                data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    for valor in ("-1", "abc", "NaN", "1.999"):
        response = client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar",
                               data={"accion": "guardar", "respaldo_gb": valor})
        assert response.status_code == 200
        db.session.refresh(m)
        assert m.respaldo_gb is None


def test_tamano_respaldo_al_final_de_seccion(entorno):
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo", data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    html = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar").get_data(as_text=True)
    assert html.index("Confirmación de respaldo en repositorio autorizado") < html.index('name="respaldo_gb"') < html.index("Mantenimiento de hardware")
    assert 'name="respaldo_mb"' not in html


def test_actualizar_borrador_agrega_controles_sin_perder_resultados():
    from app.services.checklist_mantenimiento import actualizar_checklist_pendiente
    anterior = [f for f in plantilla() if f["actividad"] not in {
        "Verificación del funcionamiento del antivirus",
        "Verificación de los controles del Firewall de Windows"}]
    anterior[0]["resultado"] = "CUMPLE"
    actualizado = actualizar_checklist_pendiente(anterior)
    assert len(actualizado) == 41
    assert actualizado[0]["resultado"] == "CUMPLE"
    assert next(f for f in actualizado if f["actividad"] == "Verificación del funcionamiento del antivirus")["grupo"] == "software"
    assert next(f for f in actualizado if f["actividad"] == "Verificación de los controles del Firewall de Windows")["grupo"] == "seguridad"
    assert actualizado == actualizar_checklist_pendiente(actualizado)


def test_nuevos_controles_aparecen_en_formulario_y_pdf(entorno):
    from io import BytesIO
    from pypdf import PdfReader
    client, _, equipo_id = entorno
    client.post("/coordinacion/seguridad/mantenimientos/nuevo", data={"equipo_id": str(equipo_id), "tipo": "PREVENTIVO"})
    m = MantenimientoEquipo.query.one()
    html = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar").get_data(as_text=True)
    assert "Verificación del funcionamiento del antivirus" in html
    assert "Verificación de los controles del Firewall de Windows" in html
    client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/reloj", data={"accion": "iniciar"})
    form = {"accion": "finalizar", "estado_final": "OPERATIVO"}
    form.update({"resultado_" + f["codigo"]: "CUMPLE" for f in m.checklist})
    assert client.post(f"/coordinacion/seguridad/mantenimientos/{m.id}/editar", data=form).status_code == 302
    pdf = client.get(f"/coordinacion/seguridad/mantenimientos/{m.id}/pdf")
    assert pdf.status_code == 200
    texto = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf.data)).pages)
    assert "funcionamiento del antivirus" in texto
    assert "Firewall de Windows" in texto


def test_boleta_usa_datos_maestros_del_equipo_vinculado(entorno):
    from app.forms.soporte_tecnico_form import SoporteTecnicoForm
    from app.routes.soporte_tecnico import _aplicar_formulario
    from app.models.soporte_tecnico import ServicioSoporteTecnico
    from datetime import datetime
    client, usuario_id, equipo_id = entorno
    equipo = db.session.get(EquipoInstitucional, equipo_id)
    equipo.marca = "Dell"
    equipo.modelo = "OptiPlex"
    equipo.serie = "SERIE-CANONICA"
    equipo.ip_estatica = "192.0.2.10"
    db.session.commit()
    with client.application.test_request_context("/"):
        formulario = SoporteTecnicoForm(data={
            "equipo_institucional_id": equipo_id,
            "personal_institucional_id": 0,
            "fecha_hora_solicitud": datetime(2026, 10, 21, 10, 0),
            "usuario_solicitante": "Usuario de prueba",
            "coordinacion_area": "Área de prueba",
            "tecnico_asignado": "Técnico de prueba",
            "descripcion_solicitud": "Revisión",
            "tipos_servicio": ["HARDWARE"],
            "estado_final": "PENDIENTE",
            "seguimiento": "NO",
            "inventario": "SICOIN-EQUIVOCADO",
            "numero_serie": "SERIE-EQUIVOCADA",
            "marca_modelo": "Marca incorrecta",
            "tipo_equipo": "LAPTOP",
        })
        boleta = ServicioSoporteTecnico()
        _aplicar_formulario(boleta, formulario)
        assert boleta.equipo_institucional_id == equipo_id
        assert boleta.inventario == equipo.codigo
        assert boleta.numero_serie == "SERIE-CANONICA"
        assert boleta.marca_modelo == "Dell OptiPlex"
        assert boleta.tipo_equipo == "PC"
        assert boleta.ip_nombre_equipo == "192.0.2.10"


def test_vinculacion_inventario_en_formulario_de_boleta(entorno):
    client, _, _ = entorno
    html = client.get("/coordinacion/soporte-tecnico/nuevo").get_data(as_text=True)
    assert 'id="buscar_equipo_inventario"' in html
    assert 'data-sicoin="SICOIN-MNT-01"' in html
    assert "Abrir Inventario Tecnológico" in html
    assert "aplicarEquipo()" in html
