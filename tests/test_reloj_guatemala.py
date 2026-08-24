from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reloj_guatemala_integrado_en_barra_superior():
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/js/reloj_guatemala.js").read_text(encoding="utf-8")
    estilos = (ROOT / "app/static/css/reloj_guatemala.css").read_text(encoding="utf-8")

    assert 'data-reloj-guatemala' in base
    assert 'Hora local de Guatemala' in base
    assert 'reloj_guatemala.js' in base
    assert 'reloj_guatemala.css' in base
    assert "America/Guatemala" in javascript
    assert "second: '2-digit'" in javascript
    assert "hour12: false" in javascript
    assert ".reloj-guatemala" in estilos
    assert "font-variant-numeric: tabular-nums" in estilos
