"""Catálogo de vulnerabilidades y boletas de inspección por activo institucional."""
from datetime import datetime
from app import db


class VulnerabilidadTI(db.Model):
    __tablename__ = "vulnerabilidades_ti"
    id = db.Column(db.Integer, primary_key=True)
    cve = db.Column(db.String(28), unique=True, index=True)
    fuente = db.Column(db.String(24), nullable=False, index=True)
    fuentes = db.Column(db.JSON, nullable=False, default=list)
    titulo = db.Column(db.String(220), nullable=False)
    fabricante = db.Column(db.String(140))
    producto = db.Column(db.String(160))
    severidad = db.Column(db.String(16), nullable=False, default="DESCONOCIDA", index=True)
    descripcion = db.Column(db.Text, nullable=False, default="")
    recomendacion = db.Column(db.Text, nullable=False, default="")
    referencia = db.Column(db.String(500))
    fecha_publicacion = db.Column(db.Date)
    fecha_recibido = db.Column(db.Date)
    explotada = db.Column(db.Boolean, nullable=False, default=False)
    archivo_pdf = db.Column(db.String(80))
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


informe_vulnerabilidad_ti = db.Table(
    "informe_vulnerabilidad_ti",
    db.Column("informe_id", db.Integer, db.ForeignKey("informes_seguridad_ti.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("vulnerabilidad_id", db.Integer, db.ForeignKey("vulnerabilidades_ti.id", ondelete="RESTRICT"),
              primary_key=True),
)


class InformeSeguridadTI(db.Model):
    """Un informe CERT/MINGOB puede vincularse a varios CVE sin duplicarlos."""
    __tablename__ = "informes_seguridad_ti"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(220), nullable=False)
    emisor = db.Column(db.String(160), nullable=False, default="CERT MINGOB")
    tecnologia = db.Column(db.String(40), nullable=False)
    fecha_informe = db.Column(db.Date)
    fecha_recibido = db.Column(db.Date)
    resumen = db.Column(db.Text, nullable=False, default="")
    archivo_nombre = db.Column(db.String(80), nullable=False, unique=True)
    nombre_original = db.Column(db.String(180), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, unique=True, index=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creador = db.relationship("Usuario")
    vulnerabilidades = db.relationship("VulnerabilidadTI", secondary=informe_vulnerabilidad_ti,
                                        backref="informes", lazy="select")


class SincronizacionVulnerabilidadesTI(db.Model):
    __tablename__ = "sincronizaciones_vulnerabilidades_ti"
    id = db.Column(db.Integer, primary_key=True)
    fuente = db.Column(db.String(24), nullable=False, unique=True)
    ultimo_intento = db.Column(db.DateTime)
    ultimo_exito = db.Column(db.DateTime)
    ultimo_error = db.Column(db.String(400))
    registros_nuevos = db.Column(db.Integer, nullable=False, default=0)


class BoletaSeguridadTI(db.Model):
    """La fila pertenece a un equipo existente. Cierre y checklist son inmutables."""
    __tablename__ = "boletas_seguridad_ti"
    id = db.Column(db.Integer, primary_key=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos_institucionales.id", ondelete="RESTRICT"), nullable=False, index=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR", index=True)
    checklist_version = db.Column(db.Integer, nullable=False, default=1)
    checklist = db.Column(db.JSON, nullable=False, default=list)
    datos_equipo = db.Column(db.JSON, nullable=False, default=dict)
    versiones = db.Column(db.JSON, nullable=False, default=dict)
    diagnostico = db.Column(db.Text, nullable=False, default="")
    acciones = db.Column(db.Text, nullable=False, default="")
    resultado_final = db.Column(db.String(30))
    requiere_seguimiento = db.Column(db.Boolean, nullable=False, default=False)
    iniciado_en = db.Column(db.DateTime)
    tramo_iniciado_en = db.Column(db.DateTime)
    segundos_acumulados = db.Column(db.Integer, nullable=False, default=0)
    cerrado_en = db.Column(db.DateTime)
    # Se conserva el registro y la numeración: eliminación lógica reversible.
    estado_anterior = db.Column(db.String(20))
    anulada_en = db.Column(db.DateTime)
    anulada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="RESTRICT"))
    motivo_anulacion = db.Column(db.String(400))

    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    equipo = db.relationship("EquipoInstitucional")
    tecnico = db.relationship("Usuario", foreign_keys=[tecnico_id])
    anulada_por = db.relationship("Usuario", foreign_keys=[anulada_por_id])

    @property
    def numero(self):
        return f"BSI-{self.id:06d}" if self.id else "Automático"

    def segundos(self, ahora=None):
        ahora = ahora or datetime.utcnow()
        extra = max(0, int((ahora - self.tramo_iniciado_en).total_seconds())) if self.tramo_iniciado_en else 0
        return self.segundos_acumulados + extra

    def cambiar_reloj(self, accion, ahora=None):
        ahora = ahora or datetime.utcnow()
        if self.estado in ("FINALIZADO", "ANULADA"):
            raise ValueError("La boleta cerrada no admite cambios.")
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
            raise ValueError("Acción de cronómetro inválida.")
