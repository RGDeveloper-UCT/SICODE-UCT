"""Reglas de visibilidad, alertas y repetición de la Agenda UCT."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

from sqlalchemy import and_, or_
from app import db
from app.models.agenda import AgendaActividad, AgendaNotificacion, AgendaParticipante

TZ = ZoneInfo("America/Guatemala")


def ahora_gt():
    """Los DateTime de la agenda guardan hora civil de Guatemala."""
    return datetime.now(TZ).replace(tzinfo=None)


def fecha_local(texto):
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(str(texto))
        if dt.tzinfo:
            return dt.astimezone(TZ).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        raise ValueError("La fecha u hora no tiene un formato válido.")


def visible_query(usuario):
    compartidas = AgendaActividad.visibilidad == "equipo"
    vinculadas = or_(
        AgendaActividad.creado_por_id == usuario.id,
        AgendaActividad.responsable_id == usuario.id,
        AgendaActividad.id.in_(
            db.session.query(AgendaParticipante.actividad_id).filter(
                AgendaParticipante.usuario_id == usuario.id
            )
        ),
    )
    if not usuario.puede_modificar:
        return AgendaActividad.query.filter(compartidas)
    return AgendaActividad.query.filter(or_(compartidas, vinculadas))


def puede_ver(usuario, actividad):
    if actividad.visibilidad == "equipo":
        return True
    return usuario.puede_modificar and (
        actividad.creado_por_id == usuario.id or
        actividad.responsable_id == usuario.id or
        any(p.usuario_id == usuario.id for p in actividad.participantes)
    )


def puede_editar(usuario, actividad):
    return usuario.puede_modificar and (
        actividad.creado_por_id == usuario.id or
        actividad.responsable_id == usuario.id or
        any(p.usuario_id == usuario.id for p in actividad.participantes)
    )


def destinatarios(actividad):
    return set([actividad.creado_por_id, actividad.responsable_id] +
               [p.usuario_id for p in actividad.participantes])


def notificar(usuarios, actividad, titulo, mensaje, prioridad="media", obligatoria=False, clave=None, omitir=None):
    """Agrega avisos a la misma transacción; no provoca commit independiente."""
    for usuario_id in set(usuarios):
        if usuario_id == omitir:
            continue
        codigo = (clave or str(uuid4())) + ":" + str(usuario_id)
        if db.session.query(AgendaNotificacion.id).filter_by(clave=codigo).first():
            continue
        db.session.add(AgendaNotificacion(
            usuario_id=usuario_id, actividad_id=actividad.id if actividad else None,
            clave=codigo, titulo=titulo[:180], mensaje=mensaje[:2000],
            prioridad=prioridad, obligatoria=obligatoria,
            creada_en=datetime.utcnow(),
        ))


def alertas_de_plazo(usuario_id):
    """Crear una sola alerta obligatoria por fecha y responsable si vence pronto."""
    limite = ahora_gt() + timedelta(days=3)
    trabajos = (
        AgendaActividad.query
        .filter(AgendaActividad.estado.notin_(("finalizada", "cancelada")))
        .filter(AgendaActividad.vencimiento.isnot(None),
                AgendaActividad.vencimiento <= limite,
                AgendaActividad.prioridad.in_(("alta", "media")))
        .filter(or_(
            AgendaActividad.creado_por_id == usuario_id,
            AgendaActividad.responsable_id == usuario_id,
            AgendaActividad.id.in_(
                db.session.query(AgendaParticipante.actividad_id).filter(
                    AgendaParticipante.usuario_id == usuario_id
                )
            ),
        )).limit(150).all()
    )
    nuevo = False
    for tarea in trabajos:
        clave = "plazo:%s:%s:%s" % (tarea.id, tarea.vencimiento.isoformat(), usuario_id)
        if AgendaNotificacion.query.filter_by(clave=clave).first():
            continue
        vencida = tarea.vencimiento < ahora_gt()
        prioridad = "alta" if vencida or (tarea.prioridad == "alta" and tarea.vencimiento <= ahora_gt() + timedelta(days=1)) else "media"
        db.session.add(AgendaNotificacion(
            usuario_id=usuario_id, actividad_id=tarea.id,
            clave=clave, titulo=("Actividad vencida: " if vencida else "Actividad próxima: ") + tarea.titulo[:158],
            mensaje="Vencimiento: " + tarea.vencimiento.strftime("%d/%m/%Y %H:%M") + " (Guatemala)",
            prioridad=prioridad, obligatoria=True, creada_en=datetime.utcnow(),
        ))
        nuevo = True
    if nuevo:
        db.session.commit()


def avisos_usuario(usuario_id, obligatorios=False):
    consulta = AgendaNotificacion.query.filter_by(usuario_id=usuario_id)
    if obligatorios:
        consulta = consulta.filter(
            AgendaNotificacion.obligatoria.is_(True),
            AgendaNotificacion.confirmada_en.is_(None),
        )
    else:
        consulta = consulta.filter(AgendaNotificacion.leida_en.is_(None))
    avisos = consulta.order_by(AgendaNotificacion.creada_en.desc()).limit(100).all()
    # Ignorar recordatorios correspondientes a vencimientos anteriores tras reprogramación.
    return [a for a in avisos if not a.clave.startswith("plazo:") or (
        a.actividad is not None and a.actividad.estado not in ("finalizada", "cancelada") and
        a.actividad.vencimiento and a.actividad.vencimiento.isoformat() in a.clave
    )]


def aviso_json(aviso):
    return {
        "id": aviso.id, "titulo": aviso.titulo, "mensaje": aviso.mensaje,
        "prioridad": aviso.prioridad, "obligatoria": aviso.obligatoria,
        "actividad_id": aviso.actividad_id,
        "creada_en": aviso.creada_en.isoformat(),
    }


def siguiente_repeticion(actividad):
    """Crea la próxima ocurrencia solo al finalizar; nunca duplica en cada consulta."""
    from dateutil.relativedelta import relativedelta
    intervalo = {
        "diaria": relativedelta(days=1),
        "semanal": relativedelta(weeks=1),
        "mensual": relativedelta(months=1),
        "anual": relativedelta(years=1),
        "laboral": relativedelta(days=1),
    }.get(actividad.recurrencia)
    if not intervalo or not actividad.vencimiento:
        return None
    nueva_fecha = actividad.vencimiento + intervalo
    if actividad.recurrencia == "laboral":
        while nueva_fecha.weekday() >= 5:
            nueva_fecha += timedelta(days=1)
    comienzo = actividad.inicio + (nueva_fecha - actividad.vencimiento) if actividad.inicio else None
    siguiente = AgendaActividad(
        titulo=actividad.titulo, descripcion=actividad.descripcion, tipo=actividad.tipo,
        estado="pendiente", prioridad=actividad.prioridad, visibilidad=actividad.visibilidad,
        creado_por_id=actividad.creado_por_id, responsable_id=actividad.responsable_id,
        inicio=comienzo, vencimiento=nueva_fecha, todo_el_dia=actividad.todo_el_dia,
        lugar=actividad.lugar, modalidad=actividad.modalidad, recurrencia=actividad.recurrencia,
        requiere_revision=actividad.requiere_revision, referencia_sp=actividad.referencia_sp,
    )
    db.session.add(siguiente)
    db.session.flush()
    for persona in actividad.participantes:
        db.session.add(AgendaParticipante(actividad_id=siguiente.id, usuario_id=persona.usuario_id))
    return siguiente
