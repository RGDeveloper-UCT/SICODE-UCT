from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import db


ZONA_HORARIA_GUATEMALA = ZoneInfo("America/Guatemala")


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

    # La bitácora conserva UTC en la base de datos para mantener una referencia
    # única y compatible con los registros históricos. La presentación se
    # convierte a America/Guatemala mediante creado_en_guatemala.
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    usuario = db.relationship("Usuario", backref=db.backref("acciones_bitacora", lazy=True))
    expediente = db.relationship("Expediente", backref=db.backref("acciones_bitacora", lazy=True))

    @property
    def creado_en_guatemala(self):
        """Devuelve creado_en convertido de UTC a la hora oficial de Guatemala.

        El esquema histórico usa DateTime sin información de zona. Por ello un
        valor naive se interpreta explícitamente como UTC antes de convertirlo.
        Esto corrige tanto registros existentes como registros nuevos sin
        modificar los timestamps almacenados ni requerir una migración.
        """
        if self.creado_en is None:
            return None

        fecha = self.creado_en
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return fecha.astimezone(ZONA_HORARIA_GUATEMALA)

    def __repr__(self):
        return f"<Bitacora {self.accion}>"
