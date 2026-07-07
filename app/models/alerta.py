from datetime import datetime
from app import db

class Alerta(db.Model):
    __tablename__ = "alertas"

    id = db.Column(db.Integer, primary_key=True)

    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False)
    documento_id = db.Column(db.Integer, db.ForeignKey("documentos_expediente.id"), nullable=True)

    tipo_alerta = db.Column(db.String(100), nullable=False)
    titulo = db.Column(db.String(180), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)

    gravedad = db.Column(db.String(50), nullable=False, default="Media")
    estado = db.Column(db.String(50), nullable=False, default="Abierta")
    origen = db.Column(db.String(80), nullable=False, default="Automática")

    creada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    cerrada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cerrado_en = db.Column(db.DateTime, nullable=True)

    expediente = db.relationship("Expediente", backref=db.backref("alertas", lazy=True))
    documento = db.relationship("DocumentoExpediente", backref=db.backref("alertas", lazy=True))
    creada_por = db.relationship("Usuario", foreign_keys=[creada_por_id])
    cerrada_por = db.relationship("Usuario", foreign_keys=[cerrada_por_id])

    def __repr__(self):
        return f"<Alerta {self.tipo_alerta} Expediente {self.expediente_id}>"
