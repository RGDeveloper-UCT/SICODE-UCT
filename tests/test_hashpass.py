"""Pruebas HashPass HP-001 sobre SQLite temporal, sin secretos reales."""
import base64
import re

import pytest
from cryptography.exceptions import InvalidTag
from flask import g
from flask_login import login_user
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.hashpass import HashPassBoveda, HashPassPermiso, HashPassRegistro, HashPassCompartido
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
    panel = usuario.get("/hashpass/configurar")
    assert panel.status_code == 200
    assert b"Argon2id" in panel.data
    assert b"AES-256-GCM" in panel.data
    assert b"HTTPS" in panel.data

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
    bloqueo = usuario.get("/hashpass/")
    assert bloqueo.status_code == 200
    assert b"b\xc3\xb3veda est\xc3\xa1 bloqueada" in bloqueo.data
    assert registro.id[:8].encode() not in bloqueo.data
    assert b"<th>Identificador</th>" not in bloqueo.data
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


def test_admin_ve_estado_y_acceso_de_permisos(contexto_hashpass):
    app, ids = contexto_hashpass
    admin = _cliente(app, ids[0])
    pagina = admin.get("/admin/usuarios")
    assert pagina.status_code == 200
    assert b"HashPass" in pagina.data
    assert b"Conceder permiso HashPass" in pagina.data

    app.config["HASHPASS_ENABLED"] = False
    deshabilitado = admin.get("/admin/usuarios")
    assert deshabilitado.status_code == 200
    assert b"deshabilitado" in deshabilitado.data
    assert b"Conceder permiso HashPass" not in deshabilitado.data
    assert admin.get("/hashpass/").status_code == 404


def test_cli_hashpass_status_sin_secretos(contexto_hashpass):
    app, ids = contexto_hashpass
    resultado = app.test_cli_runner().invoke(args=["hashpass-status"])
    assert resultado.exit_code == 0, resultado.output
    assert "Tablas HashPass presentes=True" in resultado.output
    assert "HASHPASS_ENABLED=True" in resultado.output
    assert MAESTRA not in resultado.output


def test_produccion_bloquea_http_y_cookies_inseguras(contexto_hashpass):
    app, ids = contexto_hashpass
    admin = _cliente(app, ids[0])
    app.config.update(TESTING=False, HASHPASS_REQUIRE_HTTPS=False, SESSION_COOKIE_SECURE=False)
    url = f"/hashpass/permiso/{ids[1]}"
    assert admin.post(url, data={"accion": "conceder"}).status_code == 403

    app.config.update(HASHPASS_REQUIRE_HTTPS=True, SESSION_COOKIE_SECURE=True)
    assert admin.post(url, data={"accion": "conceder"}, base_url="http://localhost").status_code == 403
    respuesta = admin.post(url, data={"accion": "conceder"}, base_url="https://localhost")
    assert respuesta.status_code == 302


def test_csrf_estricto_https_y_referer_mismo_origen(contexto_hashpass):
    """Formulario real: token válido + Referer HTTPS sin reducir protección CSRF."""
    app, ids = contexto_hashpass
    app.config.update(WTF_CSRF_ENABLED=True, WTF_CSRF_SSL_STRICT=True)
    db.session.add(HashPassPermiso(
        usuario_id=ids[1], autorizado=True, autorizado_por=ids[0]
    ))
    db.session.commit()

    client = app.test_client()
    base = "https://localhost"
    assert client.get(
        f"/__hashpass_test_login/{ids[1]}", base_url=base
    ).status_code == 200

    response = client.get("/hashpass/configurar", base_url=base)
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cache-Control"].startswith("no-store")
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)
    )
    assert token is not None

    # Flask-WTF debe seguir rechazando POST HTTPS sin Referer.
    datos = {"maestra": MAESTRA, "confirmar": MAESTRA, "csrf_token": token.group(1)}
    sin_referer = client.post(
        "/hashpass/configurar", data=datos, base_url=base
    )
    assert sin_referer.status_code == 400

    # La solicitud legítima same-origin sí es aceptada.
    aceptado = client.post(
        "/hashpass/configurar",
        data=datos,
        base_url=base,
        headers={"Referer": "https://localhost/hashpass/configurar"},
    )
    assert aceptado.status_code == 302
    assert db.session.get(HashPassBoveda, ids[1]) is not None


MAESTRA_B = "frase-de-otra-persona-maestra-2026"


def _compartidos_habilitados(app):
    # Únicamente material ficticio de pruebas; no reutilizar en producción.
    app.config.update(
        HASHPASS_SHARED_ENABLED=True,
        HASHPASS_SHARED_KEY_B64=base64.b64encode(bytes(range(32))).decode("ascii"),
    )


