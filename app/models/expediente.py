from datetime import datetime
from app import db

class Expediente(db.Model):
    __tablename__ = "expedientes"

    id = db.Column(db.Integer, primary_key=True)

    codigo_interno = db.Column(db.String(50), unique=True, nullable=False)
    no_sp = db.Column(db.String(50), unique=True, nullable=False)

    nombre_referencia = db.Column(db.String(150), nullable=True)
    estado_administrativo = db.Column(db.String(80), nullable=False, default="Activo")
    estado_fisico_documental = db.Column(db.String(80), nullable=False, default="Pendiente de verificación")

    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Expediente SP {self.no_sp}>"
