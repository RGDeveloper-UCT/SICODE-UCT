from datetime import datetime

from app import db


class FavoritoUsuario(db.Model):
    """Acceso rápido personal a un módulo, página o registro interno de SICODE."""

    __tablename__ = "favoritos_usuario"
    __table_args__ = (
        db.UniqueConstraint("usuario_id", "url", name="uq_favoritos_usuario_usuario_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    titulo = db.Column(db.String(160), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default="pagina")
    icono = db.Column(db.String(40), nullable=False, default="star")
    orden = db.Column(db.SmallInteger, nullable=False, default=1)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def a_dict(self):
        return {
            "id": self.id,
            "titulo": self.titulo,
            "url": self.url,
            "tipo": self.tipo,
            "icono": self.icono,
            "orden": self.orden,
        }
