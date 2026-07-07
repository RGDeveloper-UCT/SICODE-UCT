from datetime import datetime
from app import db

class DocumentoExpediente(db.Model):
    __tablename__ = "documentos_expediente"

    id = db.Column(db.Integer, primary_key=True)

    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False)

    nombre_documento = db.Column(db.String(180), nullable=False)
    tipo_documento = db.Column(db.String(80), nullable=False, default="Documento")
    folio_inicio = db.Column(db.Integer, nullable=False)
    folio_fin = db.Column(db.Integer, nullable=False)
    total_folios = db.Column(db.Integer, nullable=False)

    estado_revision = db.Column(db.String(80), nullable=False, default="Pendiente de revisión")
    es_anexo = db.Column(db.Boolean, default=False)

    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship("Expediente", backref=db.backref("documentos_indice", lazy=True))

    def __repr__(self):
        return f"<DocumentoExpediente {self.nombre_documento} Expediente {self.expediente_id}>"
