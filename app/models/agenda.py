"""Agenda UCT: actividades, colaboración, avisos y cumpleaños (metadatos solamente)."""
from datetime import datetime
from app import db


class AgendaActividad(db.Model):
    __tablename__ = "agenda_actividades"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(180), nullable=False)
    descripcion = db.Column(db.Text)
    tipo = db.Column(db.String(24), nullable=False, default="tarea", index=True)
    estado = db.Column(db.String(24), nullable=False, default="pendiente", index=True)
    prioridad = db.Column(db.String(12), nullable=False, default="media", index=True)
    visibilidad = db.Column(db.String(16), nullable=False, default="equipo")
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    responsable_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    padre_id = db.Column(db.Integer, db.ForeignKey("agenda_actividades.id"), index=True)
    inicio = db.Column(db.DateTime)
    vencimiento = db.Column(db.DateTime, index=True)
    todo_el_dia = db.Column(db.Boolean, nullable=False, default=False)
    lugar = db.Column(db.String(180))
    modalidad = db.Column(db.String(24))
    recurrencia = db.Column(db.String(20), nullable=False, default="ninguna")
    requiere_revision = db.Column(db.Boolean, nullable=False, default=False)
    referencia_sp = db.Column(db.String(40), index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    finalizado_en = db.Column(db.DateTime)
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    responsable = db.relationship("Usuario", foreign_keys=[responsable_id])
    participantes = db.relationship("AgendaParticipante", back_populates="actividad", cascade="all, delete-orphan")
    subtareas = db.relationship("AgendaActividad", backref=db.backref("padre", remote_side=[id]), lazy="select")
    comentarios = db.relationship("AgendaComentario", back_populates="actividad", cascade="all, delete-orphan")

    def as_dict(self):
        return {
            "id": self.id, "titulo": self.titulo, "descripcion": self.descripcion or "",
            "tipo": self.tipo, "estado": self.estado, "prioridad": self.prioridad,
            "visibilidad": self.visibilidad, "creado_por_id": self.creado_por_id,
            "creado_por": self.creado_por.nombre if self.creado_por else "",
            "responsable_id": self.responsable_id,
            "responsable": self.responsable.nombre if self.responsable else "",
            "padre_id": self.padre_id, "inicio": self.inicio.isoformat() if self.inicio else None,
            "vencimiento": self.vencimiento.isoformat() if self.vencimiento else None,
            "todo_el_dia": self.todo_el_dia, "lugar": self.lugar or "",
            "modalidad": self.modalidad or "", "recurrencia": self.recurrencia,
            "requiere_revision": self.requiere_revision, "referencia_sp": self.referencia_sp,
            "participantes": [p.usuario_id for p in self.participantes],
            "progreso": (round(sum(s.estado == "finalizada" for s in self.subtareas) * 100 / len(self.subtareas))
                         if self.subtareas else (100 if self.estado == "finalizada" else 0)),
        }


class AgendaParticipante(db.Model):
    __tablename__ = "agenda_participantes"
    id = db.Column(db.Integer, primary_key=True)
    actividad_id = db.Column(db.Integer, db.ForeignKey("agenda_actividades.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    respuesta = db.Column(db.String(20), nullable=False, default="pendiente")
    asignado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actividad = db.relationship("AgendaActividad", back_populates="participantes")
    usuario = db.relationship("Usuario")
    __table_args__ = (db.UniqueConstraint("actividad_id", "usuario_id", name="uq_agenda_participante"),)


class AgendaComentario(db.Model):
    __tablename__ = "agenda_comentarios"
    id = db.Column(db.Integer, primary_key=True)
    actividad_id = db.Column(db.Integer, db.ForeignKey("agenda_actividades.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actividad = db.relationship("AgendaActividad", back_populates="comentarios")
    usuario = db.relationship("Usuario")


class AgendaNotificacion(db.Model):
    __tablename__ = "agenda_notificaciones"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    actividad_id = db.Column(db.Integer, db.ForeignKey("agenda_actividades.id", ondelete="SET NULL"))
    clave = db.Column(db.String(180), unique=True, nullable=False)
    titulo = db.Column(db.String(180), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    prioridad = db.Column(db.String(12), nullable=False, default="media")
    obligatoria = db.Column(db.Boolean, nullable=False, default=False)
    creada_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    leida_en = db.Column(db.DateTime)
    confirmada_en = db.Column(db.DateTime)
    actividad = db.relationship("AgendaActividad")


class AgendaCumpleanos(db.Model):
    __tablename__ = "agenda_cumpleanos"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, unique=True)
    dia = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    visible = db.Column(db.Boolean, nullable=False, default=False)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    usuario = db.relationship("Usuario")
