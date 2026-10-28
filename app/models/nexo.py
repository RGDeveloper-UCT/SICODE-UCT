"""Memoria administrativa de propuestas de SICODE NEXO 2.0.

Nunca almacena PDFs, OCR, valores de expedientes ni mensajes de chat.
"""
from datetime import datetime

from app import db


class NexoPropuesta(db.Model):
    __tablename__ = "nexo_propuestas"

    id = db.Column(db.Integer, primary_key=True)
    firma = db.Column(db.String(64), nullable=False, unique=True, index=True)
    categoria = db.Column(db.String(40), nullable=False, index=True)
    modulo = db.Column(db.String(70), nullable=False)
    titulo = db.Column(db.String(180), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    recomendacion = db.Column(db.Text, nullable=False)
    prioridad = db.Column(db.String(12), nullable=False, default="media")
    estado = db.Column(db.String(20), nullable=False, default="nueva", index=True)
    evidencia = db.Column(db.JSON, nullable=False, default=dict)
    apariciones = db.Column(db.Integer, nullable=False, default=1)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    observado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revisado_en = db.Column(db.DateTime, nullable=True)
    revisado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    resultado = db.Column(db.String(240), nullable=True)

    def como_dict(self):
        return {
            "id": self.id, "categoria": self.categoria, "modulo": self.modulo,
            "titulo": self.titulo, "detalle": self.detalle,
            "recomendacion": self.recomendacion, "prioridad": self.prioridad,
            "estado": self.estado, "evidencia": self.evidencia or {},
            "apariciones": self.apariciones,
            "creado_en": self.creado_en.isoformat() + "Z" if self.creado_en else None,
            "observado_en": self.observado_en.isoformat() + "Z" if self.observado_en else None,
            "revisado_en": self.revisado_en.isoformat() + "Z" if self.revisado_en else None,
            "resultado": self.resultado,
        }
