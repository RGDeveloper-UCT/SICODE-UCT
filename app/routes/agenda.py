"""Agenda UCT: tareas, calendario, trabajo compartido y alertas de lectura."""
import csv
from datetime import date, datetime
from io import StringIO

from flask import Blueprint, abort, jsonify, make_response, render_template, request, session, send_file
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models.agenda import (
    AgendaActividad, AgendaComentario, AgendaCumpleanos, AgendaNotificacion, AgendaParticipante,
)
from app.models.usuario import Usuario
from app.services.agenda_service import (
    alertas_de_plazo, ahora_gt, aviso_json, avisos_usuario, destinatarios,
    fecha_local, notificar, puede_editar, puede_ver, siguiente_repeticion, visible_query,
)
from app.services.bitacora_service import registrar_bitacora
from app.services.agenda_reports import generar_pdf, generar_xlsx, celda_segura

agenda_bp = Blueprint("agenda", __name__, url_prefix="/agenda")
TIPOS = {"tarea", "evento", "capacitacion", "gestion", "mantenimiento"}
ESTADOS = {"pendiente", "en_proceso", "en_revision", "finalizada", "bloqueada", "cancelada"}
PRIORIDADES = {"alta", "media", "baja"}
RECURRENCIAS = {"ninguna", "diaria", "semanal", "mensual", "anual", "laboral"}


def json_error(mensaje, estado=400):
    return jsonify({"error": mensaje}), estado


def datos_json():
    return request.get_json(silent=True) if request.is_json else request.form.to_dict()


def permitido():
    if not current_user.puede_modificar:
        abort(403)


def actividad_visible(id_):
    actividad = db.session.get(AgendaActividad, id_)
    if not actividad:
        abort(404)
    if not puede_ver(current_user, actividad):
        abort(403)
    return actividad


def editable(id_):
    actividad = actividad_visible(id_)
    if not puede_editar(current_user, actividad):
        abort(403)
    return actividad


def usuario_autorizado(id_):
    try:
        usuario = db.session.get(Usuario, int(id_))
    except (ValueError, TypeError):
        usuario = None
    return usuario if usuario and usuario.activo and usuario.puede_modificar else None


def miembros_ids(datos):
    valores = datos.get("participantes") or []
    if isinstance(valores, str):
        valores = [parte for parte in valores.split(",") if parte.strip()]
    if not isinstance(valores, list) or len(valores) > 100:
        raise ValueError("La lista de participantes no es válida.")
    try:
        ids = {int(item) for item in valores}
    except (TypeError, ValueError):
        raise ValueError("La lista de participantes contiene IDs inválidos.")
    if any(not usuario_autorizado(id_) for id_ in ids):
        raise ValueError("Uno de los participantes no está autorizado.")
    return ids


