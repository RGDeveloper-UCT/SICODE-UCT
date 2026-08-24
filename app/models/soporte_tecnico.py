from datetime import datetime

from app import db


class ServicioSoporteTecnico(db.Model):
    """Boleta estructurada de soporte técnico vinculada al registro operativo.

    La tabla guarda únicamente metadatos administrativos y técnicos de la
    atención. No almacena copias de archivos, respaldos, credenciales ni
    documentos del usuario atendido.
    """

    __tablename__ = "servicios_soporte_tecnico"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(
        db.Integer,
        db.ForeignKey("registros_coordinacion.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    numero_boleta = db.Column(db.String(40), nullable=False, unique=True, index=True)
    fecha_hora_solicitud = db.Column(db.DateTime, nullable=False, index=True)

    # 1. Datos del usuario y ubicación
    usuario_solicitante = db.Column(db.String(180), nullable=False, index=True)
    puesto_cargo = db.Column(db.String(160), nullable=True)
    coordinacion_area = db.Column(db.String(180), nullable=False, index=True)
    tecnico_asignado = db.Column(db.String(180), nullable=False, index=True)

    # 2–4. Tipo y detalle funcional. JSON permite conservar las selecciones
    # múltiples de la boleta sin crear una tabla por cada casilla de verificación.
    tipos_servicio = db.Column(db.JSON, nullable=False, default=list)
    gestion_usuario_detalles = db.Column(db.JSON, nullable=False, default=list)
    hardware_detalles = db.Column(db.JSON, nullable=False, default=list)
    software_detalles = db.Column(db.JSON, nullable=False, default=list)
    instalacion_detalles = db.Column(db.JSON, nullable=False, default=list)
    traslado_detalles = db.Column(db.JSON, nullable=False, default=list)
    revision_detalles = db.Column(db.JSON, nullable=False, default=list)
    otro_servicio_ti = db.Column(db.String(220), nullable=True)
    otro_instalacion = db.Column(db.String(220), nullable=True)
    otro_traslado = db.Column(db.String(220), nullable=True)
    otro_revision = db.Column(db.String(220), nullable=True)

    # 5. Identificación de equipo
    tipo_equipo = db.Column(db.String(40), nullable=True)
    tipo_equipo_otro = db.Column(db.String(80), nullable=True)
    marca_modelo = db.Column(db.String(180), nullable=True)
    numero_serie = db.Column(db.String(120), nullable=True, index=True)
    inventario = db.Column(db.String(120), nullable=True, index=True)
    ip_nombre_equipo = db.Column(db.String(180), nullable=True, index=True)

    # 6–8. Solicitud, diagnóstico y cierre
    descripcion_solicitud = db.Column(db.Text, nullable=False)
    diagnostico_trabajo = db.Column(db.Text, nullable=True)
    estado_final = db.Column(db.String(30), nullable=False, default="PENDIENTE", index=True)
    seguimiento = db.Column(db.Boolean, nullable=False, default=False, index=True)
    fecha_hora_cierre = db.Column(db.DateTime, nullable=True)
    tiempo_empleado = db.Column(db.String(80), nullable=True)
    observaciones_cierre = db.Column(db.Text, nullable=True)

    # El sistema registra nombres/fechas para imprimir la boleta. La firma se
    # realiza físicamente sobre el PDF impreso; no se captura imagen de firma.
    nombre_firma_usuario = db.Column(db.String(180), nullable=True)
    fecha_firma_usuario = db.Column(db.Date, nullable=True)
    nombre_firma_tecnico = db.Column(db.String(180), nullable=True)
    fecha_firma_tecnico = db.Column(db.Date, nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    registro = db.relationship(
        "RegistroCoordinacion",
        backref=db.backref("soporte_tecnico", uselist=False, cascade="all, delete-orphan"),
    )

    @property
    def estado_legible(self):
        return {
            "RESUELTO": "Resuelto",
            "PARCIAL": "Parcial",
            "PENDIENTE": "Pendiente",
            "ESCALADO": "Escalado",
        }.get(self.estado_final, self.estado_final or "Pendiente")

    @property
    def requiere_equipo(self):
        return bool(
            set(self.tipos_servicio or [])
            & {"HARDWARE", "SOFTWARE", "INSTALACION", "TRASLADO", "REVISION"}
        )
