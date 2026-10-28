"""Diagnóstico agregado, memoria de propuestas y revisión programable de NEXO.

No se accede a textos de expedientes, documentos, nombres o identificadores de SP.
Las propuestas no alteran registros operativos.
"""
import hashlib
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app import db
from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.nexo import NexoPropuesta
from app.models.prestamo import PrestamoExpediente


ESTADOS_PROPUESTA = {"nueva", "en_revision", "aprobada", "descartada", "implementada"}
PRIORIDADES = {"alta", "media", "baja"}


def indicadores():
    """Sólo cifras agregadas. No realiza una consulta arbitraria formulada por IA."""
    expedientes = Expediente.query.count()
    return {
        "expedientes_total": expedientes,
        "expedientes_sin_fisico": Expediente.query.filter(
            Expediente.expediente_fisico_registrado.is_(False),
        ).count(),
        "expedientes_sin_rectificacion": Expediente.query.filter(
            Expediente.expediente_fisico_registrado.is_(True),
            db.or_(Expediente.folios_rectificados.is_(None),
                   Expediente.anexos_rectificados.is_(None)),
        ).count(),
        "documentos_indice": DocumentoExpediente.query.filter_by(activo=True).count(),
        "documentos_rango_invalido": DocumentoExpediente.query.filter(
            DocumentoExpediente.activo.is_(True),
            db.or_(DocumentoExpediente.folio_inicio <= 0,
                   DocumentoExpediente.folio_fin < DocumentoExpediente.folio_inicio,
                   DocumentoExpediente.total_folios !=
                   DocumentoExpediente.folio_fin - DocumentoExpediente.folio_inicio + 1),
        ).count(),
        "prestamos_vencidos": PrestamoExpediente.query.filter(
            PrestamoExpediente.activo.is_(True),
            PrestamoExpediente.fecha_real_devolucion.is_(None),
            PrestamoExpediente.fecha_estimada_devolucion < date.today(),
        ).count(),
        "alertas_abiertas": Alerta.query.filter(
            func.lower(Alerta.estado).notin_(["cerrada", "corregida", "cerrado"]),
        ).count(),
    }


def detectar_propuestas(datos):
    """Recomendaciones reproducibles con umbrales explícitos y evidencia numérica."""
    reglas = (
        ("expedientes_sin_fisico", "Expedientes",
         "SP sin expediente físico registrado",
         "Existen sujetos portadores sin expediente físico registrado o localizado.",
         "Revisar la recepción física y el seguimiento de expedientes pendientes.", "media"),
        ("expedientes_sin_rectificacion", "Expedientes",
         "Rectificación documental incompleta",
         "Existen expedientes físicos sin rectificación completa de folios o anexos.",
         "Priorizar rectificaciones pendientes antes de movimientos y nuevas incorporaciones.", "alta"),
        ("documentos_rango_invalido", "Índice documental",
         "Rangos de foliación inconsistentes",
         "Hay registros del índice con folios o totales aritméticamente inconsistentes.",
         "Revisar los rangos señalados mediante el control de integridad institucional.", "alta"),
        ("prestamos_vencidos", "Préstamos",
         "Devoluciones de expedientes atrasadas",
         "Existen préstamos sin devolución registrados después de su fecha prevista.",
         "Revisar y dar seguimiento a las devoluciones mediante el módulo de préstamos.", "alta"),
        ("alertas_abiertas", "Alertas",
         "Alertas administrativas pendientes",
         "Existen alertas que todavía requieren revisión o cierre.",
         "Clasificar las alertas abiertas y asignar seguimiento según su gravedad.", "media"),
    )
    propuestas = []
    for clave, modulo, titulo, detalle, accion, prioridad in reglas:
        total = int(datos.get(clave, 0))
        if total <= 0:
            continue
        propuestas.append({
            "categoria": "integridad" if clave in {"documentos_rango_invalido", "expedientes_sin_rectificacion"} else "operacion",
            "modulo": modulo, "titulo": titulo,
            "detalle": f"{detalle} Registros observados: {total}.",
            "recomendacion": accion, "prioridad": prioridad,
            "evidencia": {"indicador": clave, "cantidad": total},
        })
    return propuestas


def guardar_propuestas(propuestas):
    """Deduplica por regla y módulo; no reabre decisiones anteriores."""
    nuevas = 0
    ahora = datetime.utcnow()
    for item in propuestas:
        firma = hashlib.sha256(
            f"{item['modulo']}|{item['titulo']}|{item['categoria']}".encode("utf-8")
        ).hexdigest()[:40]
        existente = NexoPropuesta.query.filter_by(firma=firma).first()
        if existente:
            # Una revisión repetida sin cambios no infla artificialmente la actividad.
            if existente.evidencia != item["evidencia"]:
                existente.evidencia = item["evidencia"]
                existente.detalle = item["detalle"]
                existente.apariciones = int(existente.apariciones or 0) + 1
                existente.observado_en = ahora
            continue
        db.session.add(NexoPropuesta(
            firma=firma, categoria=item["categoria"], modulo=item["modulo"],
            titulo=item["titulo"], detalle=item["detalle"],
            recomendacion=item["recomendacion"],
            prioridad=item["prioridad"] if item["prioridad"] in PRIORIDADES else "media",
            evidencia=item["evidencia"], estado="nueva",
        ))
        nuevas += 1
    if nuevas or db.session.dirty:
        db.session.commit()
    return nuevas


