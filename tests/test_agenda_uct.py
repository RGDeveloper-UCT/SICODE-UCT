"""Cobertura de roles, asignación colaborativa, avisos y cumpleaños de Agenda UCT."""
from datetime import datetime, timedelta
import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.usuario import Usuario
from app.models.agenda import AgendaActividad, AgendaNotificacion


@pytest.fixture
def sistema():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        for nombre, rol in [("uno", "usuario_autorizado"), ("dos", "usuario_autorizado"),
                            ("tres", "usuario_autorizado"), ("visor", "visor")]:
            persona = Usuario(
                nombre=nombre.title(), usuario=nombre, correo=nombre+"@uct.test",
                password_hash=generate_password_hash("Prueba1234", method="pbkdf2:sha256"),
                rol=rol, activo=True, debe_cambiar_password=False,
            )
            db.session.add(persona)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def cliente(app, nombre):
    c = app.test_client()
    r = c.post("/login", data={"usuario": nombre, "password": "Prueba1234"})
    assert r.status_code == 302
    return c


def crear(c, **campos):
    data = {"titulo": "Verificar expediente", "tipo": "tarea",
            "prioridad": "alta", "visibilidad": "equipo", **campos}
    return c.post("/agenda/api/actividades", json=data)


def test_menu_entre_favoritos_y_administracion(sistema):
    c = cliente(sistema, "uno")
    html = c.get("/dashboard").get_data(as_text=True)
    assert 'id="nav-agenda-uct"' in html
    assert html.index('id="nav-favoritos-sicode"') < html.index('id="nav-agenda-uct"')
    assert "agenda_global.js" in html
    assert "css/agenda.css" in html
    assert c.get("/agenda/").status_code == 200


def test_creador_asigna_y_recibe_aviso_de_finalizacion(sistema):
    c1 = cliente(sistema, "uno")
    c2 = cliente(sistema, "dos")
    r = crear(c1, responsable_id=2, participantes=[3])
    assert r.status_code == 201, r.get_data(as_text=True)
    id_ = r.get_json()["actividad"]["id"]
    pendientes = c2.get("/agenda/api/avisos").get_json()["avisos"]
    assert any("Nueva actividad" in n["titulo"] for n in pendientes)
    fin = c2.post(f"/agenda/api/actividades/{id_}/estado", json={"estado":"finalizada"})
    assert fin.status_code == 200, fin.get_data(as_text=True)
    assert fin.get_json()["actividad"]["estado"] == "finalizada"
    a1 = c1.get("/agenda/api/avisos").get_json()["avisos"]
    assert any("finalizada" in n["titulo"] for n in a1)
    with sistema.app_context():
        assert AgendaActividad.query.get(id_).finalizado_en is not None


def test_revision_solo_valida_creador(sistema):
    c1,c2 = cliente(sistema, "uno"),cliente(sistema,"dos")
    id_ = crear(c1, responsable_id=2, requiere_revision=True).get_json()["actividad"]["id"]
    r = c2.post(f"/agenda/api/actividades/{id_}/estado", json={"estado":"finalizada"})
    assert r.get_json()["actividad"]["estado"] == "en_revision"
    r = c1.post(f"/agenda/api/actividades/{id_}/estado", json={"estado":"finalizada"})
    assert r.get_json()["actividad"]["estado"] == "finalizada"


def test_subtareas_y_permisos(sistema):
    c1,c2,c3 = cliente(sistema,"uno"),cliente(sistema,"dos"),cliente(sistema,"tres")
    padre = crear(c1, responsable_id=2, visibilidad="personal").get_json()["actividad"]["id"]
    assert c3.get(f"/agenda/api/actividades/{padre}").status_code == 403
    assert c3.patch(f"/agenda/api/actividades/{padre}", json={"titulo":"Intruso"}).status_code == 403
    sub = crear(c1, titulo="Preparar listado", padre_id=padre, responsable_id=2, visibilidad="personal")
    assert sub.status_code == 201
    assert c2.post(f"/agenda/api/actividades/{padre}/estado", json={"estado":"finalizada"}).status_code == 400
    sid = sub.get_json()["actividad"]["id"]
    assert c2.post(f"/agenda/api/actividades/{sid}/estado",json={"estado":"finalizada"}).status_code==200
    assert c2.post(f"/agenda/api/actividades/{padre}/estado",json={"estado":"finalizada"}).status_code==200


