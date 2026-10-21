"""Verifica que la política Referer y CSRF HTTPS sean compatibles."""
from flask_wtf.csrf import generate_csrf
from app import create_app


def test_csrf_https_mismo_origen_conserva_proteccion():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)

    @app.route("/__test_csrf_referer", methods=["GET", "POST"])
    def ruta_prueba():
        from flask import request
        return generate_csrf() if request.method == "GET" else "registrado"

    client = app.test_client()
    pagina = client.get("/__test_csrf_referer", base_url="https://sicode.test")
    assert pagina.status_code == 200
    assert pagina.headers["Referrer-Policy"] == "same-origin"
    token = pagina.get_data(as_text=True)

    correcto = client.post(
        "/__test_csrf_referer", base_url="https://sicode.test",
        data={"csrf_token": token},
        headers={"Referer": "https://sicode.test/coordinacion/seguridad/personal/nuevo"},
    )
    assert correcto.status_code == 200

    ausente = client.post(
        "/__test_csrf_referer", base_url="https://sicode.test",
        data={"csrf_token": token},
    )
    assert ausente.status_code == 400

    origen_distinto = client.post(
        "/__test_csrf_referer", base_url="https://sicode.test",
        data={"csrf_token": token},
        headers={"Referer": "https://ejemplo-ajeno.test/"},
    )
    assert origen_distinto.status_code == 400
