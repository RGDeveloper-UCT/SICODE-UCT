from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required

from app.routes.nexo_ia import nexo_ia_bp
from app.services.nexo_autocorreccion_service import aplicar_autocorreccion_ortografica


def _exigir_administrador():
    if not current_user.is_authenticated or current_user.rol != "administrador":
        abort(403)
    if not getattr(current_user, "puede_modificar", False):
        abort(403)


@nexo_ia_bp.route("/corregir-ortografia-segura", methods=["POST"])
@login_required
def corregir_ortografia_segura():
    """Aplica únicamente normalizaciones ortográficas de catálogo >=95%."""
    _exigir_administrador()
    resultado = aplicar_autocorreccion_ortografica(usuario_id=current_user.id)
    total = int(resultado.get("registros_corregidos") or 0)

    if total:
        cambios = resultado.get("correcciones") or []
        ejemplos = "; ".join(
            f"{item['anterior']} → {item['canonico']} ({item['registros']})"
            for item in cambios[:4]
        )
        flash(
            f"NEXO corrigió {total} registro(s) con confianza ortográfica >=95%. "
            f"{ejemplos}",
            "success",
        )
    else:
        flash(
            "NEXO no encontró errores ortográficos que cumplan el umbral seguro de 95%.",
            "info",
        )

    return redirect(url_for("nexo_ia.inicio"))
