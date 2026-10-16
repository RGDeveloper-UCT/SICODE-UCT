"""Inventario maestro de equipos vinculable a todos los controles de seguridad."""
from datetime import datetime
from app import db

class EquipoInstitucional(db.Model):
    __tablename__ = "equipos_institucionales"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(60), nullable=False, unique=True, index=True)
    tipo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(120))
    serie = db.Column(db.String(120), unique=True)
    numero_inventario = db.Column(db.String(120), unique=True)
    area = db.Column(db.String(160))
    ubicacion = db.Column(db.String(160))
    responsable_usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)
    acceso_institucional = db.Column(db.Boolean, nullable=False, default=True)
    tipo_acceso = db.Column(db.String(40), nullable=False, default="INTERNO")
    estado = db.Column(db.String(30), nullable=False, default="ACTIVO", index=True)
    observaciones = db.Column(db.Text)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    responsable = db.relationship("Usuario", foreign_keys=[responsable_usuario_id])
    creador = db.relationship("Usuario", foreign_keys=[creado_por_id])

    def snapshot(self):
        return {campo: getattr(self, campo) for campo in (
            "codigo", "tipo", "nombre", "marca", "modelo", "serie",
            "numero_inventario", "area", "ubicacion", "responsable_usuario_id",
            "acceso_institucional", "tipo_acceso", "estado", "observaciones"
        )}
