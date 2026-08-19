from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user, login_required

from app import db
from app.models.expediente import Expediente
from app.security import admin_required
from app.services.expedientes_admin_service import (
    AlineacionCodigosError,
    EliminacionExpedienteBloqueada,
    eliminar_registro_administrativo,
)


expedientes_admin_bp = Blueprint("expedientes_admin", __name__)


@expedientes_admin_bp.route("/expedientes/<int:expediente_id>/eliminar-admin", methods=["POST"])
@login_required
@admin_required
def eliminar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    no_sp = expediente.no_sp

    try:
        cambios = eliminar_registro_administrativo(expediente, current_user.id)
        db.session.commit()
    except EliminacionExpedienteBloqueada as error:
        db.session.rollback()
        detalle = ", ".join(
            f"{nombre}: {cantidad}" for nombre, cantidad in error.dependencias.items()
        )
        flash(
            "No se puede eliminar este SP porque ya tiene historial operativo asociado "
            f"({detalle}). Desactívelo para conservar trazabilidad.",
            "danger",
        )
        return redirect(url_for("expedientes.detalle", expediente_id=expediente_id))
    except AlineacionCodigosError as error:
        db.session.rollback()
        flash(f"No se realizó la eliminación: {error}", "danger")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente_id))
    except Exception:
        db.session.rollback()
        raise

    flash(
        f"SP {no_sp} eliminado. Se realinearon {len(cambios)} códigos internos SICODE con su No. de SP.",
        "success",
    )
    return redirect(url_for("expedientes.listado"))
