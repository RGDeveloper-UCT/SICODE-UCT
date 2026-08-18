from app.checks import HallazgoIntegridad
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, RemisionExpediente
from app.services.sp_service import normalizar_sp


TIPOS_ENTRANTES = {"PAGO", "INSTALACION", "DESINSTALACION", "ANEXO", "MONITOREO"}


def ejecutar():
    hallazgos = []

    for registro in RegistroCoordinacion.query.filter(RegistroCoordinacion.estado != "Completo").all():
        severidad = "error" if registro.estado == "Pendiente de vincular" else "advertencia"
        hallazgos.append(HallazgoIntegridad(
            codigo="COORD-PEND-001",
            severidad=severidad,
            modulo="Coordinación",
            entidad="RegistroCoordinacion",
            registro=f"Registro {registro.id} · {registro.tipo}",
            descripcion=f"Registro operativo en estado '{registro.estado}'. SP: {registro.no_sp_referencia or 'Sin SP'}.",
            recomendacion="Completar o vincular la información pendiente desde Coordinación.",
        ))

    for registro in RegistroCoordinacion.query.filter(RegistroCoordinacion.tipo.in_(TIPOS_ENTRANTES)).all():
        # Los importados históricos no siempre contienen esta información; se
        # advierte, pero no se inventa ni bloquea la conservación del histórico.
        faltantes = []
        if not registro.persona_entrega:
            faltantes.append("quién entrega/remite")
        if not registro.folios_recepcion:
            faltantes.append("folios recibidos")
        if faltantes and registro.origen_registro == "MANUAL":
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-RECEP-001",
                severidad="advertencia",
                modulo="Coordinación",
                entidad="RegistroCoordinacion",
                registro=f"Registro {registro.id} · {registro.tipo}",
                descripcion="Recepción manual incompleta: falta " + " y ".join(faltantes) + ".",
                recomendacion="Completar los metadatos de recepción si la información está disponible.",
            ))

    for registro in RegistroCoordinacion.query.filter(RegistroCoordinacion.expediente_id.isnot(None)).all():
        if registro.no_sp_referencia and normalizar_sp(registro.no_sp_referencia) != normalizar_sp(registro.expediente.no_sp):
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-SP-001",
                severidad="error",
                modulo="Coordinación",
                entidad="RegistroCoordinacion",
                registro=f"Registro {registro.id}",
                descripcion=(
                    f"El SP de referencia ({registro.no_sp_referencia}) no coincide con el expediente vinculado "
                    f"(SP {registro.expediente.no_sp})."
                ),
                recomendacion="Revisar el vínculo; no corregir automáticamente sin confirmar el documento origen.",
            ))

    anexos = AnexoCoordinacion.query.all()
    for anexo in anexos:
        if anexo.registro.expediente_id and anexo.documento_expediente_id is None:
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-ANEXO-001",
                severidad="advertencia",
                modulo="Coordinación",
                entidad="AnexoCoordinacion",
                registro=f"Anexo {anexo.id} · SP {anexo.registro.no_sp_referencia or '—'}",
                descripcion="Anexo recibido y vinculado al SP, pero todavía no incorporado al índice documental.",
                recomendacion="Incorporarlo desde el Índice documental cuando forme parte del expediente físico.",
            ))
        if anexo.documento_expediente and anexo.registro.expediente_id != anexo.documento_expediente.expediente_id:
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-ANEXO-002",
                severidad="error",
                modulo="Coordinación",
                entidad="AnexoCoordinacion",
                registro=f"Anexo {anexo.id}",
                descripcion="El anexo de recepción está vinculado a un documento de otro expediente.",
                recomendacion="Revisar manualmente ambos vínculos antes de modificar la relación.",
            ))

    for detalle in RemisionExpediente.query.all():
        if detalle.expediente_id is None:
            continue
        if normalizar_sp(detalle.no_sp_referencia) != normalizar_sp(detalle.expediente.no_sp):
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-REM-001",
                severidad="error",
                modulo="Coordinación",
                entidad="RemisionExpediente",
                registro=f"Detalle remisión {detalle.id}",
                descripcion="El SP escrito en la remisión no coincide con el expediente vinculado.",
                recomendacion="Verificar el expediente físico y la remisión antes de corregir el vínculo.",
            ))

    return hallazgos
