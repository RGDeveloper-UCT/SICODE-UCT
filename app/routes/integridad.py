from flask import Blueprint, render_template
from flask_login import login_required

from app.security import admin_required
from app.services.integridad_service import ejecutar_control_integridad


integridad_bp = Blueprint("integridad", __name__, url_prefix="/admin/integridad")


@integridad_bp.route("")
@integridad_bp.route("/")
@login_required
@admin_required
def inicio():
    return render_template(
        "admin/integridad.html",
        control=ejecutar_control_integridad(),
    )
