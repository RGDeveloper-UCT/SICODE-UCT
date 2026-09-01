"""Control de acceso transversal del módulo NEXO.

NEXO forma parte del panel de Administración y, por diseño, únicamente puede
ser consultado por cuentas con rol administrador. El guard se registra sobre
el Blueprint para proteger también accesos directos por URL, no solo ocultar
el enlace en la interfaz.
"""

from flask import abort
from flask_login import current_user

from app.routes.nexo_ia import nexo_ia_bp


@nexo_ia_bp.before_request
def restringir_nexo_a_administradores():
    if current_user.is_authenticated and current_user.rol != "administrador":
        abort(403)
    return None
