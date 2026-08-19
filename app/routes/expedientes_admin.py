from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user, login_required

from app import db
from app.models.expediente import Expediente
from app.security import admin_required
from app.services.expedientes_admin_service import (
    AlineacionCodigosError,
    EliminacionExpedienteBloqueada,
    dependencias_purgables,
    eliminar_registro_administrativo,
)


expedientes_admin_bp = Blueprint("expedientes_admin", __name__)


@expedientes_admin_bp.route("/expedientes/<int:expediente_id>/eliminar-admin", methods=["POST"])
@login_required
@admin_required
def eliminar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    no_sp = expediente.no_sp
    historial_local = dependencias_purgables(expediente.id)

    try:
        cambios = eliminar_registro_administrativo(expediente, current_user.id)
        db.session.commit()
    except EliminacionExpedienteBloqueada as error:
        db.session.rollback()
        detalle = ", ".join(
            f"{nombre}: {cantidad}" for nombre, cantidad in error.dependencias.items()
        )
        flash(
            "No se puede purgar este SP porque está vinculado con trazabilidad institucional "
            f"({detalle}). En este caso debe conservarse y desactivarse.",
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

    detalle_historial = (
        "; historial local eliminado: "
        + ", ".join(f"{nombre} {cantidad}" for nombre, cantidad in historial_local.items())
        if historial_local
        else ""
    )
    flash(
        f"SP {no_sp} eliminado definitivamente{detalle_historial}. "
        f"Se realinearon {len(cambios)} códigos internos SICODE con su No. de SP.",
        "success",
    )
    return redirect(url_for("expedientes.listado"))
