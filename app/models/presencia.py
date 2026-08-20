from datetime import datetime

from app import db


class PresenciaUsuario(db.Model):
    __tablename__ = "presencias_usuario"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sesion_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    iniciado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ultimo_pulso_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    ruta = db.Column(db.String(255), nullable=True)
    pagina = db.Column(db.String(180), nullable=True)

    usuario = db.relationship("Usuario", lazy="joined")

    def __repr__(self):
        return f"<PresenciaUsuario usuario={self.usuario_id} sesion={self.sesion_id[:8]}>"
