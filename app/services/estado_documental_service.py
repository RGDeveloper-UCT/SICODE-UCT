from datetime import datetime


TIPOS_VERIFICACION_DOCUMENTAL = {"DOCUMENTAL", "INTEGRAL"}
ESTADOS_DOCUMENTO_CON_INCIDENCIA = {"Mal foliado", "Anexo pendiente", "Con observaciones"}


def _fecha_documento(documento):
    return documento.actualizado_en or documento.creado_en


def _ultima_fecha(valores):
    fechas = [valor for valor in valores if valor is not None]
    return max(fechas) if fechas else None


def _ultima_verificacion(expediente, tipos=None):
    verificaciones = list(expediente.verificaciones or [])
    if tipos is not None:
        verificaciones = [item for item in verificaciones if item.tipo in tipos]
    if not verificaciones:
        return None
    return max(verificaciones, key=lambda item: item.creado_en or datetime.min)


def calcular_estado_documental(expediente):
    """Construye la vista documental canónica de un SP sin modificar datos.

    Árbol de autoridad:
      Expediente -> existencia física -> Índice documental -> rectificación ->
      verificación -> estado documental derivado.

    La columna histórica ``estado_fisico_documental`` se conserva en base de
    datos únicamente por compatibilidad y auditoría; no decide el estado
    vigente devuelto por este servicio.
    """
    documentos = sorted(
        [doc for doc in expediente.documentos_indice if doc.activo],
        key=lambda doc: (doc.folio_inicio, doc.folio_fin, doc.id),
    )
    anexos_indice = [doc for doc in documentos if doc.es_anexo]

    total_documentos = len(documentos)
    total_folios_documentados = sum(doc.total_folios or 0 for doc in documentos)
    ultimo_folio_indice = max((doc.folio_fin for doc in documentos), default=0)

    incidencias = []
    saltos = []
    traslapes = []
    anterior = None
    for documento in documentos:
        if documento.estado_revision in ESTADOS_DOCUMENTO_CON_INCIDENCIA:
            incidencias.append(
                f"{documento.nombre_documento}: {documento.estado_revision}"
            )
        if anterior:
            if documento.folio_inicio <= anterior.folio_fin:
                traslapes.append(
                    f"{anterior.folio_inicio}-{anterior.folio_fin} / "
                    f"{documento.folio_inicio}-{documento.folio_fin}"
                )
            elif documento.folio_inicio > anterior.folio_fin + 1:
                saltos.append(f"{anterior.folio_fin + 1}-{documento.folio_inicio - 1}")
        anterior = documento

    if traslapes:
        incidencias.append("Índice con rangos traslapados")
    if saltos:
        incidencias.append("Índice con saltos de foliación")

    folios_rectificados = expediente.folios_rectificados
    anexos_rectificados = expediente.anexos_rectificados
    coincide_foliacion = None
    if folios_rectificados is not None and documentos:
        # La rectificación expresa la cantidad física total del expediente;
        # el último número foliado es la comparación documental más estable.
        coincide_foliacion = folios_rectificados == ultimo_folio_indice
        if not coincide_foliacion:
            incidencias.append(
                f"Rectificación física ({folios_rectificados}) no coincide con "
                f"último folio del índice ({ultimo_folio_indice})"
            )

    coincide_anexos = None
    if anexos_rectificados is not None:
        coincide_anexos = anexos_rectificados == len(anexos_indice)
        if not coincide_anexos:
            incidencias.append(
                f"Anexos rectificados ({anexos_rectificados}) no coinciden con "
                f"anexos indexados ({len(anexos_indice)})"
            )

    ultima_modificacion_indice = _ultima_fecha(_fecha_documento(doc) for doc in documentos)
    ultima_modificacion_documental = _ultima_fecha(
        [ultima_modificacion_indice, expediente.rectificado_en]
    )

    ultima_verificacion_documental = _ultima_verificacion(
        expediente, TIPOS_VERIFICACION_DOCUMENTAL
    )
    ultima_verificacion_general = _ultima_verificacion(expediente)

    verificacion_vigente = False
    if ultima_verificacion_documental and ultima_verificacion_documental.creado_en:
        verificacion_vigente = (
            ultima_modificacion_documental is None
            or ultima_verificacion_documental.creado_en >= ultima_modificacion_documental
        )

    if not expediente.expediente_fisico_registrado:
        estado = "Sin expediente físico"
        origen_estado = "EXISTENCIA_FISICA"
    elif not documentos:
        estado = "Pendiente de indexación"
        origen_estado = "INDICE_DOCUMENTAL"
    elif (
        ultima_verificacion_general
        and ultima_verificacion_general.resultado == "No localizado"
        and (
            ultima_verificacion_documental is None
            or (ultima_verificacion_general.creado_en or datetime.min)
            >= (ultima_verificacion_documental.creado_en or datetime.min)
        )
    ):
        estado = "No localizado"
        origen_estado = "VERIFICACION"
    elif not ultima_verificacion_documental:
        estado = "Pendiente de verificación"
        origen_estado = "VERIFICACION"
    elif not verificacion_vigente:
        estado = "Verificación desactualizada"
        origen_estado = "VIGENCIA"
    else:
        estado = ultima_verificacion_documental.resultado
        origen_estado = "VERIFICACION"
        if estado == "Verificado" and incidencias:
            estado = "Con observaciones"
            origen_estado = "INTEGRIDAD_DOCUMENTAL"

    return {
        "estado": estado,
        "origen_estado": origen_estado,
        "expediente_fisico": bool(expediente.expediente_fisico_registrado),
        "documentos": total_documentos,
        "folios_documentados": total_folios_documentados,
        "ultimo_folio_indice": ultimo_folio_indice,
        "folios_rectificados": folios_rectificados,
        "coincide_foliacion": coincide_foliacion,
        "anexos_indexados": len(anexos_indice),
        "anexos_rectificados": anexos_rectificados,
        "coincide_anexos": coincide_anexos,
        "incidencias": incidencias,
        "saltos": saltos,
        "traslapes": traslapes,
        "ultima_modificacion_indice": ultima_modificacion_indice,
        "ultima_modificacion_documental": ultima_modificacion_documental,
        "ultima_verificacion": ultima_verificacion_documental,
        "verificacion_vigente": verificacion_vigente,
        "estado_legacy": getattr(expediente, "_estado_fisico_documental_legacy", None),
    }


def estado_documental_actual(expediente):
    return calcular_estado_documental(expediente)["estado"]