def llenar(actividad, datos, crear=False):
    """Validación de los campos editables sin permitir cambios por asignación masiva."""
    if crear or "titulo" in datos:
        titulo = str(datos.get("titulo") or "").strip()
        if not titulo or len(titulo) > 180:
            raise ValueError("El título es obligatorio y admite hasta 180 caracteres.")
        actividad.titulo = titulo
    for campo, opciones in (
        ("tipo", TIPOS), ("prioridad", PRIORIDADES),
        ("recurrencia", RECURRENCIAS), ("visibilidad", {"equipo", "personal"}),
    ):
        if crear or campo in datos:
            valor = datos.get(campo) or {"tipo": "tarea", "prioridad": "media",
                                         "recurrencia": "ninguna", "visibilidad": "equipo"}[campo]
            if valor not in opciones:
                raise ValueError("Valor inválido para " + campo)
            setattr(actividad, campo, valor)
    if crear or "descripcion" in datos:
        descripcion = str(datos.get("descripcion") or "")
        if len(descripcion) > 5000:
            raise ValueError("La descripción supera 5000 caracteres.")
        actividad.descripcion = descripcion
    for campo in ("inicio", "vencimiento"):
        if crear or campo in datos:
            setattr(actividad, campo, fecha_local(datos.get(campo)))
    if actividad.inicio and actividad.vencimiento and actividad.inicio > actividad.vencimiento:
        raise ValueError("La fecha de inicio no puede ser posterior al vencimiento.")
    for campo, limite in (("lugar", 180), ("modalidad", 24), ("referencia_sp", 40)):
        if crear or campo in datos:
            valor = str(datos.get(campo) or "").strip()
            if len(valor) > limite:
                raise ValueError("La longitud del campo " + campo + " es inválida.")
            setattr(actividad, campo, valor or None)
    for campo in ("requiere_revision", "todo_el_dia"):
        if crear or campo in datos:
            actividad.__setattr__(campo, datos.get(campo) in (True, "true", "1", 1, "on"))
    if crear or "responsable_id" in datos:
        responsable_id = datos.get("responsable_id") or current_user.id
        responsable = usuario_autorizado(responsable_id)
        if not responsable:
            raise ValueError("El responsable no existe o no está autorizado.")
        actividad.responsable_id = responsable.id
    if crear and datos.get("padre_id"):
        padre = editable(int(datos["padre_id"]))
        if padre.padre_id:
            raise ValueError("Las subtareas no pueden anidar más niveles.")
        actividad.padre_id = padre.id
        actividad.visibilidad = padre.visibilidad
    if not crear and ("padre_id" in datos or "creado_por_id" in datos):
        raise ValueError("No se permite cambiar el creador o padre de una tarea.")
    if actividad.padre_id and actividad.recurrencia != "ninguna":
        raise ValueError("Las subtareas no pueden tener recurrencia automática.")


def auditoria(accion, actividad, descripcion):
    registrar_bitacora(
        accion=accion, modulo="Agenda UCT", descripcion=descripcion,
        usuario_id=current_user.id, entidad="AgendaActividad",
        entidad_id=actividad.id, commit=False,
    )


@agenda_bp.get("/")
@login_required
def inicio():
    usuarios = Usuario.query.filter(Usuario.activo.is_(True),
        Usuario.rol.in_(("administrador", "usuario_autorizado"))).order_by(Usuario.nombre).all()
    cumple = AgendaCumpleanos.query.filter_by(usuario_id=current_user.id).first()
    return render_template("agenda/inicio.html", usuarios=usuarios, cumple=cumple)


@agenda_bp.get("/api/actividades")
@login_required
def listar():
    consulta = visible_query(current_user)
    estado = request.args.get("estado")
    tipo = request.args.get("tipo")
    busqueda = (request.args.get("q") or "").strip()
    if estado in ESTADOS:
        consulta = consulta.filter(AgendaActividad.estado == estado)
    if tipo in TIPOS:
        consulta = consulta.filter(AgendaActividad.tipo == tipo)
    if busqueda:
        consulta = consulta.filter(AgendaActividad.titulo.ilike("%" + busqueda[:100] + "%"))
    if request.args.get("mias") == "1":
        consulta = consulta.filter(or_(
            AgendaActividad.creado_por_id == current_user.id,
            AgendaActividad.responsable_id == current_user.id,
            AgendaActividad.id.in_(db.session.query(AgendaParticipante.actividad_id).filter(
                AgendaParticipante.usuario_id == current_user.id)),
        ))
    actividades = consulta.order_by(AgendaActividad.vencimiento.asc().nullslast(),
                                    AgendaActividad.id.desc()).limit(500).all()
    return jsonify({"actividades": [a.as_dict() for a in actividades]})


@agenda_bp.get("/api/actividades/<int:id_>")
@login_required
def detalle(id_):
    actividad = actividad_visible(id_)
    return jsonify({
        "actividad": actividad.as_dict(),
        "subtareas": [a.as_dict() for a in actividad.subtareas if puede_ver(current_user, a)],
        "comentarios": [{
            "id": c.id, "usuario": c.usuario.nombre if c.usuario else "",
            "texto": c.texto, "fecha": c.creado_en.isoformat()
        } for c in sorted(actividad.comentarios, key=lambda c: c.creado_en)],
        "asistencias": [{
            "usuario_id": p.usuario_id, "nombre": p.usuario.nombre if p.usuario else "",
            "respuesta": p.respuesta
        } for p in actividad.participantes],
    })


