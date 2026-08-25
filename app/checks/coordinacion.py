from app.checks import HallazgoIntegridad
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, RemisionExpediente
from app.models.documento_expediente import DocumentoExpediente
from app.services.sp_service import normalizar_sp


TIPOS_ENTRANTES = {
    "PAGO",
    "INSTALACION",
    "DESINSTALACION",
    "ANEXO",
    "MONITOREO",
    "EXPEDIENTE_COMPLETO",
}


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

    # Expediente completo crea documentos hijos reales en el índice. Para
    # registros históricos anteriores a esta relación no se modifica nada; el
    # auditor solamente informa que su trazabilidad estructurada aún no existe.
    for registro in RegistroCoordinacion.query.filter_by(tipo="EXPEDIENTE_COMPLETO").all():
        documentos = DocumentoExpediente.query.filter_by(
            registro_coordinacion_id=registro.id
        ).all()
        if not documentos:
            hallazgos.append(HallazgoIntegridad(
                codigo="COORD-EXP-DOC-001",
                severidad="advertencia",
                modulo="Coordinación",
                entidad="RegistroCoordinacion",
                registro=f"Recepción expediente completo {registro.id}",
                descripcion="La recepción no tiene documentos del índice enlazados mediante la relación de origen estructurada.",
                recomendacion="Conservar el registro histórico. Solo vincularlo manualmente si la correspondencia documental puede confirmarse sin ambigüedad.",
            ))
        for documento in documentos:
            if registro.expediente_id != documento.expediente_id:
                hallazgos.append(HallazgoIntegridad(
                    codigo="COORD-EXP-DOC-002",
                    severidad="error",
                    modulo="Coordinación",
                    entidad="DocumentoExpediente",
                    registro=f"Documento {documento.id}",
                    descripcion="El documento generado por una recepción de expediente completo pertenece a un SP distinto al registro de origen.",
                    recomendacion="Revisar el vínculo de origen y el expediente antes de modificar cualquier registro.",
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
