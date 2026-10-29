"""Pruebas HashPass HP-001 sobre SQLite temporal, sin secretos reales."""
import pytest
from cryptography.exceptions import InvalidTag
from flask import g
from flask_login import login_user
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.hashpass import HashPassBoveda, HashPassPermiso, HashPassRegistro
from app.models.bitacora import Bitacora
from app.models.usuario import Usuario
from app.services.hashpass_crypto import (
    abrir_boveda, cifrar_registro, crear_boveda, descifrar_registro,
    reenvolver_clave,
)

MAESTRA = "frase-de-prueba-para-hashpass-2026"


def test_aead_vincula_dueno_y_registro_y_detecta_manipulacion():
    sal, nonce, envuelta = crear_boveda(MAESTRA, 101)
    dek = abrir_boveda(MAESTRA, 101, sal, nonce, envuelta)
    assert len(dek) == 32
    with pytest.raises(InvalidTag):
        abrir_boveda("incorrecta-muy-larga-2026", 101, sal, nonce, envuelta)
    with pytest.raises(InvalidTag):
        abrir_boveda(MAESTRA, 102, sal, nonce, envuelta)
    datos = {"nombre": "Web de prueba", "usuario": "demo", "secreto": "solo-prueba"}
    n, cifrado = cifrar_registro(dek, 101, "identificador-a", datos)
    assert b"solo-prueba" not in cifrado
    assert b"Web de prueba" not in cifrado
    assert descifrar_registro(dek, 101, "identificador-a", n, cifrado) == datos
    with pytest.raises(InvalidTag):
        descifrar_registro(dek, 101, "identificador-b", n, cifrado)
    with pytest.raises(InvalidTag):
        descifrar_registro(dek, 102, "identificador-a", n, cifrado)
    with pytest.raises(InvalidTag):
        descifrar_registro(dek, 101, "identificador-a", n, cifrado[:-1] + bytes([cifrado[-1] ^ 1]))
    sal2, nonce2, envuelta2 = reenvolver_clave(dek, "nueva-frase-maestra-de-pruebas", 101)
    assert abrir_boveda("nueva-frase-maestra-de-pruebas", 101, sal2, nonce2, envuelta2) == dek
    with pytest.raises(InvalidTag):
        abrir_boveda(MAESTRA, 101, sal2, nonce2, envuelta2)


@pytest.fixture
def contexto_hashpass():
    app = create_app()
    app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        HASHPASS_ENABLED=True, HASHPASS_REQUIRE_HTTPS=False,
    )
    # El app_context de la fixture permanece abierto entre varios clientes.
    # Flask-Login almacena current_user en g, común a ese contexto; limpiar
    # su caché ANTES de otros before_request evita suplantación entre clientes.
    def _aislar_cliente_test():
        g.pop("_login_user", None)

    app.before_request_funcs.setdefault(None, []).insert(0, _aislar_cliente_test)

    @app.get("/__hashpass_test_login/<int:usuario_id>")
    def _login_hashpass_test(usuario_id):
        usuario = db.session.get(Usuario, usuario_id)
        login_user(usuario, fresh=True)
        return "ok"

    with app.app_context():
        db.create_all()
        try:
            usuarios = []
            for nombre, rol in [
                ("hp-admin-test", Usuario.ROL_ADMINISTRADOR),
                ("hp-usuario-a", Usuario.ROL_AUTORIZADO),
                ("hp-usuario-b", Usuario.ROL_AUTORIZADO),
            ]:
                usuario = Usuario(
                    nombre=nombre, usuario=nombre, rol=rol, activo=True,
                    password_hash=generate_password_hash("clave-sicode-test-2026"),
                )
                usuario.debe_cambiar_password = False
                db.session.add(usuario)
                usuarios.append(usuario)
            db.session.commit()
            yield app, [u.id for u in usuarios]
        finally:
            db.session.remove()
            db.drop_all()


