from datetime import datetime

from app import db


class ColaRecepcionDocumental(db.Model):
    __tablename__ = "cola_recepcion_documental"

    ESTADOS = ("PENDIENTE", "EN_PROCESO", "COMPLETADO")

    id = db.Column(db.Integer, primary_key=True)
    correlativo = db.Column(db.String(32), nullable=False, unique=True, index=True)
    recibido_en = db.Column(db.DateTime, nullable=False, index=True)
    recibido_de = db.Column(db.String(180), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion_temporal = db.Column(db.String(180), nullable=True)
    acciones = db.Column(db.JSON, nullable=False, default=list)
    observaciones = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE", index=True)
    completado_en = db.Column(db.DateTime, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    usuario = db.relationship(
        "Usuario",
        backref=db.backref("cola_recepcion_documental", lazy=True),
    )

    @property
    def estado_legible(self):
        return {
            "PENDIENTE": "Pendiente",
            "EN_PROCESO": "En proceso",
            "COMPLETADO": "Completado",
        }.get(self.estado, self.estado)

    @property
    def esta_completado(self):
        return self.estado == "COMPLETADO"

    def __repr__(self):
        return f"<ColaRecepcionDocumental {self.correlativo}>"
