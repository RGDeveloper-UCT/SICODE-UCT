from datetime import datetime

from app import db


class VerificacionExpediente(db.Model):
    """Evento histórico de revisión; no reemplaza el estado actual del expediente."""

    __tablename__ = "verificaciones_expediente"

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)

    tipo = db.Column(db.String(30), nullable=False, default="INTEGRAL", index=True)
    resultado = db.Column(db.String(80), nullable=False, index=True)
    folios_verificados = db.Column(db.Integer, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    origen = db.Column(db.String(30), nullable=False, default="MANUAL")
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    expediente = db.relationship("Expediente", backref=db.backref("verificaciones", lazy=True, cascade="all, delete-orphan"))
    usuario = db.relationship("Usuario", backref=db.backref("verificaciones_expediente", lazy=True))

    __table_args__ = (
        db.CheckConstraint("tipo IN ('FISICA', 'DOCUMENTAL', 'INTEGRAL')", name="ck_verificacion_tipo"),
        db.CheckConstraint(
            "resultado IN ('Verificado', 'Con observaciones', 'Incompleto', 'No localizado')",
            name="ck_verificacion_resultado",
        ),
        db.CheckConstraint(
            "folios_verificados IS NULL OR folios_verificados >= 0",
            name="ck_verificacion_folios_no_negativos",
        ),
    )
