from flask import render_template
from flask_login import login_required

from app.routes.sicode_ia import TIPOS_DOCUMENTO_LOTE, _analisis_lote, _exigir_modificacion, _segmentos_lote


@login_required
def revision_rc_re(token):
    _exigir_modificacion()
    analisis = _analisis_lote(token)
    segmentos = _segmentos_lote(analisis)
    verificados = sum(1 for s in segmentos if s.estado == "VERIFICADO_HUMANO")
    cargados = sum(1 for s in segmentos if s.estado == "CONFIRMADO")
    return render_template(
        "analisis_documental/sicode_ia_revision_rc_re.html",
        analisis=analisis,
        segmentos=segmentos,
        token=token,
        verificados=verificados,
        cargados=cargados,
        total=len(segmentos),
        tipos_documento=TIPOS_DOCUMENTO_LOTE,
    )
