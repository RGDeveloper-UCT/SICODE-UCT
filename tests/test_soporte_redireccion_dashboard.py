from pathlib import Path


def test_ticket_soporte_cerrado_regresa_al_dashboard():
    javascript = Path("app/static/js/ticket_soporte.js").read_text(encoding="utf-8")

    assert "const dashboardPath = '/dashboard';" in javascript
    assert "ticket.pendingSubmitState === 'PENDIENTE'" in javascript
    assert "window.location.replace(dashboardPath);" in javascript
    assert "clearTicket();" in javascript
