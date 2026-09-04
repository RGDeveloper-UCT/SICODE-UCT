from collections import defaultdict

from app.checks import HallazgoIntegridad
from app.models.documento_expediente import DocumentoExpediente
from app.services.foliacion_service import analizar_secuencia_principal


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
        analisis = analizar_secuencia_principal(documentos)

        for anterior, documento in analisis["traslapes"]:
            hallazgos.append(HallazgoIntegridad(
                codigo="FOL-TRASLAPE-001",
                severidad="error",
                modulo="Índice documental",
                entidad="Expediente",
                registro=f"Expediente ID {expediente_id}",
                descripcion=(
                    f"Traslape en la foliación general entre '{anterior.nombre_documento}' "
                    f"({anterior.folio_inicio}-{anterior.folio_fin}) y '{documento.nombre_documento}' "
                    f"({documento.folio_inicio}-{documento.folio_fin})."
                ),
                recomendacion=(
                    "Verificar físicamente la foliación del cuerpo principal y corregir uno de los rangos. "
                    "Los anexos no se comparan aquí porque poseen foliación independiente."
                ),
            ))

        for inicio, fin in analisis["saltos"]:
            hallazgos.append(HallazgoIntegridad(
                codigo="FOL-SALTO-001",
                severidad="advertencia",
                modulo="Índice documental",
                entidad="Expediente",
                registro=f"Expediente ID {expediente_id}",
                descripcion=f"Salto de foliación general entre los folios {inicio} y {fin}.",
                recomendacion="Confirmar si el salto es válido o si falta registrar un documento/rango del cuerpo principal.",
            ))

    return hallazgos
