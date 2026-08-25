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

        resumen = expediente.estado_documental_resumen

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

            if resumen["documentos"] == 0:
                hallazgos.append(HallazgoIntegridad(
                    codigo="DOC-INDICE-001",
                    severidad="advertencia",
                    modulo="Estado documental",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="Existe expediente físico, pero todavía no posee documentos activos en el índice documental.",
                    recomendacion="Incorporar al índice cada documento que forme parte físicamente del expediente.",
                ))

            if resumen["coincide_foliacion"] is False:
                hallazgos.append(HallazgoIntegridad(
                    codigo="DOC-FOLIOS-001",
                    severidad="error",
                    modulo="Estado documental",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion=(
                        f"La rectificación registra {resumen['folios_rectificados']} folios, pero el índice "
                        f"termina en el folio {resumen['ultimo_folio_indice']}."
                    ),
                    recomendacion="Verificar físicamente el expediente y corregir el índice o realizar una nueva rectificación según corresponda.",
                ))

            if resumen["coincide_anexos"] is False:
                hallazgos.append(HallazgoIntegridad(
                    codigo="DOC-ANEXOS-001",
                    severidad="advertencia",
                    modulo="Estado documental",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion=(
                        f"La rectificación registra {resumen['anexos_rectificados']} anexos y el índice "
                        f"documental contiene {resumen['anexos_indexados']} anexos activos."
                    ),
                    recomendacion="Confirmar qué anexos forman parte del expediente e incorporarlos o rectificarlos sin duplicar registros.",
                ))

            if resumen["estado"] == "Verificación desactualizada":
                hallazgos.append(HallazgoIntegridad(
                    codigo="DOC-VIGENCIA-001",
                    severidad="advertencia",
                    modulo="Estado documental",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="La composición documental o la rectificación cambió después de la última verificación documental.",
                    recomendacion="Realizar una nueva verificación documental o integral después de confirmar los cambios del expediente.",
                ))

            if resumen["incidencias"]:
                hallazgos.append(HallazgoIntegridad(
                    codigo="DOC-INTEGRIDAD-001",
                    severidad="advertencia",
                    modulo="Estado documental",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="; ".join(resumen["incidencias"][:4]),
                    recomendacion="Resolver las incidencias desde el índice documental y confirmar posteriormente mediante verificación.",
                ))

            if not expediente.verificaciones:
                hallazgos.append(HallazgoIntegridad(
                    codigo="EXP-VERIF-001",
                    severidad="advertencia",
                    modulo="Expedientes",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion="Expediente físico sin una verificación histórica registrada en el control documental.",
                    recomendacion="Registrar una verificación cuando corresponda; no inventar verificaciones históricas faltantes.",
                ))

        legacy = resumen.get("estado_legacy")
        if legacy and legacy != resumen["estado"]:
            hallazgos.append(HallazgoIntegridad(
                codigo="DOC-LEGACY-001",
                severidad="advertencia",
                modulo="Estado documental",
                entidad="Expediente",
                registro=f"SP {expediente.no_sp}",
                descripcion=(
                    f"El estado histórico almacenado es '{legacy}', mientras el estado derivado actual es "
                    f"'{resumen['estado']}'."
                ),
                recomendacion="No modificar el histórico. Utilizar el estado derivado y completar índice/rectificación/verificación si hace falta.",
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
