from datetime import datetime

from app import db


class AccesoCCT(db.Model):
    """Registro administrativo de ingreso al Centro de Control Telemático."""

    __tablename__ = "accesos_cct"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), nullable=False, index=True)
    cui = db.Column(db.String(13), nullable=False, index=True)
    motivo = db.Column(db.String(40), nullable=False, index=True)
    motivo_otro = db.Column(db.String(240), nullable=True)
    fecha_hora_entrada = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    creado_por = db.relationship("Usuario", foreign_keys=[usuario_id], lazy="joined")

    @property
    def correlativo(self):
        return f"CCT-{self.id:06d}" if self.id else "CCT-PENDIENTE"

    @property
    def motivo_legible(self):
        etiquetas = {
            "SERVICIO_TECNICO": "Servicio técnico",
            "VISITA_TECNICA": "Visita técnica",
            "AUDITORIA": "Auditoría",
            "OTRO": "Otro",
        }
        if self.motivo == "OTRO" and self.motivo_otro:
            return f"Otro: {self.motivo_otro}"
        return etiquetas.get(self.motivo, self.motivo or "Sin especificar")

    @property
    def cui_formateado(self):
        texto = str(self.cui or "")
        if len(texto) == 13 and texto.isdigit():
            return f"{texto[:4]} {texto[4:9]} {texto[9:]}"
        return texto