def resumen_propuestas(limite=30):
    propuestas = (
        NexoPropuesta.query.order_by(NexoPropuesta.observado_en.desc(), NexoPropuesta.id.desc())
        .limit(min(int(limite), 100)).all()
    )
    estados = {estado: 0 for estado in sorted(ESTADOS_PROPUESTA)}
    for estado, cantidad in db.session.query(
        NexoPropuesta.estado, func.count(NexoPropuesta.id)
    ).group_by(NexoPropuesta.estado).all():
        estados[estado] = cantidad
    return {"total": sum(estados.values()), "por_estado": estados,
            "propuestas": [p.como_dict() for p in propuestas]}


def ultima_revision():
    evento = (Bitacora.query.filter_by(accion="NEXO_REVISION_AUTOMATICA")
              .order_by(Bitacora.id.desc()).first())
    return evento.creado_en.isoformat() + "Z" if evento else None


def actualizar_estado(propuesta_id, estado, usuario_id, resultado=""):
    if estado not in ESTADOS_PROPUESTA:
        raise ValueError("Estado de propuesta no permitido")
    propuesta = db.session.get(NexoPropuesta, propuesta_id)
    if propuesta is None:
        return None
    anterior = propuesta.estado
    propuesta.estado = estado
    propuesta.revisado_en = datetime.utcnow()
    propuesta.revisado_por_id = usuario_id
    propuesta.resultado = str(resultado or "").strip()[:240] or None
    db.session.add(Bitacora(
        usuario_id=usuario_id, accion="NEXO_PROPUESTA_REVISION",
        modulo="NEXO", entidad="NexoPropuesta", entidad_id=str(propuesta.id),
        descripcion=f"Propuesta {propuesta.id}: {anterior} -> {estado}",
        datos_anteriores={"estado": anterior},
        datos_posteriores={"estado": estado},
        motivo="Revisión exclusiva de administración",
    ))
    db.session.commit()
    return propuesta.como_dict()


def ejecutar_revision(usuario_id=None, origen="programada"):
    """Rutina idempotente invocable por CLI o administrador."""
    from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes
    from app.services.cerebro_sicode_schema import inventariar_esquema_sicode
    from app.services.cerebro_sicode_service import analizar_sicode, guardar_hallazgos

    aprendidas = absorber_verificaciones_pendientes(usuario_id=usuario_id)
    esquema = inventariar_esquema_sicode(usuario_id=usuario_id)
    analisis = analizar_sicode()
    hallazgos_nuevos = guardar_hallazgos(analisis, usuario_id=usuario_id)
    datos = indicadores()
    nuevas = guardar_propuestas(detectar_propuestas(datos))
    db.session.add(Bitacora(
        usuario_id=usuario_id, accion="NEXO_REVISION_AUTOMATICA",
        modulo="NEXO", entidad="CerebroSicode",
        descripcion="NEXO completó una revisión de metadatos agregados.",
        datos_posteriores={
            "origen": origen[:20], "aprendizajes_nuevos": aprendidas,
            "hallazgos_nuevos": hallazgos_nuevos,
            "propuestas_nuevas": nuevas,
            "indicadores": datos,
            "cambio_esquema": bool(esquema.get("cambio_detectado")),
        },
        motivo="Análisis institucional sin modificación de expedientes",
    ))
    db.session.commit()
    return {"aprendizajes_nuevos": aprendidas,
            "hallazgos_nuevos": hallazgos_nuevos,
            "propuestas_nuevas": nuevas, "indicadores": datos}



def actividad_reciente(dias=7):
    """Evolución comprobable: ejecuciones y cambios en los últimos días."""
    desde = datetime.utcnow() - timedelta(days=max(1, min(int(dias), 31)))
    eventos = (Bitacora.query.filter_by(accion="NEXO_REVISION_AUTOMATICA")
               .filter(Bitacora.creado_en >= desde)
               .order_by(Bitacora.id.desc()).limit(200).all())
    return {
        "dias": dias, "revisiones": len(eventos),
        "aprendizajes": sum(int((e.datos_posteriores or {}).get("aprendizajes_nuevos") or 0)
                            for e in eventos),
        "propuestas_nuevas": sum(int((e.datos_posteriores or {}).get("propuestas_nuevas") or 0)
                                for e in eventos),
        "hallazgos_nuevos": sum(int((e.datos_posteriores or {}).get("hallazgos_nuevos") or 0)
                              for e in eventos),
    }
