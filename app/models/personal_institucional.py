"""Directorio de personal independiente de las cuentas de autenticación."""
from datetime import datetime
from sqlalchemy.orm import validates
from app import db

class PersonalInstitucional(db.Model):
    __tablename__ = "personal_institucional"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(120), nullable=False)
    coordinacion = db.Column(db.String(160), nullable=False, index=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @validates("nombre", "apellido")
    def normalizar_nombres(self, _clave, valor):
        """Mantener los nombres en mayúsculas en todas las altas y ediciones ORM."""
        return str(valor or "").strip().upper()

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"
