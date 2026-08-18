from datetime import datetime

from flask_login import UserMixin

from app import db


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(80), unique=True, nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default="usuario_autorizado")
    activo = db.Column(db.Boolean, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def is_active(self):
        """Flask-Login debe considerar inactiva una cuenta deshabilitada en SICODE."""
        return bool(self.activo)

    def __repr__(self):
        return f"<Usuario {self.usuario}>"
