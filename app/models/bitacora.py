from datetime import datetime

from app import db


class Bitacora(db.Model):
    __tablename__ = "bitacora"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=True, index=True)

    accion = db.Column(db.String(120), nullable=False, index=True)
    modulo = db.Column(db.String(80), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=True)

    # Trazabilidad estructurada. Los campos anteriores se conservan para
    # compatibilidad con reportes y registros históricos.
    entidad = db.Column(db.String(80), nullable=True, index=True)
    entidad_id = db.Column(db.String(80), nullable=True, index=True)
    datos_anteriores = db.Column(db.JSON, nullable=True)
    datos_posteriores = db.Column(db.JSON, nullable=True)
    motivo = db.Column(db.Text, nullable=True)

    ip_origen = db.Column(db.String(80), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    usuario = db.relationship("Usuario", backref=db.backref("acciones_bitacora", lazy=True))
    expediente = db.relationship("Expediente", backref=db.backref("acciones_bitacora", lazy=True))

    def __repr__(self):
        return f"<Bitacora {self.accion}>"
