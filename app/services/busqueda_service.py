from sqlalchemy import or_

from app.models.coordinacion import (
    ActividadCoordinacion,
    AnexoCoordinacion,
    DocumentoEmitido,
    MovimientoDispositivo,
    PagoCoordinacion,
    RegistroCoordinacion,
    RemisionCoordinacion,
    ReporteMonitoreo,
)
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.ubicacion import UbicacionFisica


LIMITE_POR_GRUPO = 15


def _resultado(categoria, titulo, detalle, endpoint, **params):
    return {
        "categoria": categoria,
        "titulo": titulo,
        "detalle": detalle,
        "endpoint": endpoint,
        "params": params,
    }


def buscar_global(texto):
    q = (texto or "").strip()
    if len(q) < 2:
        return []
    patron = f"%{q}%"
    resultados = []

    expedientes = Expediente.query.filter(or_(
        Expediente.no_sp.ilike(patron),
        Expediente.codigo_interno.ilike(patron),
        Expediente.nombre_referencia.ilike(patron),
        Expediente.nombres.ilike(patron),
        Expediente.apellidos.ilike(patron),
        Expediente.expediente_oj.ilike(patron),
        Expediente.telefono.ilike(patron),
    )).limit(LIMITE_POR_GRUPO).all()
    for item in expedientes:
        resultados.append(_resultado(
            "SP / Expediente",
            f"SP {item.no_sp} · {item.nombre_referencia or 'Sin nombre'}",
            f"{item.codigo_interno} · {item.disponibilidad}",
            "expedientes.detalle",
            expediente_id=item.id,
        ))

    documentos = DocumentoExpediente.query.filter(or_(
        DocumentoExpediente.nombre_documento.ilike(patron),
        DocumentoExpediente.tipo_documento.ilike(patron),
        DocumentoExpediente.estado_revision.ilike(patron),
    )).limit(LIMITE_POR_GRUPO).all()
    for item in documentos:
        resultados.append(_resultado(
            "Índice documental",
            item.nombre_documento,
            f"SP {item.expediente.no_sp} · folios {item.folio_inicio}-{item.folio_fin}",
            "indice_documental.listado",
            expediente_id=item.expediente_id,
        ))

    prestamos = PrestamoExpediente.query.filter(or_(
        PrestamoExpediente.numero_control.ilike(patron),
        PrestamoExpediente.solicitante.ilike(patron),
        PrestamoExpediente.persona_entrega.ilike(patron),
        PrestamoExpediente.persona_recibe.ilike(patron),
    )).limit(LIMITE_POR_GRUPO).all()
    for item in prestamos:
        resultados.append(_resultado(
            "Préstamo",
            item.numero_control,
            f"SP {item.expediente.no_sp} · {item.solicitante} · {item.estado}",
            "prestamos.detalle",
            prestamo_id=item.id,
        ))

    ubicaciones = UbicacionFisica.query.filter(or_(
        UbicacionFisica.archivador.ilike(patron),
        UbicacionFisica.sicoin.ilike(patron),
        UbicacionFisica.estante.ilike(patron),
        UbicacionFisica.caja.ilike(patron),
        UbicacionFisica.modulo.ilike(patron),
        UbicacionFisica.posicion.ilike(patron),
    )).limit(LIMITE_POR_GRUPO).all()
    for item in ubicaciones:
        resultados.append(_resultado(
            "Ubicación",
            f"SP {item.expediente.no_sp}",
            " · ".join(filter(None, [item.archivador, item.estante, item.caja, item.modulo, item.posicion])) or "Ubicación sin detalle",
            "expedientes.detalle",
            expediente_id=item.expediente_id,
        ))

    registros = RegistroCoordinacion.query.filter(or_(
        RegistroCoordinacion.no_sp_referencia.ilike(patron),
        RegistroCoordinacion.rc.ilike(patron),
        RegistroCoordinacion.providencia.ilike(patron),
        RegistroCoordinacion.observaciones.ilike(patron),
    )).limit(LIMITE_POR_GRUPO).all()
    ids_coord = {item.id for item in registros}

    detalles = []
    detalles.extend(PagoCoordinacion.query.filter(PagoCoordinacion.boleta.ilike(patron)).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(MovimientoDispositivo.query.filter(MovimientoDispositivo.descripcion.ilike(patron)).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(AnexoCoordinacion.query.filter(or_(AnexoCoordinacion.tipo_anexo.ilike(patron), AnexoCoordinacion.numero_anexo.ilike(patron))).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(ReporteMonitoreo.query.filter(or_(ReporteMonitoreo.numero_reporte.ilike(patron), ReporteMonitoreo.tipo_evento.ilike(patron))).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(DocumentoEmitido.query.filter(or_(DocumentoEmitido.numero_documento.ilike(patron), DocumentoEmitido.destino.ilike(patron), DocumentoEmitido.descripcion.ilike(patron))).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(ActividadCoordinacion.query.filter(or_(ActividadCoordinacion.tipo_actividad.ilike(patron), ActividadCoordinacion.area_apoyo.ilike(patron), ActividadCoordinacion.descripcion.ilike(patron))).limit(LIMITE_POR_GRUPO).all())
    detalles.extend(RemisionCoordinacion.query.filter(or_(RemisionCoordinacion.numero_control.ilike(patron), RemisionCoordinacion.destino.ilike(patron))).limit(LIMITE_POR_GRUPO).all())

    for detalle in detalles:
        registro = detalle.registro
        if registro.id not in ids_coord:
            registros.append(registro)
            ids_coord.add(registro.id)

    for item in registros[:30]:
        resultados.append(_resultado(
            "Coordinación",
            f"{item.tipo} · SP {item.no_sp_referencia or '—'}",
            f"RC {item.rc or '—'} · Providencia {item.providencia or '—'} · {item.estado}",
            "coordinacion.detalle",
            registro_id=item.id,
        ))

    return resultados[:80]