@agenda_bp.post("/api/actividades")
@login_required
def crear():
    permitido()
    datos = datos_json() or {}
    actividad = AgendaActividad(creado_por_id=current_user.id,
                                responsable_id=current_user.id)
    try:
        llenar(actividad, datos, crear=True)
        participantes = miembros_ids(datos)
    except (TypeError, ValueError) as error:
        return json_error(str(error))
    db.session.add(actividad)
    db.session.flush()
    for usuario_id in participantes - {actividad.responsable_id}:
        db.session.add(AgendaParticipante(actividad_id=actividad.id, usuario_id=usuario_id))
    notificar(destinatarios(actividad) | participantes, actividad,
             "Nueva actividad asignada", "Se le asignó: " + actividad.titulo,
             actividad.prioridad, omitir=current_user.id)
    auditoria("AGENDA_CREAR", actividad, "Actividad creada: " + actividad.titulo)
    db.session.commit()
    return jsonify({"actividad": actividad.as_dict()}), 201


@agenda_bp.patch("/api/actividades/<int:id_>")
@login_required
def modificar(id_):
    actividad = editable(id_)
    datos = datos_json() or {}
    original = actividad.responsable_id
    fechas_anteriores = (actividad.inicio, actividad.vencimiento)
    titulo_anterior = actividad.titulo
    try:
        llenar(actividad, datos)
        nuevos = miembros_ids(datos) if "participantes" in datos else None
    except (ValueError, TypeError) as error:
        return json_error(str(error))
    if nuevos is not None:
        anteriores = {p.usuario_id for p in actividad.participantes}
        for p in list(actividad.participantes):
            if p.usuario_id not in nuevos:
                db.session.delete(p)
                actividad.participantes.remove(p)
        for id_nuevo in nuevos - anteriores - {actividad.responsable_id}:
            db.session.add(AgendaParticipante(actividad_id=actividad.id, usuario_id=id_nuevo))
        notificar(nuevos - anteriores, actividad, "Se le incorporó a una actividad",
                 actividad.titulo, actividad.prioridad)
    if original != actividad.responsable_id:
        notificar({actividad.responsable_id}, actividad, "Nueva responsabilidad",
                 actividad.titulo, actividad.prioridad)
    if fechas_anteriores != (actividad.inicio, actividad.vencimiento):
        notificar(destinatarios(actividad) | ({original} if original else set()),
                 actividad, "Se reprogramó una actividad",
                 current_user.nombre + " actualizó las fechas de «" + actividad.titulo + "».",
                 actividad.prioridad, omitir=current_user.id)
    elif titulo_anterior != actividad.titulo:
        notificar(destinatarios(actividad), actividad, "Cambio de nombre de actividad",
                 current_user.nombre + " actualizó «" + actividad.titulo + "».",
                 actividad.prioridad, omitir=current_user.id)
    auditoria("AGENDA_EDITAR", actividad, "Actividad editada: " + actividad.titulo)
    db.session.commit()
    return jsonify({"actividad": actividad.as_dict()})


@agenda_bp.post("/api/actividades/<int:id_>/estado")
@login_required
def cambiar_estado(id_):
    actividad = editable(id_)
    datos = datos_json() or {}
    estado = datos.get("estado")
    if estado not in ESTADOS:
        return json_error("Estado inválido.")
    if estado == "finalizada" and actividad.requiere_revision and current_user.id != actividad.creado_por_id:
        estado = "en_revision"
    if estado == "finalizada" and any(s.estado not in ("finalizada", "cancelada") for s in actividad.subtareas):
        return json_error("Complete las subtareas antes de finalizar la actividad.")
    anterior = actividad.estado
    actividad.estado = estado
    if estado == "finalizada":
        actividad.finalizado_en = datetime.utcnow()
        if anterior != "finalizada":
            siguiente = siguiente_repeticion(actividad)
            if siguiente:
                notificar(destinatarios(siguiente), siguiente, "Actividad recurrente programada",
                         siguiente.titulo, siguiente.prioridad, omitir=current_user.id)
    else:
        actividad.finalizado_en = None
    if anterior != estado:
        titulo = ("Actividad finalizada" if estado == "finalizada" else
                  "Actividad pendiente de validación" if estado == "en_revision" else
                  "Actualización de actividad")
        notificar(destinatarios(actividad), actividad, titulo,
                 current_user.nombre + " actualizó «" + actividad.titulo + "» a " + estado,
                 actividad.prioridad, omitir=current_user.id)
    auditoria("AGENDA_ESTADO", actividad, "Cambio de estado " + anterior + " -> " + estado)
    db.session.commit()
    return jsonify({"actividad": actividad.as_dict()})


