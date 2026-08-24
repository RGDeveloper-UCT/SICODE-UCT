from datetime import datetime

from app import db


class PrestamoGrupo(db.Model):
    __tablename__ = "prestamos_grupos"

    id = db.Column(db.Integer, primary_key=True)
    numero_control = db.Column(db.String(100), unique=True, nullable=False, index=True)
    sp_desde = db.Column(db.Integer, nullable=False)
    sp_hasta = db.Column(db.Integer, nullable=False)
    solicitante = db.Column(db.String(150), nullable=False)
    persona_entrega = db.Column(db.String(150), nullable=False)
    persona_recibe = db.Column(db.String(150), nullable=False)
    fecha_prestamo = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_estimada_devolucion = db.Column(db.Date, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id], lazy="joined")
    detalles = db.relationship(
        "PrestamoGrupoDetalle",
        back_populates="grupo",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PrestamoGrupoDetalle.id",
    )

    __table_args__ = (
        db.CheckConstraint("sp_desde > 0", name="ck_prestamo_grupo_sp_desde_positivo"),
        db.CheckConstraint("sp_hasta >= sp_desde", name="ck_prestamo_grupo_rango_valido"),
    )

    @property
    def total_expedientes(self):
        return len(self.detalles)

    @property
    def total_pendientes(self):
        return sum(
            1
            for detalle in self.detalles
            if detalle.prestamo and detalle.prestamo.estado == "En préstamo" and detalle.prestamo.activo
        )

    @property
    def estado(self):
        if not self.detalles:
            return "Sin expedientes"
        if self.total_pendientes == 0:
            return "Devuelto"
        if self.total_pendientes == len(self.detalles):
            return "En préstamo"
        return "Parcialmente devuelto"

    def __repr__(self):
        return f"<PrestamoGrupo {self.numero_control}>"


class PrestamoGrupoDetalle(db.Model):
    __tablename__ = "prestamos_grupos_detalle"

    id = db.Column(db.Integer, primary_key=True)
    prestamo_grupo_id = db.Column(
        db.Integer,
        db.ForeignKey("prestamos_grupos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prestamo_id = db.Column(
        db.Integer,
        db.ForeignKey("prestamos_expedientes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False, index=True)
    orden = db.Column(db.Integer, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    grupo = db.relationship("PrestamoGrupo", back_populates="detalles")
    prestamo = db.relationship(
        "PrestamoExpediente",
        lazy="joined",
        backref=db.backref("detalle_grupal", uselist=False, lazy="selectin"),
    )
    expediente = db.relationship("Expediente", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("prestamo_grupo_id", "expediente_id", name="uq_prestamo_grupo_expediente"),
        db.CheckConstraint("orden > 0", name="ck_prestamo_grupo_detalle_orden_positivo"),
    )

    def __repr__(self):
        return f"<PrestamoGrupoDetalle grupo={self.prestamo_grupo_id} expediente={self.expediente_id}>"