def test_compartidos_entre_usuarios_y_permiso_revocado(contexto_hashpass):
    app, ids = contexto_hashpass
    _compartidos_habilitados(app)
    admin = _cliente(app, ids[0])
    autor = _cliente(app, ids[1])
    lector = _cliente(app, ids[2])
    for usuario_id in ids[1:]:
        assert admin.post(
            f"/hashpass/permiso/{usuario_id}", data={"accion": "conceder"},
        ).status_code == 302
    assert autor.post(
        "/hashpass/configurar", data={"maestra": MAESTRA, "confirmar": MAESTRA},
    ).status_code == 302
    assert lector.post(
        "/hashpass/configurar", data={"maestra": MAESTRA_B, "confirmar": MAESTRA_B},
    ).status_code == 302

    nuevo = autor.post("/hashpass/compartidos/nuevo", data={
        "tipo": "red", "nombre": "AP institucional ficticio",
        "usuario": "wifi-demo", "secreto": "clave-ficticia-de-pruebas",
        "ip": "192.0.2.88", "maestra": MAESTRA,
    })
    assert nuevo.status_code == 302
    registro = HashPassCompartido.query.one()
    assert b"clave-ficticia" not in registro.contenido_cifrado
    assert b"AP institucional" not in registro.contenido_cifrado
    assert b"192.0.2.88" not in registro.contenido_cifrado

    # El usuario B no requiere la contraseña maestra de A.
    bloqueada = lector.get("/hashpass/compartidos")
    assert bloqueada.status_code == 200
    assert b"AP institucional" not in bloqueada.data
    mostrados = lector.post("/hashpass/compartidos", data={"maestra": MAESTRA_B})
    assert mostrados.status_code == 200
    assert b"AP institucional ficticio" in mostrados.data
    assert b"clave-ficticia" not in mostrados.data

    detalle = lector.post(
        f"/hashpass/compartidos/{registro.id}/ver",
        data={"maestra": MAESTRA_B},
    )
    assert detalle.status_code == 200
    assert b"clave-ficticia-de-pruebas" in detalle.data
    assert Bitacora.query.filter_by(
        accion="HASHPASS_COMPARTIDO_REVELAR", usuario_id=ids[2],
    ).count() == 1

    editado = lector.post(
        f"/hashpass/compartidos/{registro.id}/editar",
        data={
            "tipo": "red", "nombre": "AP compartido actualizado",
            "secreto": "otra-clave-ficticia", "maestra": MAESTRA_B,
        },
    )
    assert editado.status_code == 302
    assert db.session.get(HashPassCompartido, registro.id).actualizado_por_id == ids[2]
    assert b"otra-clave-ficticia" in autor.post(
        f"/hashpass/compartidos/{registro.id}/ver", data={"maestra": MAESTRA}
    ).data

    # El administrador sin permiso propio tampoco puede revelar.
    assert admin.get(f"/hashpass/compartidos/{registro.id}/ver").status_code == 403
    admin.post(f"/hashpass/permiso/{ids[2]}", data={"accion": "revocar"})
    assert lector.get("/hashpass/compartidos").status_code == 403


def test_publicacion_legado_una_vez_y_acceso_posterior(contexto_hashpass):
    app, ids = contexto_hashpass
    admin = _cliente(app, ids[0])
    autor = _cliente(app, ids[1])
    lector = _cliente(app, ids[2])
    admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"})
    autor.post("/hashpass/configurar", data={"maestra": MAESTRA, "confirmar": MAESTRA})
    creado = autor.post("/hashpass/registro/nuevo", data={
        "tipo": "web", "nombre": "Web anterior",
        "secreto": "legado-ficticio-123", "maestra": MAESTRA,
    })
    assert creado.status_code == 302
    privado = HashPassRegistro.query.one()
    assert privado.archivado is False

    _compartidos_habilitados(app)
    assert autor.get("/hashpass/").status_code == 302
    assert autor.get("/hashpass/compartidos/publicar-privados").status_code == 200
    publicacion = autor.post(
        "/hashpass/compartidos/publicar-privados", data={"maestra": MAESTRA},
    )
    assert publicacion.status_code == 302
    compartido = HashPassCompartido.query.one()
    assert compartido.origen_privado_id == privado.id
    assert db.session.get(HashPassRegistro, privado.id).archivado is True
    assert autor.post(
        "/hashpass/compartidos/publicar-privados", data={"maestra": MAESTRA},
    ).status_code == 302
    assert HashPassCompartido.query.count() == 1

    # Usuario autorizado más tarde también obtiene acceso a lo compartido.
    admin.post(f"/hashpass/permiso/{ids[2]}", data={"accion": "conceder"})
    lector.post("/hashpass/configurar", data={"maestra": MAESTRA_B, "confirmar": MAESTRA_B})
    consulta = lector.post(
        f"/hashpass/compartidos/{compartido.id}/ver",
        data={"maestra": MAESTRA_B},
    )
    assert consulta.status_code == 200
    assert b"legado-ficticio-123" in consulta.data


def test_compartidos_no_operan_sin_clave_custodiada(contexto_hashpass):
    app, ids = contexto_hashpass
    app.config.update(HASHPASS_SHARED_ENABLED=True, HASHPASS_SHARED_KEY_B64="")
    admin = _cliente(app, ids[0])
    usuario = _cliente(app, ids[1])
    admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"})
    assert usuario.get("/hashpass/compartidos").status_code == 503
    assert HashPassCompartido.query.count() == 0
    panel = admin.get("/admin/usuarios")
    assert panel.status_code == 200
    assert b"HASHPASS_SHARED_KEY_B64" in panel.data
    assert b"Conceder permiso HashPass" not in panel.data


def test_auditoria_compartida_no_filtra_secretos(contexto_hashpass):
    app, ids = contexto_hashpass
    _compartidos_habilitados(app)
    admin = _cliente(app, ids[0])
    usuario = _cliente(app, ids[1])
    admin.post(f"/hashpass/permiso/{ids[1]}", data={"accion": "conceder"})
    usuario.post("/hashpass/configurar", data={"maestra": MAESTRA, "confirmar": MAESTRA})
    usuario.post("/hashpass/compartidos/nuevo", data={
        "nombre": "Demo log", "tipo": "api", "secreto": "NO-LOG-ESTE-VALOR",
        "maestra": MAESTRA,
    })
    registros = Bitacora.query.filter_by(modulo="HashPass").all()
    assert registros
    assert "NO-LOG-ESTE-VALOR" not in str([
        (x.accion, x.descripcion, x.datos_anteriores, x.datos_posteriores)
        for x in registros
    ])
