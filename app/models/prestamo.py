from datetime import datetime

from sqlalchemy import text

from app import db


class PrestamoExpediente(db.Model):
    __tablename__ = "prestamos_expedientes"

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False, index=True)

    numero_control = db.Column(db.String(80), unique=True, nullable=False)

    solicitante = db.Column(db.String(150), nullable=False)
    persona_entrega = db.Column(db.String(150), nullable=False)
    persona_recibe = db.Column(db.String(150), nullable=False)

    fecha_prestamo = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_estimada_devolucion = db.Column(db.Date, nullable=True)
    fecha_real_devolucion = db.Column(db.DateTime, nullable=True)

    persona_devuelve = db.Column(db.String(150), nullable=True)
    persona_recibe_devolucion = db.Column(db.String(150), nullable=True)

    estado = db.Column(db.String(50), nullable=False, default="En préstamo", index=True)

    observaciones = db.Column(db.Text, nullable=True)
    observaciones_devolucion = db.Column(db.Text, nullable=True)

    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship("Expediente", backref=db.backref("prestamos", lazy=True))

    __table_args__ = (
        db.CheckConstraint(
            "estado IN ('En préstamo', 'Devuelto')",
            name="ck_prestamo_estado",
        ),
        db.Index(
            "uq_prestamo_activo_expediente",
            "expediente_id",
            unique=True,
            postgresql_where=text("estado = 'En préstamo' AND activo = true"),
            sqlite_where=text("estado = 'En préstamo' AND activo = 1"),
        ),
    )

    def __repr__(self):
        return f"<Prestamo {self.numero_control} Expediente {self.expediente_id}>"
