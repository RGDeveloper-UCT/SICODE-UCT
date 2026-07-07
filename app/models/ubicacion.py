from datetime import datetime
from app import db

class UbicacionFisica(db.Model):
    __tablename__ = "ubicaciones_fisicas"

    id = db.Column(db.Integer, primary_key=True)

    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False)

    archivador = db.Column(db.String(80), nullable=True)
    sicoin = db.Column(db.String(80), nullable=True)
    estante = db.Column(db.String(80), nullable=True)
    caja = db.Column(db.String(80), nullable=True)
    modulo = db.Column(db.String(80), nullable=True)
    posicion = db.Column(db.String(80), nullable=True)

    observaciones = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship("Expediente", backref=db.backref("ubicaciones", lazy=True))

    def __repr__(self):
        return f"<Ubicacion Expediente {self.expediente_id}>"
