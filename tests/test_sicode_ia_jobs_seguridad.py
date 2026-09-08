import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.usuario import Usuario


@pytest.fixture()
def app_jobs():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="Usuario IA",
            usuario="ia-user",
            correo="ia-user@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="usuario_autorizado",
            activo=True,
        )
        db.session.add(usuario)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login(app):
    cliente = app.test_client()
    respuesta = cliente.post(
        "/login",
        data={"usuario": "ia-user", "password": "Password123"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 302
    return cliente


def test_estado_fallido_no_expone_traceback_interno(app_jobs, monkeypatch):
    import app.routes.sicode_ia_jobs as modulo

    class Estado:
        value = "failed"

    class JobFalso:
        id = "job-seguro"
        meta = {"usuario_id": 1, "fase": "failed", "porcentaje": 0}
        exc_info = "Traceback: SECRET_PATH=/opt/sicode/.env contraseña=no_debe_salir"

        def get_status(self, refresh=True):
            return Estado()

        def get_meta(self, refresh=True):
            return dict(self.meta)

    monkeypatch.setattr(modulo, "_redis", lambda: object())
    monkeypatch.setattr(modulo.Job, "fetch", lambda job_id, connection=None: JobFalso())

    cliente = _login(app_jobs)
    respuesta = cliente.get("/coordinacion/analisis-documental/ia/trabajos/job-seguro/estado")
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["estado"] == "failed"
    assert datos["semaforo"] == "rojo"
    assert "error" not in datos
    texto = respuesta.get_data(as_text=True)
    assert "SECRET_PATH" not in texto
    assert "contraseña" not in texto
