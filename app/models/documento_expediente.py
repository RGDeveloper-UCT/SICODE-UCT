from datetime import datetime

from app import db


class DocumentoExpediente(db.Model):
    __tablename__ = "documentos_expediente"

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False, index=True)

    # Origen administrativo opcional. Es nullable para conservar intactos los
    # documentos históricos y los registros creados directamente desde Índice.
    registro_coordinacion_id = db.Column(
        db.Integer,
        db.ForeignKey("registros_coordinacion.id"),
        nullable=True,
        index=True,
    )

    nombre_documento = db.Column(db.String(180), nullable=False)
    tipo_documento = db.Column(db.String(80), nullable=False, default="Documento")
    folio_inicio = db.Column(db.Integer, nullable=False)
    folio_fin = db.Column(db.Integer, nullable=False)
    # Se conserva por compatibilidad/reportes, pero la regla de DB garantiza
    # que siempre sea exactamente el valor derivado del rango.
    total_folios = db.Column(db.Integer, nullable=False)

    estado_revision = db.Column(db.String(80), nullable=False, default="Pendiente de revisión")
    es_anexo = db.Column(db.Boolean, nullable=False, default=False)

    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship("Expediente", backref=db.backref("documentos_indice", lazy=True))
    registro_coordinacion = db.relationship(
        "RegistroCoordinacion",
        backref=db.backref("documentos_generados", lazy=True),
    )

    __table_args__ = (
        db.CheckConstraint("folio_inicio >= 1", name="ck_documento_folio_inicio_positivo"),
        db.CheckConstraint("folio_fin >= folio_inicio", name="ck_documento_rango_folios"),
        db.CheckConstraint(
            "total_folios = folio_fin - folio_inicio + 1",
            name="ck_documento_total_folios",
        ),
        db.Index("ix_documento_expediente_folios", "expediente_id", "folio_inicio", "folio_fin"),
    )

    def __repr__(self):
        return f"<DocumentoExpediente {self.nombre_documento} Expediente {self.expediente_id}>"
