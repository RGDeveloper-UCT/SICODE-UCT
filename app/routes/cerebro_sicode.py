from flask import Blueprint, abort, jsonify
from flask_login import current_user, login_required

from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes
from app.services.cerebro_sicode_schema import inventariar_esquema_sicode
from app.services.cerebro_sicode_service import analizar_sicode, guardar_hallazgos


cerebro_sicode_bp = Blueprint(
    "cerebro_sicode",
    __name__,
    url_prefix="/coordinacion/analisis-documental/ia/cerebro",
)


@cerebro_sicode_bp.route("/estado")
@login_required
def estado():
    if current_user.rol != "administrador":
        abort(403)

    aprendidas = absorber_verificaciones_pendientes(usuario_id=current_user.id)
    esquema = inventariar_esquema_sicode(usuario_id=current_user.id)
    resultado = analizar_sicode()
    nuevos_hallazgos = guardar_hallazgos(resultado, usuario_id=current_user.id)
    resultado["retroalimentaciones_nuevas"] = aprendidas
    resultado["hallazgos_guardados_nuevos"] = nuevos_hallazgos
    resultado["esquema"] = esquema

    return jsonify(resultado)
