from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSICIONES_JS = ROOT / "app" / "static" / "js" / "transiciones.js"


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