@agenda_bp.post("/api/actividades/<int:id_>/comentarios")
@login_required
def comentar(id_):
    actividad = editable(id_)
    texto = str((datos_json() or {}).get("texto") or "").strip()
    if not texto or len(texto) > 2000:
        return json_error("El comentario debe tener entre 1 y 2000 caracteres.")
    db.session.add(AgendaComentario(actividad_id=id_, usuario_id=current_user.id, texto=texto))
    notificar(destinatarios(actividad), actividad, "Nuevo comentario",
             current_user.nombre + " comentó en «" + actividad.titulo + "»",
             actividad.prioridad, omitir=current_user.id)
    auditoria("AGENDA_COMENTAR", actividad, "Comentario agregado a actividad")
    db.session.commit()
    return jsonify({"ok": True}), 201


@agenda_bp.post("/api/actividades/<int:id_>/asistencia")
@login_required
def confirmar_asistencia(id_):
    actividad = actividad_visible(id_)
    respuesta = (datos_json() or {}).get("respuesta")
    if respuesta not in {"aceptada", "rechazada", "pendiente"}:
        return json_error("Respuesta inválida.")
    participante = AgendaParticipante.query.filter_by(
        actividad_id=id_, usuario_id=current_user.id).first()
    if not participante:
        return json_error("No figura como participante del evento.", 403)
    participante.respuesta = respuesta
    notificar({actividad.creado_por_id}, actividad, "Respuesta a convocatoria",
             current_user.nombre + ": " + respuesta + " — " + actividad.titulo,
             omitir=current_user.id)
    auditoria("AGENDA_ASISTENCIA", actividad, "Respuesta a convocatoria: " + respuesta)
    db.session.commit()
    return jsonify({"respuesta": respuesta})


@agenda_bp.get("/api/avisos")
@login_required
def avisos():
    alertas_de_plazo(current_user.id)
    pendientes = avisos_usuario(current_user.id)
    return jsonify({"avisos": [aviso_json(n) for n in pendientes], "total": len(pendientes)})


@agenda_bp.get("/api/avisos/inicio")
@login_required
def avisos_inicio():
    if not session.get("agenda_login_pendiente", False):
        return jsonify({"avisos": []})
    alertas_de_plazo(current_user.id)
    pendientes = avisos_usuario(current_user.id, True)
    if not pendientes:
        session.pop("agenda_login_pendiente", None)
    return jsonify({"avisos": [aviso_json(n) for n in pendientes]})


@agenda_bp.post("/api/avisos/<int:id_>/confirmar")
@login_required
def confirmar_aviso(id_):
    notificacion = AgendaNotificacion.query.filter_by(
        id=id_, usuario_id=current_user.id).first_or_404()
    ahora = datetime.utcnow()
    if not notificacion.leida_en:
        notificacion.leida_en = ahora
    if not notificacion.confirmada_en:
        notificacion.confirmada_en = ahora
        registrar_bitacora("AGENDA_CONFIRMAR_AVISO", "Agenda UCT",
            "Confirmación de lectura de aviso " + str(id_), usuario_id=current_user.id,
            entidad="AgendaNotificacion", entidad_id=id_, commit=False)
    db.session.commit()
    return jsonify({"ok": True, "confirmada_en": ahora.isoformat()})


