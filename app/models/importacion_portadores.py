from datetime import datetime
from app import db


class ImportacionPortadores(db.Model):
    __tablename__ = "importaciones_portadores"

    id = db.Column(db.Integer, primary_key=True)
    archivo_nombre = db.Column(db.String(255), nullable=False)
    archivo_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    total_filas = db.Column(db.Integer, nullable=False, default=0)
    nuevos = db.Column(db.Integer, nullable=False, default=0)
    actualizados = db.Column(db.Integer, nullable=False, default=0)
    sin_cambios = db.Column(db.Integer, nullable=False, default=0)
    omitidos = db.Column(db.Integer, nullable=False, default=0)
    duplicados = db.Column(db.Integer, nullable=False, default=0)
    vinculados_coordinacion = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    usuario = db.relationship("Usuario", backref=db.backref("importaciones_portadores", lazy=True))
