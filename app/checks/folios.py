from collections import defaultdict

from app.checks import HallazgoIntegridad
from app.models.documento_expediente import DocumentoExpediente


def ejecutar():
    hallazgos = []
    por_expediente = defaultdict(list)

    for documento in DocumentoExpediente.query.filter_by(activo=True).order_by(
        DocumentoExpediente.expediente_id.asc(),
        DocumentoExpediente.folio_inicio.asc(),
    ).all():
        por_expediente[documento.expediente_id].append(documento)

        if documento.folio_inicio < 1 or documento.folio_fin < documento.folio_inicio:
            hallazgos.append(HallazgoIntegridad(
                codigo="FOL-RANGO-001",
                severidad="error",
                modulo="Índice documental",
                entidad="DocumentoExpediente",
                registro=f"Documento {documento.id}",
                descripcion=f"Rango de folios inválido: {documento.folio_inicio}-{documento.folio_fin}.",
                recomendacion="Corregir el rango después de verificar el expediente físico.",
            ))

        calculado = documento.folio_fin - documento.folio_inicio + 1
        if documento.total_folios != calculado:
            hallazgos.append(HallazgoIntegridad(
                codigo="FOL-TOTAL-001",
                severidad="error",
                modulo="Índice documental",
                entidad="DocumentoExpediente",
                registro=f"Documento {documento.id}",
                descripcion=f"Total almacenado {documento.total_folios} no coincide con el rango ({calculado}).",
                recomendacion="Recalcular el total a partir del rango; no editar ambos valores independientemente.",
            ))

    for expediente_id, documentos in por_expediente.items():
        anterior = None
        for documento in documentos:
            if anterior:
                if documento.folio_inicio <= anterior.folio_fin:
                    hallazgos.append(HallazgoIntegridad(
                        codigo="FOL-TRASLAPE-001",
                        severidad="error",
                        modulo="Índice documental",
                        entidad="Expediente",
                        registro=f"Expediente ID {expediente_id}",
                        descripcion=(
                            f"Traslape entre '{anterior.nombre_documento}' ({anterior.folio_inicio}-{anterior.folio_fin}) "
                            f"y '{documento.nombre_documento}' ({documento.folio_inicio}-{documento.folio_fin})."
                        ),
                        recomendacion="Verificar físicamente la foliación y corregir uno de los rangos.",
                    ))
                elif documento.folio_inicio > anterior.folio_fin + 1:
                    hallazgos.append(HallazgoIntegridad(
                        codigo="FOL-SALTO-001",
                        severidad="advertencia",
                        modulo="Índice documental",
                        entidad="Expediente",
                        registro=f"Expediente ID {expediente_id}",
                        descripcion=f"Salto de foliación entre {anterior.folio_fin} y {documento.folio_inicio}.",
                        recomendacion="Confirmar si el salto es válido o si falta registrar un documento/rango.",
                    ))
            anterior = documento

    return hallazgos
