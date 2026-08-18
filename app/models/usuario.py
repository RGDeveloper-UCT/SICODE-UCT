from datetime import datetime

from flask_login import UserMixin
from sqlalchemy.orm import validates

from app import db


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(80), unique=True, nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=True, index=True)
    rol = db.Column(db.String(50), nullable=False, default="usuario_autorizado")
    activo = db.Column(db.Boolean, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @validates("usuario")
    def _normalizar_usuario(self, _clave, valor):
        return str(valor or "").strip().lower()

    @validates("correo")
    def _normalizar_correo(self, _clave, valor):
        texto = str(valor or "").strip().lower()
        return texto or None

    @validates("password_hash")
    def _marcar_password_temporal(self, _clave, valor):
        # Cualquier contraseña asignada por administración/seed se considera
        # temporal. El flujo de cambio propio la marca como definitiva.
        self.debe_cambiar_password = True
        return valor

    @property
    def is_active(self):
        return bool(self.activo)

    def __repr__(self):
        return f"<Usuario {self.usuario}>"
