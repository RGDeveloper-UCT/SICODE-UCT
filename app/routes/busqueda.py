from flask import Blueprint, render_template, request
from flask_login import login_required

from app.services.busqueda_service import buscar_global


busqueda_bp = Blueprint("busqueda", __name__)


@busqueda_bp.route("/buscar")
@login_required
def global_():
    q = request.args.get("q", "").strip()
    resultados = buscar_global(q) if q else []
    return render_template("busqueda/resultados.html", q=q, resultados=resultados)