def test_visores_no_crean_tareas(sistema):
    v=cliente(sistema,"visor")
    assert v.get("/agenda/").status_code == 200
    assert crear(v).status_code == 403
    assert v.post("/agenda/api/cumpleanos", json={"dia":10,"mes":5}).status_code == 403


def test_cumpleanos_visibilidad_y_fecha_bisiesta(sistema):
    c1,c2=cliente(sistema,"uno"),cliente(sistema,"dos")
    assert c1.post("/agenda/api/cumpleanos",json={"dia":29,"mes":2,"visible":False}).status_code==200
    assert not c2.get("/agenda/api/cumpleanos").get_json()["cumpleanos"]
    assert len(c1.get("/agenda/api/cumpleanos").get_json()["cumpleanos"]) == 1
    assert c1.post("/agenda/api/cumpleanos",json={"dia":31,"mes":2}).status_code==400
    assert c1.post("/agenda/api/cumpleanos",json={"dia":29,"mes":2,"visible":True}).status_code==200
    assert len(c2.get("/agenda/api/cumpleanos").get_json()["cumpleanos"])==1


def test_avisos_tras_login_una_vez_y_confirmacion(sistema):
    c=cliente(sistema,"uno")
    vencimiento=(datetime.now()+timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r=crear(c, vencimiento=vencimiento, prioridad="alta")
    assert r.status_code==201
    primero=c.get("/agenda/api/avisos/inicio").get_json()["avisos"]
    assert len(primero)==1
    assert primero[0]["prioridad"] in {"alta","media"}
    # Recargar el dashboard NO omite avisos obligatorios pendientes.
    assert len(c.get("/agenda/api/avisos/inicio").get_json()["avisos"]) == 1
    id_=primero[0]["id"]
    assert c.post(f"/agenda/api/avisos/{id_}/leer").status_code==409
    assert c.post(f"/agenda/api/avisos/{id_}/confirmar").status_code==200
    assert not c.get("/agenda/api/avisos") .get_json()["avisos"]
    assert not c.get("/agenda/api/avisos/inicio").get_json()["avisos"]
    with sistema.app_context():
        assert AgendaNotificacion.query.get(id_).confirmada_en is not None


def test_repeticion_semana_y_exportacion(sistema):
    c=cliente(sistema,"uno")
    vence=(datetime.now()+timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    r=crear(c, vencimiento=vence, recurrencia="semanal")
    id_=r.get_json()["actividad"]["id"]
    assert c.post(f"/agenda/api/actividades/{id_}/estado",json={"estado":"finalizada"}).status_code==200
    with sistema.app_context():
        assert AgendaActividad.query.count() == 2
    respuesta=c.get("/agenda/api/reporte.csv")
    assert respuesta.status_code==200
    assert "text/csv" in respuesta.headers["Content-Type"]


def test_detalle_con_enlaces_campos_y_auditoria_del_actor(sistema):
    """Los eventos y tareas conservan el enlace y los metadatos completos."""
    from app.models.bitacora import Bitacora

    c = cliente(sistema, "uno")
    enlace = "https://drive.google.com/drive/folders/ejemplo123"
    r = crear(
        c, titulo="Reunión de validación", tipo="evento",
        descripcion="Material de apoyo:\nhttps://drive.google.com/file/d/referencia/view",
        lugar=enlace, modalidad="virtual", referencia_sp="SP-001",
        inicio="2099-10-26T08:00", vencimiento="2099-10-28T16:00",
        todo_el_dia=True, requiere_revision=True, visibilidad="equipo",
        recurrencia="ninguna", participantes=[2],
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    id_ = r.get_json()["actividad"]["id"]

    detalle = c.get(f"/agenda/api/actividades/{id_}")
    assert detalle.status_code == 200
    datos = detalle.get_json()
    actividad = datos["actividad"]
    assert actividad["lugar"] == enlace
    assert "drive.google.com/file/" in actividad["descripcion"]
    for campo in ("tipo", "titulo", "descripcion", "prioridad", "estado", "visibilidad",
                  "creado_por", "responsable", "inicio", "vencimiento", "todo_el_dia",
                  "lugar", "modalidad", "recurrencia", "requiere_revision",
                  "referencia_sp", "participantes", "progreso"):
        assert campo in actividad, campo
    assert actividad["tipo"] == "evento"
    assert actividad["todo_el_dia"] is True
    assert actividad["requiere_revision"] is True
    assert actividad["modalidad"] == "virtual"
    assert actividad["referencia_sp"] == "SP-001"
    assert any(p["usuario_id"] == 2 for p in datos["asistencias"])

    nuevo = "https://drive.google.com/drive/folders/actualizado456"
    edicion = c.patch(f"/agenda/api/actividades/{id_}", json={"lugar": nuevo})
    assert edicion.status_code == 200, edicion.get_data(as_text=True)
    assert c.get(f"/agenda/api/actividades/{id_}").get_json()["actividad"]["lugar"] == nuevo
    with sistema.app_context():
        acciones = Bitacora.query.filter_by(accion="AGENDA_LUGAR_ENLACE", entidad_id=str(id_)).all()
        assert len(acciones) == 2
        assert all(a.usuario_id == 1 for a in acciones)
        # La bitácora identifica al autor, pero no replica los enlaces en texto plano.
        assert all("drive.google.com" not in (a.descripcion or "") for a in acciones)


def test_detalle_frontend_incluye_enlaces_y_eventos_multidia(sistema):
    c = cliente(sistema, "uno")
    codigo = c.get("/static/js/agenda.js").get_data(as_text=True)
    assert "function conEnlaces" in codigo
    assert 'rel="noopener noreferrer"' in codigo
    assert 'referrerpolicy="no-referrer"' in codigo
    assert "conEnlaces(x.descripcion)" in codigo
    assert "conEnlaces(x.lugar)" in codigo
    assert "conEnlaces(n.texto)" in codigo
    assert "ocupaDia(x, fechaISO)" in codigo
    assert "fechaFin(x) >= inicioMes" in codigo
    assert "Requiere revisión del creador" in codigo
    assert "Todo el día" in codigo


def test_papelera_tarea_no_se_borra_y_se_restaura_con_datos(sistema):
    from app.models.bitacora import Bitacora

    c = cliente(sistema, "uno")
    creada = crear(c, titulo="Tarea reversible", descripcion="Observación de control",
                  referencia_sp="SP-312", participantes=[2])
    assert creada.status_code == 201
    id_ = creada.get_json()["actividad"]["id"]
    assert c.post(f"/agenda/api/actividades/{id_}/estado",
                  json={"estado": "en_proceso"}).status_code == 200
    assert c.post(f"/agenda/api/actividades/{id_}/comentarios",
                  json={"texto": "Avance conservado"}).status_code == 201

    eliminada = c.post(f"/agenda/api/actividades/{id_}/eliminar")
    assert eliminada.status_code == 200
    assert eliminada.get_json()["actividad"]["eliminado_en"]
    assert eliminada.get_json()["actividad"]["eliminado_por"] == "Uno"
    assert id_ not in [a["id"] for a in c.get("/agenda/api/actividades").get_json()["actividades"]]
    assert "Tarea reversible" not in c.get("/agenda/api/reporte.csv").get_data(as_text=True)
    assert c.get(f"/agenda/api/actividades/{id_}").status_code == 404
    assert c.patch(f"/agenda/api/actividades/{id_}", json={"titulo": "Otro"}).status_code == 404
    assert c.post(f"/agenda/api/actividades/{id_}/estado", json={"estado": "finalizada"}).status_code == 404
    assert c.post(f"/agenda/api/actividades/{id_}/comentarios", json={"texto": "Intruso"}).status_code == 404
    assert c.post(f"/agenda/api/actividades/{id_}/eliminar").status_code == 404

    papelera = c.get("/agenda/api/eliminadas").get_json()["actividades"]
    assert any(a["id"] == id_ for a in papelera)
    recuperada = c.post(f"/agenda/api/actividades/{id_}/restaurar")
    assert recuperada.status_code == 200
    item = recuperada.get_json()["actividad"]
    assert item["estado"] == "en_proceso"
    assert item["referencia_sp"] == "SP-312"
    assert item["descripcion"] == "Observación de control"
    assert item["participantes"] == [2]
    assert item["eliminado_en"] is None
    assert c.post(f"/agenda/api/actividades/{id_}/restaurar").status_code == 409
    assert any(a["id"] == id_ for a in c.get("/agenda/api/actividades").get_json()["actividades"])
    assert "Avance conservado" in str(c.get(f"/agenda/api/actividades/{id_}").get_json()["comentarios"])
    with sistema.app_context():
        assert db.session.get(AgendaActividad, id_) is not None
        acciones = [a.accion for a in Bitacora.query.filter_by(entidad="AgendaActividad", entidad_id=str(id_)).all()]
        assert "AGENDA_ELIMINAR" in acciones
        assert "AGENDA_RESTAURAR" in acciones


def test_papelera_evento_privado_permisos_y_visor(sistema):
    c1, c2, c3, visor = (cliente(sistema, u) for u in ("uno", "dos", "tres", "visor"))
    evento = crear(c1, titulo="Evento privado recuperable", tipo="evento",
                   visibilidad="personal", responsable_id=2, lugar="Auditorio")
    id_ = evento.get_json()["actividad"]["id"]
    ruta = f"/agenda/api/actividades/{id_}"
    assert c3.post(ruta + "/eliminar").status_code == 403
    assert visor.post(ruta + "/eliminar").status_code == 403
    assert c2.post(ruta + "/eliminar").status_code == 200
    assert not c3.get("/agenda/api/eliminadas").get_json()["actividades"]
    assert not visor.get("/agenda/api/eliminadas").get_json()["actividades"]
    assert c3.post(ruta + "/restaurar").status_code == 403
    assert visor.post(ruta + "/restaurar").status_code == 403
    assert c2.post(ruta + "/restaurar").status_code == 200
    assert c1.get(ruta).get_json()["actividad"]["lugar"] == "Auditorio"


def test_papelera_subtareas_restauracion_selectiva(sistema):
    c = cliente(sistema, "uno")
    padre = crear(c, titulo="Tarea principal").get_json()["actividad"]["id"]
    activa = crear(c, titulo="Subtarea activa", padre_id=padre).get_json()["actividad"]["id"]
    previa = crear(c, titulo="Subtarea eliminada antes", padre_id=padre).get_json()["actividad"]["id"]
    assert c.post(f"/agenda/api/actividades/{previa}/eliminar").status_code == 200
    assert c.post(f"/agenda/api/actividades/{padre}/eliminar").status_code == 200
    assert c.post(f"/agenda/api/actividades/{activa}/restaurar").status_code == 409
    listado = c.get("/agenda/api/eliminadas").get_json()["actividades"]
    assert [x["id"] for x in listado] == [padre]
    assert c.post(f"/agenda/api/actividades/{padre}/restaurar").status_code == 200
    activos = {a["id"] for a in c.get("/agenda/api/actividades").get_json()["actividades"]}
    assert {padre, activa} <= activos
    assert previa not in activos
    assert c.get(f"/agenda/api/actividades/{padre}").get_json()["subtareas"][0]["id"] == activa
    assert c.post(f"/agenda/api/actividades/{previa}/restaurar").status_code == 200


def test_papelera_no_genera_alertas_de_plazo_y_aparece_en_interfaz(sistema):
    c = cliente(sistema, "uno")
    vence = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    id_ = crear(c, titulo="Tarea sin alerta luego de eliminar",
                vencimiento=vence, prioridad="alta").get_json()["actividad"]["id"]
    assert c.post(f"/agenda/api/actividades/{id_}/eliminar").status_code == 200
    assert not any("Tarea sin alerta" in aviso["titulo"]
                   for aviso in c.get("/agenda/api/avisos").get_json()["avisos"])
    html = c.get("/agenda/").get_data(as_text=True)
    script = c.get("/static/js/agenda.js").get_data(as_text=True)
    assert 'id="agenda-papelera"' in html
    assert 'id="agenda-eliminadas-lista"' in html
    assert 'data-agenda-eliminar' in script
    assert 'data-agenda-restaurar' in script
