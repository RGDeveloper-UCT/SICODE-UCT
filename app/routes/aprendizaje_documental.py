from flask_login import login_required

from app.models.lote_documental import AprendizajeDocumental
from app.routes.lote_documental import lote_documental_bp


def estado_aprendizaje():
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


lote_documental_bp.add_url_rule(
    "/aprendizaje",
    endpoint="aprendizaje",
    view_func=login_required(estado_aprendizaje),
    methods=["GET"],
)
