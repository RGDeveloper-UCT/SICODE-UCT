"""Intervenciones sobre el inventario maestro de Control 09."""
from datetime import datetime
from app import db

class MantenimientoEquipo(db.Model):
    __tablename__ = "mantenimientos_equipos"
    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos_institucionales.id", ondelete="RESTRICT"), nullable=False, index=True)
    boleta_id = db.Column(db.Integer, db.ForeignKey("servicios_soporte_tecnico.id", ondelete="SET NULL"), nullable=True, index=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="PREVENTIVO")
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)
    diagnostico = db.Column(db.Text, nullable=False, default="")
    trabajo_realizado = db.Column(db.Text, nullable=False, default="")
    respaldo_mb = db.Column(db.Numeric(12, 2), nullable=True)
    estado_final = db.Column(db.String(40), nullable=True)
    requiere_seguimiento = db.Column(db.Boolean, nullable=False, default=False)
    checklist_version = db.Column(db.Integer, nullable=False, default=1)
    checklist = db.Column(db.JSON, nullable=False, default=list)
    datos_equipo = db.Column(db.JSON, nullable=False, default=dict)
    iniciado_en = db.Column(db.DateTime, nullable=True)
    tramo_iniciado_en = db.Column(db.DateTime, nullable=True)
    segundos_acumulados = db.Column(db.Integer, nullable=False, default=0)
    cerrado_en = db.Column(db.DateTime, nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    equipo = db.relationship("EquipoInstitucional", backref=db.backref("mantenimientos", lazy="dynamic"))
    boleta = db.relationship("ServicioSoporteTecnico")
    tecnico = db.relationship("Usuario")

    @property
    def numero(self):
        return f"MNT-{self.id:06d}" if self.id else "Automático"

    def segundos(self, ahora=None):
        ahora = ahora or datetime.utcnow()
        adicional = max(0, int((ahora - self.tramo_iniciado_en).total_seconds())) if self.tramo_iniciado_en else 0
        return self.segundos_acumulados + adicional

    def cambiar_reloj(self, accion, ahora=None):
        ahora = ahora or datetime.utcnow()
        if self.estado == "FINALIZADO":
            raise ValueError("Un mantenimiento finalizado no puede reanudarse.")
        if accion == "iniciar":
            if not self.tramo_iniciado_en:
                self.iniciado_en = self.iniciado_en or ahora
                self.tramo_iniciado_en = ahora
                self.estado = "EN_PROCESO"
        elif accion == "pausar":
            if self.tramo_iniciado_en:
                self.segundos_acumulados = self.segundos(ahora)
                self.tramo_iniciado_en = None
                self.estado = "PAUSADO"
        else:
            raise ValueError("Acción de reloj no reconocida.")