def _cliente(app, usuario_id):
    cliente = app.test_client()
    assert cliente.get(f"/__hashpass_test_login/{usuario_id}").status_code == 200
    return cliente


def test_permiso_privado_cifrado_bitacora_e_idor(contexto_hashpass):
    app, ids = contexto_hashpass
    admin = _cliente(app, ids[0])
    usuario = _cliente(app, ids[1])
    otro = _cliente(app, ids[2])
    assert usuario.get("/hashpass/").status_code == 403
    assert admin.get("/hashpass/").status_code == 403

    # Sólo un administrador puede conceder. Usuario sin autorización: 403.
    assert usuario.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"}).status_code == 403
    assert admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"}).status_code == 302
    assert usuario.get("/hashpass/").status_code == 302

    configuracion = usuario.post("/hashpass/configurar", data={"maestra": MAESTRA, "confirmar": MAESTRA})
    assert configuracion.status_code == 302
    boveda = db.session.get(HashPassBoveda, ids[1])
    assert boveda is not None
    assert MAESTRA.encode() not in boveda.clave_envuelta

    creado = usuario.post("/hashpass/registro/nuevo", data={
        "tipo": "servidor", "nombre": "Equipo ficticio",
        "usuario": "admin-demo", "secreto": "secreto-ficticio-123",
        "ip": "192.0.2.44", "maestra": MAESTRA,
    })
    assert creado.status_code == 302
    registro = HashPassRegistro.query.filter_by(usuario_id=ids[1]).one()
    assert b"secreto-ficticio" not in registro.contenido_cifrado
    assert b"192.0.2.44" not in registro.contenido_cifrado
    assert b"Equipo ficticio" not in registro.contenido_cifrado
    listado = usuario.post("/hashpass/", data={"maestra": MAESTRA, "q": "Equipo"})
    assert listado.status_code == 200
    assert b"Equipo ficticio" in listado.data
    assert "no-store" in listado.headers["Cache-Control"]
    assert usuario.get(f"/hashpass/registro/{registro.id}/ver").status_code == 200
    detalle = usuario.post(f"/hashpass/registro/{registro.id}/ver", data={"maestra": MAESTRA})
    assert detalle.status_code == 200
    assert b"secreto-ficticio-123" in detalle.data
    assert "no-store" in detalle.headers["Cache-Control"]
    assert Bitacora.query.filter_by(accion="HASHPASS_REVELAR_REGISTRO").count() == 1
    assert "secreto-ficticio" not in str([
        (b.accion, b.descripcion, b.datos_anteriores, b.datos_posteriores)
        for b in Bitacora.query.filter_by(modulo="HashPass")
    ])

    assert admin.post(f"/hashpass/permiso/{ids[2]}", data={"accion": "conceder"}).status_code == 302
    assert otro.get(f"/hashpass/registro/{registro.id}/ver").status_code == 404
    assert admin.get(f"/hashpass/registro/{registro.id}/ver").status_code == 403
    assert admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "revocar"}).status_code == 302
    assert usuario.get("/hashpass/").status_code == 403


def test_fallos_de_maestra_se_auditan(contexto_hashpass):
    app, ids = contexto_hashpass
    admin = _cliente(app, ids[0])
    usuario = _cliente(app, ids[1])
    admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"})
    usuario.post("/hashpass/configurar", data={"maestra": MAESTRA, "confirmar": MAESTRA})
    for _ in range(5):
        response = usuario.post("/hashpass/registro/nuevo", data={
            "tipo": "web", "nombre": "Demo", "secreto": "dummy",
            "maestra": "maestra-incorrecta-pruebas",
        })
        assert response.status_code == 200
    assert Bitacora.query.filter_by(accion="HASHPASS_MAESTRA_FALLIDA").count() == 5
    bloqueado = usuario.post("/hashpass/registro/nuevo", data={
        "tipo": "web", "nombre": "Demo", "secreto": "dummy", "maestra": MAESTRA,
    })
    assert bloqueado.status_code == 429
    assert HashPassRegistro.query.count() == 0
