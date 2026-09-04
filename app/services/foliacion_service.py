from __future__ import annotations


def es_foliacion_principal(documento):
    """Los registros históricos con ``es_anexo`` NULL pertenecen al cuerpo principal."""
    return not bool(documento.es_anexo)


def separar_ambitos(documentos):
    """Separa el cuerpo principal de los anexos.

    Regla institucional: el expediente principal comparte una sola secuencia de
    folios. Cada anexo posee su propia foliación independiente y por ello nunca
    debe compararse contra el cuerpo principal ni contra otro anexo.
    """
    principales = [documento for documento in documentos if es_foliacion_principal(documento)]
    anexos = [documento for documento in documentos if bool(documento.es_anexo)]
    return principales, anexos


def analizar_secuencia_principal(documentos):
    """Detecta saltos y traslapes reales en la foliación del cuerpo principal.

    El algoritmo conserva el intervalo que alcanza el mayor folio visto. Esto
    evita perder traslapes anidados como 1-100, 2-3, 4-5.
    """
    principales, _ = separar_ambitos(documentos)
    ordenados = sorted(
        principales,
        key=lambda documento: (documento.folio_inicio, documento.folio_fin, documento.id or 0),
    )

    traslapes = []
    saltos = []
    cobertura_fin = None
    documento_cobertura = None

    for documento in ordenados:
        if cobertura_fin is None:
            cobertura_fin = documento.folio_fin
            documento_cobertura = documento
            continue

        if documento.folio_inicio <= cobertura_fin:
            traslapes.append((documento_cobertura, documento))
        elif documento.folio_inicio > cobertura_fin + 1:
            saltos.append((cobertura_fin + 1, documento.folio_inicio - 1))

        if documento.folio_fin > cobertura_fin:
            cobertura_fin = documento.folio_fin
            documento_cobertura = documento

    return {
        "documentos": ordenados,
        "traslapes": traslapes,
        "saltos": saltos,
        "ultimo_folio": max((documento.folio_fin for documento in ordenados), default=0),
        "total_folios_registrados": sum(documento.total_folios or 0 for documento in ordenados),
    }