@agenda_bp.post("/api/avisos/<int:id_>/leer")
@login_required
def leer_aviso(id_):
    aviso = AgendaNotificacion.query.filter_by(
        id=id_, usuario_id=current_user.id).first_or_404()
    if aviso.obligatoria and not aviso.confirmada_en:
        return json_error("Debe confirmar que está enterado de esta notificación.", 409)
    aviso.leida_en = aviso.leida_en or datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@agenda_bp.get("/api/cumpleanos")
@login_required
def listar_cumpleanos():
    registros = AgendaCumpleanos.query.join(Usuario).filter(
        Usuario.activo.is_(True),
        or_(AgendaCumpleanos.visible.is_(True),
            AgendaCumpleanos.usuario_id == current_user.id),
    ).all()
    return jsonify({"cumpleanos": [{
        "nombre": r.usuario.nombre, "usuario_id": r.usuario_id, "dia": r.dia,
        "mes": r.mes, "visible": r.visible,
    } for r in registros]})


@agenda_bp.post("/api/cumpleanos")
@login_required
def guardar_cumpleanos():
    permitido()
    datos = datos_json() or {}
    try:
        dia, mes = int(datos.get("dia")), int(datos.get("mes"))
        date(2024, mes, dia)  # Año bisiesto: admite 29 de febrero.
    except (TypeError, ValueError):
        return json_error("Día o mes inválidos.")
    registro = AgendaCumpleanos.query.filter_by(usuario_id=current_user.id).first()
    if not registro:
        registro = AgendaCumpleanos(usuario_id=current_user.id)
        db.session.add(registro)
    registro.dia, registro.mes = dia, mes
    registro.visible = datos.get("visible") in (True, 1, "1", "true", "on")
    registrar_bitacora("AGENDA_CUMPLEANOS", "Agenda UCT", "Actualizó preferencias de cumpleaños",
                      usuario_id=current_user.id, entidad="AgendaCumpleanos",
                      entidad_id=current_user.id, commit=False)
    db.session.commit()
    return jsonify({"ok": True})


@agenda_bp.get("/api/reporte.xlsx")
@login_required
def reporte_excel():
    permitido()
    registros = visible_query(current_user).order_by(AgendaActividad.id.desc()).limit(5000).all()
    resultado = generar_xlsx(registros)
    registrar_bitacora("AGENDA_EXPORTAR_XLSX", "Agenda UCT", "Exportación de Excel de actividades",
                      usuario_id=current_user.id)
    return send_file(resultado,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name="agenda_uct.xlsx")


@agenda_bp.get("/api/reporte.pdf")
@login_required
def reporte_pdf():
    permitido()
    registros = visible_query(current_user).order_by(AgendaActividad.id.desc()).limit(500).all()
    resultado = generar_pdf(registros)
    registrar_bitacora("AGENDA_EXPORTAR_PDF", "Agenda UCT", "Exportación PDF de actividades",
                      usuario_id=current_user.id)
    return send_file(resultado, mimetype="application/pdf", as_attachment=True,
                     download_name="agenda_uct.pdf")


@agenda_bp.get("/api/reporte.csv")
@login_required
def reporte():
    permitido()
    actividades = visible_query(current_user).order_by(AgendaActividad.id.desc()).limit(5000).all()
    buffer = StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["ID", "Tipo", "Título", "Estado", "Prioridad",
                       "Responsable", "Inicio", "Vencimiento", "Referencia SP"])
    for a in actividades:
        escritor.writerow([celda_segura(v) for v in (
            a.id, a.tipo, a.titulo, a.estado, a.prioridad,
            a.responsable.nombre if a.responsable else "",
            a.inicio.isoformat() if a.inicio else "",
            a.vencimiento.isoformat() if a.vencimiento else "",
            a.referencia_sp or "")])
    respuesta = make_response("\ufeff" + buffer.getvalue())
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = "attachment; filename=agenda_uct.csv"
    registrar_bitacora("AGENDA_EXPORTAR", "Agenda UCT", "Exportación CSV de actividades",
                      usuario_id=current_user.id)
    return respuesta
