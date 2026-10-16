"""Inventario maestro de activos informáticos."""
from datetime import datetime
from app import db

class EquipoInstitucional(db.Model):
    __tablename__ = "equipos_institucionales"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(60), nullable=False, unique=True, index=True)  # SICOIN
    tipo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(120))
    serie = db.Column(db.String(120), unique=True)
    numero_inventario = db.Column(db.String(120), unique=True)  # legado: oculto, no eliminar datos históricos
    ip_estatica = db.Column(db.String(45), nullable=True, index=True)
    area = db.Column(db.String(160))
    ubicacion = db.Column(db.String(160))
    responsable_usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)  # legado
    responsable_personal_id = db.Column(db.Integer, db.ForeignKey("personal_institucional.id"), index=True)
    acceso_institucional = db.Column(db.Boolean, nullable=False, default=True)
    tipo_acceso = db.Column(db.String(40), nullable=False, default="INTERNO")
    estado = db.Column(db.String(30), nullable=False, default="ACTIVO", index=True)
    observaciones = db.Column(db.Text)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    responsable = db.relationship("Usuario", foreign_keys=[responsable_usuario_id])
    personal_responsable = db.relationship("PersonalInstitucional", foreign_keys=[responsable_personal_id])
    creador = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def numero_registro(self):
        return f"UCT-EQ-{self.id:06d}" if self.id else "Automático al guardar"

    @property
    def numero_boleta(self):
        boletas = getattr(self, "boletas_soporte", None)
        ultima = max(boletas, key=lambda b: b.id, default=None) if boletas is not None else None
        return ultima.numero_boleta if ultima else None

    @property
    def nombre_responsable(self):
        if self.personal_responsable:
            return self.personal_responsable.nombre_completo
        return self.responsable.nombre if self.responsable else "Sin asignación"

    def snapshot(self):
        return {campo: getattr(self, campo) for campo in (
            "codigo", "tipo", "nombre", "marca", "modelo", "serie",
            "numero_inventario", "ip_estatica", "area", "ubicacion", "responsable_usuario_id",
            "responsable_personal_id", "acceso_institucional", "tipo_acceso",
            "estado", "observaciones"
        )}
