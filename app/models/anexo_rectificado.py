from datetime import datetime

from app import db


class AnexoRectificado(db.Model):
    """Detalle opcional de un anexo consignado durante la rectificación física."""

    __tablename__ = "anexos_rectificados"

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(
        db.Integer,
        db.ForeignKey("expedientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    numero_anexo = db.Column(db.String(50), nullable=True)
    titulo = db.Column(db.String(180), nullable=False)
    tipo_anexo = db.Column(db.String(120), nullable=True)

    fecha_recepcion = db.Column(db.Date, nullable=True)
    persona_entrega = db.Column(db.String(180), nullable=True)
    rc = db.Column(db.String(80), nullable=True)
    providencia = db.Column(db.String(120), nullable=True)
    folios = db.Column(db.String(80), nullable=True)

    escaneado = db.Column(db.Boolean, nullable=False, default=False)
    fecha_escaneado = db.Column(db.Date, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship(
        "Expediente",
        backref=db.backref("anexos_rectificados_detalle", lazy=True),
    )
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id], lazy="joined")

    def __repr__(self):
        return f"<AnexoRectificado {self.titulo} Expediente {self.expediente_id}>"
