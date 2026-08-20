from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]


def test_formulario_cambio_password_visor_tiene_excepcion_visual():
    plantilla = (RAIZ / "app/templates/cuenta/cambiar_password.html").read_text(encoding="utf-8")
    css = (RAIZ / "app/static/css/visor_permisos.css").read_text(encoding="utf-8")

    assert "visor-post-permitido" in plantilla
    assert "form.visor-post-permitido" in css
    assert "display: block !important" in css


def test_busqueda_ia_post_sigue_visible_para_visor():
    plantilla = (RAIZ / "app/templates/busqueda/resultados.html").read_text(encoding="utf-8")
    css = (RAIZ / "app/static/css/visor_permisos.css").read_text(encoding="utf-8")

    assert 'action="{{ url_for(\'busqueda.ia\') }}"' in plantilla
    assert 'form[action*="/buscar/ia"]' in css


def test_css_excepciones_se_carga_despues_de_css_visor():
    base = (RAIZ / "app/templates/base.html").read_text(encoding="utf-8")

    posicion_visor = base.index("css/visor.css")
    posicion_excepciones = base.index("css/visor_permisos.css")
    assert posicion_excepciones > posicion_visor
