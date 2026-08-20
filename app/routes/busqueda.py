from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app.services.bitacora_service import registrar_bitacora
from app.services.busqueda_ia_service import buscar_con_ia
from app.services.busqueda_service import buscar_global


busqueda_bp = Blueprint("busqueda", __name__)


@busqueda_bp.route("/buscar")
@login_required
def global_():
    q = request.args.get("q", "").strip()
    resultados = buscar_global(q) if q else []
    return render_template(
        "busqueda/resultados.html",
        q=q,
        resultados=resultados,
        consulta_ia="",
        resultado_ia=None,
    )


@busqueda_bp.route("/buscar/ia", methods=["POST"])
@login_required
def ia():
    consulta_ia = request.form.get("consulta_ia", "").strip()
    if len(consulta_ia) < 3:
        flash("Escriba una consulta de al menos 3 caracteres para la búsqueda con IA.", "warning")
        return render_template(
            "busqueda/resultados.html",
            q="",
            resultados=[],
            consulta_ia=consulta_ia,
            resultado_ia=None,
        )

    resultado_ia = buscar_con_ia(consulta_ia)
    registrar_bitacora(
        accion="CONSULTA_IA",
        modulo="BÚSQUEDA",
        descripcion=f"Búsqueda IA: {consulta_ia[:250]}",
        usuario_id=current_user.id,
        entidad="busqueda_ia",
        datos_posteriores={
            "motor": resultado_ia["motor"],
            "filtros": resultado_ia["filtros"],
            "cantidad_resultados": len(resultado_ia["resultados"]),
        },
    )

    return render_template(
        "busqueda/resultados.html",
        q="",
        resultados=[],
        consulta_ia=consulta_ia,
        resultado_ia=resultado_ia,
    )
