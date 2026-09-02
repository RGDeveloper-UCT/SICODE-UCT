from datetime import datetime

from app import db


class RegistroCoordinacion(db.Model):
    __tablename__ = "registros_coordinacion"

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(40), nullable=False, index=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=True, index=True)
    no_sp_referencia = db.Column(db.String(50), nullable=True, index=True)
    rc = db.Column(db.String(80), nullable=True, index=True)
    providencia = db.Column(db.String(120), nullable=True, index=True)
    fecha_recepcion = db.Column(db.Date, nullable=True, index=True)

    # Metadatos comunes de recepción. El usuario de sesión es quien recibe;
    # persona_entrega identifica quién trajo/remitió la documentación y
    # folios_recepcion centraliza el dato común sin depender del subtipo.
    persona_entrega = db.Column(db.String(180), nullable=True, index=True)
    folios_recepcion = db.Column(db.String(80), nullable=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    usuario_origen = db.Column(db.String(120), nullable=True)
    estado = db.Column(db.String(50), nullable=False, default="Completo", index=True)
    observaciones = db.Column(db.Text, nullable=True)
    origen_registro = db.Column(db.String(30), nullable=False, default="MANUAL")
    archivo_origen = db.Column(db.String(255), nullable=True)
    lote_importacion = db.Column(db.String(64), nullable=True, index=True)
    hoja_origen = db.Column(db.String(80), nullable=True)
    fila_origen = db.Column(db.Integer, nullable=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = db.relationship("Expediente", backref=db.backref("registros_coordinacion", lazy=True))
    usuario = db.relationship("Usuario", backref=db.backref("registros_coordinacion", lazy=True))

    __table_args__ = (
        db.Index("ix_registro_coord_tipo_fecha", "tipo", "fecha_recepcion"),
        db.UniqueConstraint("lote_importacion", "hoja_origen", "fila_origen", name="uq_registro_coord_origen_fila"),
    )


class PagoCoordinacion(db.Model):
    __tablename__ = "pagos_coordinacion"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    # Legacy compatible: nuevos flujos usan RegistroCoordinacion.folios_recepcion.
    folios = db.Column(db.String(80), nullable=True)
    periodo_desde = db.Column(db.Date, nullable=True)
    periodo_hasta = db.Column(db.Date, nullable=True)
    periodo_texto = db.Column(db.String(120), nullable=True)
    boleta = db.Column(db.String(120), nullable=True)
    banco = db.Column(db.String(120), nullable=True, index=True)
    total = db.Column(db.Numeric(12, 2), nullable=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("pago", uselist=False, cascade="all, delete-orphan"))


class MovimientoDispositivo(db.Model):
    __tablename__ = "movimientos_dispositivo"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    movimiento = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.String(180), nullable=True)
    # Legacy compatible: nuevos flujos usan RegistroCoordinacion.folios_recepcion.
    folios = db.Column(db.String(80), nullable=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("movimiento_dispositivo", uselist=False, cascade="all, delete-orphan"))


class AnexoCoordinacion(db.Model):
    __tablename__ = "anexos_coordinacion"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    documento_expediente_id = db.Column(
        db.Integer,
        db.ForeignKey("documentos_expediente.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    tipo_anexo = db.Column(db.String(120), nullable=True)
    titulo = db.Column(db.String(180), nullable=True)
    # Legacy compatible: nuevos flujos usan RegistroCoordinacion.folios_recepcion.
    folios = db.Column(db.String(80), nullable=True)
    escaneado = db.Column(db.Boolean, nullable=False, default=False)
    fecha_escaneado = db.Column(db.Date, nullable=True)
    numero_anexo = db.Column(db.String(50), nullable=True)
    # Un anexo vencido/histórico conserva su número físico original, pero no
    # avanza el contador maestro de anexos vigentes del expediente.
    es_vencido = db.Column(db.Boolean, nullable=False, default=False, index=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("anexo_coordinacion", uselist=False, cascade="all, delete-orphan"))
    documento_expediente = db.relationship(
        "DocumentoExpediente",
        backref=db.backref("anexo_recepcion", uselist=False),
    )


class ReporteMonitoreo(db.Model):
    __tablename__ = "reportes_monitoreo"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    tipo_documento = db.Column(db.String(80), nullable=True, default="PROVIDENCIA")
    numero_reporte = db.Column(db.String(120), nullable=True)
    tipo_evento = db.Column(db.String(180), nullable=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("reporte_monitoreo", uselist=False, cascade="all, delete-orphan"))


class AnalisisRiesgo(db.Model):
    __tablename__ = "analisis_riesgo"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    tipo_documento = db.Column(db.String(80), nullable=True, default="PROVIDENCIA")
    correlativo = db.Column(db.String(120), nullable=True, index=True)
    tipo_evento = db.Column(db.String(180), nullable=True)

    registro = db.relationship(
        "RegistroCoordinacion",
        backref=db.backref("analisis_riesgo", uselist=False, cascade="all, delete-orphan"),
    )


class DocumentoEmitido(db.Model):
    __tablename__ = "documentos_emitidos"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    numero_documento = db.Column(db.String(120), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=True)
    destino = db.Column(db.String(180), nullable=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("documento_emitido", uselist=False, cascade="all, delete-orphan"))


class ActividadCoordinacion(db.Model):
    __tablename__ = "actividades_coordinacion"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    tipo_actividad = db.Column(db.String(100), nullable=True, index=True)
    area_apoyo = db.Column(db.String(180), nullable=True)
    descripcion = db.Column(db.Text, nullable=False)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("actividad_coordinacion", uselist=False, cascade="all, delete-orphan"))


class RemisionCoordinacion(db.Model):
    __tablename__ = "remisiones_coordinacion"

    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey("registros_coordinacion.id"), nullable=False, unique=True)
    destino = db.Column(db.String(180), nullable=False, default="Archivo/Bodega MINGOB")
    numero_control = db.Column(db.String(120), nullable=True, index=True)

    registro = db.relationship("RegistroCoordinacion", backref=db.backref("remision_coordinacion", uselist=False, cascade="all, delete-orphan"))


class RemisionExpediente(db.Model):
    __tablename__ = "remisiones_expedientes"

    id = db.Column(db.Integer, primary_key=True)
    remision_id = db.Column(db.Integer, db.ForeignKey("remisiones_coordinacion.id"), nullable=False, index=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=True, index=True)
    no_sp_referencia = db.Column(db.String(50), nullable=False, index=True)
    folios = db.Column(db.String(80), nullable=True)
    anexos = db.Column(db.String(80), nullable=True)
    estado_foliacion = db.Column(db.String(80), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    remision = db.relationship("RemisionCoordinacion", backref=db.backref("expedientes_remitidos", lazy=True, cascade="all, delete-orphan"))
    expediente = db.relationship("Expediente", backref=db.backref("remisiones_coordinacion", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("remision_id", "no_sp_referencia", name="uq_remision_sp"),
    )