from datetime import datetime

from app import db


class TrasladoVirtualExpediente(db.Model):
    __tablename__ = "traslados_virtuales_expediente"

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)

    numero_constancia = db.Column(db.String(100), unique=True, nullable=False, index=True)
    destinatario = db.Column(db.String(180), nullable=False, index=True)
    dependencia_destino = db.Column(db.String(220), nullable=True)
    plataforma = db.Column(db.String(80), nullable=False, index=True)
    enlace_corto = db.Column(db.String(500), nullable=False)
    asunto = db.Column(db.String(250), nullable=False)
    observaciones = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    expediente = db.relationship(
        "Expediente",
        backref=db.backref("traslados_virtuales", lazy=True),
    )
    usuario = db.relationship(
        "Usuario",
        backref=db.backref("traslados_virtuales_expediente", lazy=True),
    )

    def __repr__(self):
        return f"<TrasladoVirtual {self.numero_constancia} Expediente {self.expediente_id}>"
