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
    assert not c.get("/agenda/api/avisos/inicio").get_json()["avisos"]
    id_=primero[0]["id"]
    assert c.post(f"/agenda/api/avisos/{id_}/leer").status_code==409
    assert c.post(f"/agenda/api/avisos/{id_}/confirmar").status_code==200
    assert not c.get("/agenda/api/avisos") .get_json()["avisos"]
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
