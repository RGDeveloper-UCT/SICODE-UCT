from flask import Blueprint
from flask_login import login_required

from app.models.lote_documental import AprendizajeDocumental


aprendizaje_documental_bp = Blueprint(
    "aprendizaje_documental",
    __name__,
    url_prefix="/coordinacion/analisis-documental/lotes",
)


@aprendizaje_documental_bp.route("/aprendizaje")
@login_required
def estado():
    perfiles = AprendizajeDocumental.query.all()
    muestras = sum(int(p.muestras_confirmadas or 0) for p in perfiles)
    aciertos = sum(int(p.clasificaciones_correctas or 0) for p in perfiles)
    nivel = (
        int(round(sum((p.nivel_aprendizaje or 0) * p.muestras_confirmadas for p in perfiles) / muestras))
        if muestras else 0
    )
    precision = int(round(aciertos / muestras * 100)) if muestras else 0
    return {
        "nivel": max(0, min(100, nivel)),
        "muestras": muestras,
        "precision_clasificacion": max(0, min(100, precision)),
        "tipos_aprendidos": sum(1 for p in perfiles if p.muestras_confirmadas),
    }
