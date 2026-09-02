from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSICIONES_JS = ROOT / "app" / "static" / "js" / "transiciones.js"
SCROLL_FIX_JS = ROOT / "app" / "static" / "js" / "coordinacion_scroll_fix.js"
SCROLL_FIX_CSS = ROOT / "app" / "static" / "css" / "coordinacion_scroll_fix.css"
BASE_HTML = ROOT / "app" / "templates" / "base.html"


def test_carrete_coordinacion_usa_una_sola_fila():
    javascript = TRANSICIONES_JS.read_text(encoding="utf-8")

    assert "flex-flow: row nowrap !important;" in javascript
    assert "grid-template-rows: repeat(2" not in javascript
    assert "Tipos de registro de Coordinación en una sola fila" in javascript


def test_carrete_coordinacion_tiene_movimiento_interpolado_y_arrastre():
    javascript = TRANSICIONES_JS.read_text(encoding="utf-8")

    assert "easeInOutCubic" in javascript
    assert "requestAnimationFrame" in javascript
    assert "coord-carrete-arrastrando" in javascript
    assert 'evento.key === "Home"' in javascript
    assert 'evento.key === "End"' in javascript


def test_inicio_coordinacion_no_bloquea_scroll_vertical_y_limita_altura_de_tarjetas():
    css = SCROLL_FIX_CSS.read_text(encoding="utf-8")

    assert "overflow-y: auto !important;" in css
    assert "height: auto !important;" in css
    assert "height: clamp(270px, 29vh, 310px) !important;" in css
    assert "max-height: 310px !important;" in css
    assert ".acciones-tarjeta-registro" in css


def test_botones_registro_quedan_activos_centrados_y_con_area_clicable_amplia():
    css = SCROLL_FIX_CSS.read_text(encoding="utf-8")
    javascript = SCROLL_FIX_JS.read_text(encoding="utf-8")

    assert "justify-content: center;" in css
    assert "pointer-events: auto !important;" in css
    assert "min-height: 42px;" in css
    assert "flex: 0 1 84%;" in css
    assert 'querySelectorAll("a, button, summary, input, select, textarea, label' in javascript
    assert 'control.addEventListener("pointerdown"' in javascript
    assert "evento.stopPropagation();" in javascript


def test_subpanel_anexos_no_es_capturado_por_el_arrastre_y_libera_altura():
    css = SCROLL_FIX_CSS.read_text(encoding="utf-8")
    javascript = SCROLL_FIX_JS.read_text(encoding="utf-8")

    assert 'track.querySelector(".subpanel-anexos")' in javascript
    assert "HTMLDetailsElement" in javascript
    assert 'classList.toggle("coord-subpanel-abierto"' in javascript
    assert 'evento.target.closest("a, button, summary' in javascript
    assert ".coord-carrete-track.coord-subpanel-abierto" in css
    assert "height: 360px !important;" in css
    assert ".subpanel-anexos[open]" in css
    assert "overflow: visible !important;" in css


def test_titulo_anexos_tambien_abre_subpanel_con_mouse_y_teclado():
    javascript = SCROLL_FIX_JS.read_text(encoding="utf-8")

    assert 'querySelector(".tarjeta-registro-titulos")' in javascript
    assert 'setAttribute("role", "button")' in javascript
    assert 'setAttribute("tabindex", "0")' in javascript
    assert 'tituloAnexos.addEventListener("click"' in javascript
    assert 'evento.key !== "Enter" && evento.key !== " "' in javascript


def test_carrete_usa_animacion_quintica_para_flechas_teclado_y_gestos():
    javascript = SCROLL_FIX_JS.read_text(encoding="utf-8")

    assert "easeInOutQuint" in javascript
    assert "moverSuaveA" in javascript
    assert "requestAnimationFrame" in javascript
    assert ".coord-carrete-boton" in javascript
    assert "evento.stopImmediatePropagation();" in javascript
    assert "destinoGestual" in javascript


def test_rueda_vertical_se_reserva_para_la_pagina():
    javascript = SCROLL_FIX_JS.read_text(encoding="utf-8")

    assert "horizontalReal" in javascript
    assert "horizontalConShift" in javascript
    assert "evento.stopImmediatePropagation();" in javascript
    assert "evento.preventDefault();" in javascript
    assert "capture: true" in javascript


def test_base_carga_ajustes_de_coordinacion_despues_de_estilos_y_transiciones():
    plantilla = BASE_HTML.read_text(encoding="utf-8")

    assert "css/coordinacion_scroll_fix.css" in plantilla
    assert "js/coordinacion_scroll_fix.js" in plantilla
    assert plantilla.index("js/transiciones.js") < plantilla.index("js/coordinacion_scroll_fix.js")
