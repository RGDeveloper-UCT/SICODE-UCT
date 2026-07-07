from datetime import datetime
from app import db

class Bitacora(db.Model):
    __tablename__ = "bitacora"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=True)

    accion = db.Column(db.String(120), nullable=False)
    modulo = db.Column(db.String(80), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    ip_origen = db.Column(db.String(80), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship("Usuario", backref=db.backref("acciones_bitacora", lazy=True))
    expediente = db.relationship("Expediente", backref=db.backref("acciones_bitacora", lazy=True))

    def __repr__(self):
        return f"<Bitacora {self.accion}>"
