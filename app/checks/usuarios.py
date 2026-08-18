from app.checks import HallazgoIntegridad
from app.models.usuario import Usuario


ROLES_VALIDOS = {"administrador", "usuario_autorizado"}


def ejecutar():
    hallazgos = []
    administradores_activos = 0

    for usuario in Usuario.query.all():
        if usuario.activo and usuario.rol == "administrador":
            administradores_activos += 1
        if usuario.rol not in ROLES_VALIDOS:
            hallazgos.append(HallazgoIntegridad(
                codigo="USR-ROL-001",
                severidad="error",
                modulo="Usuarios",
                entidad="Usuario",
                registro=usuario.usuario,
                descripcion=f"Rol no reconocido: {usuario.rol}.",
                recomendacion="Asignar un rol institucional válido después de revisar sus responsabilidades.",
            ))

    if administradores_activos == 0:
        hallazgos.append(HallazgoIntegridad(
            codigo="USR-ADMIN-001",
            severidad="error",
            modulo="Usuarios",
            entidad="Sistema",
            registro="Administradores",
            descripcion="No existe ningún administrador activo.",
            recomendacion="Reactivar o crear de forma controlada una cuenta administrativa.",
        ))

    return hallazgos
