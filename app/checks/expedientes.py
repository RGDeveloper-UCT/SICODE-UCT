from collections import defaultdict

from app.checks import HallazgoIntegridad
from app.models.expediente import Expediente
from app.models.ubicacion import UbicacionFisica
from app.services.sp_service import normalizar_sp


ESTADOS_ADMIN_VALIDOS = {"Activo", "En revisión", "Cerrado"}


def ejecutar():
    hallazgos = []
    expedientes = Expediente.query.all()

    por_sp = defaultdict(list)
    for expediente in expedientes:
        por_sp[normalizar_sp(expediente.no_sp)].append(expediente)

        if expediente.estado_administrativo not in ESTADOS_ADMIN_VALIDOS:
            hallazgos.append(HallazgoIntegridad(
                codigo="EXP-ESTADO-001",
                severidad="error",
                modulo="Expedientes",
                entidad="Expediente",
                registro=f"SP {expediente.no_sp}",
                descripcion=f"Estado administrativo no válido: {expediente.estado_administrativo}.",
                recomendacion="Revisar el expediente y usar únicamente estados administrativos institucionales.",
            ))

        if not expediente.expediente_fisico_registrado:
            hallazgos.append(HallazgoIntegridad(
                codigo="EXP-FISICO-001",
                severidad="advertencia",
                modulo="Expedientes",
                entidad="Expediente",
                registro=f"SP {expediente.no_sp}",
                descripcion="El SP está registrado, pero todavía no se ha confirmado la existencia del expediente físico.",
                recomendacion="Registrar el expediente físico cuando sea recibido/localizado; no crear otro SP.",
            ))
        else:
            tiene_ubicacion = UbicacionFisica.query.filter_by(expediente_id=expediente.id).first() is not None
            if not tiene_ubicacion:
                hallazgos.append(HallazgoIntegridad(
                    codigo="EXP-UBIC-001",
                    severidad="advertencia",
                    modulo="Expedientes",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="Expediente físico sin ubicación registrada.",
                    recomendacion="Registrar archivador/estante/caja o la ubicación institucional correspondiente.",
                ))

            verificaciones = sorted(
                expediente.verificaciones,
                key=lambda item: item.creado_en,
                reverse=True,
            )
            if not verificaciones:
                hallazgos.append(HallazgoIntegridad(
                    codigo="EXP-VERIF-001",
                    severidad="advertencia",
                    modulo="Expedientes",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="Expediente físico sin una verificación histórica registrada en el nuevo control.",
                    recomendacion="Registrar una verificación cuando corresponda; no inventar verificaciones históricas faltantes.",
                ))
            elif expediente.estado_fisico_documental != verificaciones[0].resultado:
                hallazgos.append(HallazgoIntegridad(
                    codigo="EXP-VERIF-002",
                    severidad="error",
                    modulo="Expedientes",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion=(
                        f"El estado actual '{expediente.estado_fisico_documental}' no coincide con la última "
                        f"verificación '{verificaciones[0].resultado}'."
                    ),
                    recomendacion="Revisar el historial y corregir el estado actual solo después de confirmar cuál evento es válido.",
                ))

    for clave, registros in por_sp.items():
        if clave and len(registros) > 1:
            hallazgos.append(HallazgoIntegridad(
                codigo="EXP-SP-DUP-001",
                severidad="error",
                modulo="Expedientes",
                entidad="Expediente",
                registro=f"SP lógico {clave}",
                descripcion="Existen varios registros que representan el mismo No. de SP.",
                recomendacion="Revisar y consolidar manualmente antes de eliminar o fusionar cualquier registro.",
            ))

    return hallazgos
