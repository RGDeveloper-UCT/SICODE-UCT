from sqlalchemy import func

from app import db
from app.checks import HallazgoIntegridad
from app.models.alerta import Alerta
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente


def ejecutar():
    hallazgos = []

    duplicados = (
        db.session.query(
            RegistroCoordinacion.expediente_id,
            AnexoCoordinacion.numero_anexo,
            func.count(AnexoCoordinacion.id).label("cantidad"),
        )
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id.isnot(None),
            AnexoCoordinacion.numero_anexo.isnot(None),
        )
        .group_by(RegistroCoordinacion.expediente_id, AnexoCoordinacion.numero_anexo)
        .having(func.count(AnexoCoordinacion.id) > 1)
        .all()
    )
    for expediente_id, numero, cantidad in duplicados:
        hallazgos.append(HallazgoIntegridad(
            codigo="ANX-DUP-001",
            severidad="error",
            modulo="Anexos",
            entidad="Expediente",
            registro=f"Expediente ID {expediente_id}",
            descripcion=f"El Anexo {numero} aparece individualizado {cantidad} veces para el mismo SP.",
            recomendacion="Revisar los registros contra File Server y anular/corregir el duplicado conservando trazabilidad.",
        ))

    anexos = (
        db.session.query(AnexoCoordinacion, RegistroCoordinacion, DocumentoExpediente)
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .outerjoin(DocumentoExpediente, AnexoCoordinacion.documento_expediente_id == DocumentoExpediente.id)
        .all()
    )
    maximo_por_expediente = {}

    for anexo, registro, documento in anexos:
        numero_texto = str(anexo.numero_anexo or "").strip()
        if numero_texto:
            try:
                numero = int(numero_texto)
            except ValueError:
                hallazgos.append(HallazgoIntegridad(
                    codigo="ANX-NUM-001",
                    severidad="advertencia",
                    modulo="Anexos",
                    entidad="AnexoCoordinacion",
                    registro=f"Anexo ID {anexo.id}",
                    descripcion=f"Número de anexo no numérico: '{numero_texto}'.",
                    recomendacion="Confirmar el número físico y normalizarlo según la secuencia institucional.",
                ))
            else:
                if numero < 1 or numero > 200:
                    hallazgos.append(HallazgoIntegridad(
                        codigo="ANX-NUM-002",
                        severidad="error",
                        modulo="Anexos",
                        entidad="AnexoCoordinacion",
                        registro=f"Anexo ID {anexo.id}",
                        descripcion=f"Número de anexo fuera del rango operativo: {numero}.",
                        recomendacion="Confirmar el número contra File Server antes de corregir el registro.",
                    ))
                if registro.expediente_id is not None:
                    maximo_por_expediente[registro.expediente_id] = max(
                        maximo_por_expediente.get(registro.expediente_id, 0), numero
                    )

        if anexo.documento_expediente_id is not None:
            if documento is None:
                hallazgos.append(HallazgoIntegridad(
                    codigo="ANX-VINC-001",
                    severidad="error",
                    modulo="Anexos",
                    entidad="AnexoCoordinacion",
                    registro=f"Anexo ID {anexo.id}",
                    descripcion="El anexo apunta a un documento del índice que ya no existe.",
                    recomendacion="Restablecer el vínculo únicamente después de verificar el expediente físico.",
                ))
            elif not documento.activo:
                hallazgos.append(HallazgoIntegridad(
                    codigo="ANX-VINC-002",
                    severidad="error",
                    modulo="Anexos",
                    entidad="AnexoCoordinacion",
                    registro=f"Anexo ID {anexo.id}",
                    descripcion=f"El anexo sigue vinculado al documento anulado {documento.id}.",
                    recomendacion="Liberar el vínculo para permitir una reincorporación correcta del anexo.",
                ))
            elif not documento.es_anexo:
                hallazgos.append(HallazgoIntegridad(
                    codigo="ANX-VINC-003",
                    severidad="error",
                    modulo="Anexos",
                    entidad="AnexoCoordinacion",
                    registro=f"Anexo ID {anexo.id}",
                    descripcion=f"El anexo está vinculado a un documento {documento.id} que no está marcado como Anexo.",
                    recomendacion="Corregir el ámbito documental después de verificar físicamente la foliación.",
                ))

    if maximo_por_expediente:
        expedientes = Expediente.query.filter(Expediente.id.in_(maximo_por_expediente)).all()
        for expediente in expedientes:
            maximo = maximo_por_expediente[expediente.id]
            if expediente.anexos_rectificados is not None and expediente.anexos_rectificados < maximo:
                hallazgos.append(HallazgoIntegridad(
                    codigo="ANX-SEQ-001",
                    severidad="error",
                    modulo="Anexos",
                    entidad="Expediente",
                    registro=f"SP {expediente.no_sp}",
                    descripcion=(
                        f"El total rectificado indica {expediente.anexos_rectificados} anexo(s), "
                        f"pero existe evidencia individualizada hasta el Anexo {maximo}."
                    ),
                    recomendacion="Rectificar el total contra File Server; nunca reducirlo por debajo de la evidencia existente.",
                ))

    contradicciones = (
        db.session.query(Alerta, DocumentoExpediente)
        .join(DocumentoExpediente, Alerta.documento_id == DocumentoExpediente.id)
        .filter(
            Alerta.tipo_alerta == "REVISION_INDICE_DOCUMENTAL",
            Alerta.estado.in_(["Abierta", "En revisión"]),
            DocumentoExpediente.activo.is_(True),
            DocumentoExpediente.estado_revision == "Verificado",
        )
        .all()
    )
    for alerta, documento in contradicciones:
        hallazgos.append(HallazgoIntegridad(
            codigo="ANX-ALERTA-001",
            severidad="error",
            modulo="Anexos",
            entidad="DocumentoExpediente",
            registro=f"Documento {documento.id}",
            descripcion=(
                f"'{documento.nombre_documento}' figura Verificado, pero conserva abierta la alerta "
                f"de revisión {alerta.id}."
            ),
            recomendacion="Revisar la resolución: corregir la alerta o devolver el documento a un estado de incidencia con trazabilidad.",
        ))

    return hallazgos
