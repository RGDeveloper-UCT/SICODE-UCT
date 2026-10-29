"""Dominio autónomo de NO PORTADORES (NP). Sin FK a expedientes/SP."""
from datetime import date, datetime
import re

from sqlalchemy import text
from sqlalchemy.orm import validates
from app import db


def normalizar_np(valor):
    texto = (valor or "").strip().upper()
    texto = re.sub(r"^NP[\\s:#-]*", "", texto).strip()
    if not texto or texto.startswith("SP"):
        return ""
    return "NP-" + texto


class NoPortador(db.Model):
    __tablename__ = "no_portadores"

    id = db.Column(db.Integer, primary_key=True)
    numero_np = db.Column(db.String(50), nullable=False, unique=True, index=True)
    codigo_interno = db.Column(db.String(50), nullable=False, unique=True)
    nombre_referencia = db.Column(db.String(150))
    motivo_no_instalacion = db.Column(db.Text, nullable=False)
    fecha_no_instalacion = db.Column(db.Date)
    estado_administrativo = db.Column(db.String(80), nullable=False, default="Activo")
    estado_fisico_documental = db.Column(db.String(80), nullable=False, default="Pendiente de verificación")
    expediente_fisico_registrado = db.Column(db.Boolean, nullable=False, default=False)
    folios_rectificados = db.Column(db.Integer)
    anexos_rectificados = db.Column(db.Integer)
    rectificado_en = db.Column(db.DateTime)
    rectificado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    nombres = db.Column(db.String(150))
    apellidos = db.Column(db.String(150))
    genero = db.Column(db.String(30))
    fecha_nacimiento = db.Column(db.Date)
    fecha_instalacion = db.Column(db.Date)
    fecha_desinstalacion = db.Column(db.Date)
    expediente_oj = db.Column(db.String(120))
    delito = db.Column(db.Text)
    estado_portador = db.Column(db.String(100))
    juez = db.Column(db.String(250))
    juzgado_tribunal = db.Column(db.String(500))
    abogado = db.Column(db.String(250))
    residencia = db.Column(db.Text)
    municipio = db.Column(db.String(150))
    departamento = db.Column(db.String(150))
    zona_inclusion = db.Column(db.Text)
    zona_exclusion = db.Column(db.Text)
    zona_prevencion = db.Column(db.Text)
    financiamiento = db.Column(db.String(150))
    lugar_instalacion = db.Column(db.Text)
    estado_monitoreo = db.Column(db.String(120))
    telefono = db.Column(db.String(80))
    municipio_residencia = db.Column(db.String(150))
    departamento_residencia = db.Column(db.String(150))
    observaciones = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    rectificado_por = db.relationship("Usuario", foreign_keys=[rectificado_por_id])

    @validates("numero_np")
    def _numero_np(self, _clave, valor):
        normalizado = normalizar_np(valor)
        if not normalizado:
            raise ValueError("Número NP inválido")
        return normalizado

    @property
    def rectificacion_completa(self):
        return bool(self.folios_rectificados is not None and self.folios_rectificados > 0
                    and self.anexos_rectificados is not None and self.anexos_rectificados >= 0)

    @property
    def prestamo_activo(self):
        return next((p for p in self.prestamos if p.activo and p.estado == "En préstamo"), None)

    @property
    def disponibilidad(self):
        if not self.expediente_fisico_registrado:
            return "Sin expediente físico"
        if not self.activo:
            return "Inactivo"
        return "En préstamo" if self.prestamo_activo else "Disponible"

    @property
    def total_folios_activos(self):
        return sum(d.total_folios for d in self.documentos if d.activo)

    @property
    def prestamos_vencidos(self):
        return [p for p in self.prestamos if p.activo and p.estado == "En préstamo"
                and p.fecha_estimada_devolucion and p.fecha_estimada_devolucion < date.today()]


class UbicacionNP(db.Model):
    __tablename__ = "ubicaciones_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, unique=True)
    archivador = db.Column(db.String(80))
    sicoin = db.Column(db.String(80))
    estante = db.Column(db.String(80))
    caja = db.Column(db.String(80))
    modulo = db.Column(db.String(80))
    posicion = db.Column(db.String(80))
    observaciones = db.Column(db.Text)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("ubicacion", uselist=False))


class DocumentoNP(db.Model):
    __tablename__ = "documentos_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    nombre_documento = db.Column(db.String(180), nullable=False)
    tipo_documento = db.Column(db.String(80), nullable=False, default="Documento")
    folio_inicio = db.Column(db.Integer, nullable=False)
    folio_fin = db.Column(db.Integer, nullable=False)
    total_folios = db.Column(db.Integer, nullable=False)
    estado_revision = db.Column(db.String(80), nullable=False, default="Pendiente de revisión")
    es_anexo = db.Column(db.Boolean, nullable=False, default=False)
    indice_numero_anexo = db.Column(db.Integer)
    indice_titulo_anexo = db.Column(db.String(180))
    indice_orden = db.Column(db.Integer)
    observaciones = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("documentos", lazy=True))
    __table_args__ = (
        db.CheckConstraint("folio_inicio >= 1", name="ck_np_documento_inicio"),
        db.CheckConstraint("folio_fin >= folio_inicio", name="ck_np_documento_rango"),
        db.CheckConstraint("total_folios = folio_fin - folio_inicio + 1", name="ck_np_documento_total"),
        db.Index("ix_np_documentos_folios", "np_id", "folio_inicio", "folio_fin"),
    )


class AnexoNP(db.Model):
    __tablename__ = "anexos_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    numero_anexo = db.Column(db.String(50))
    titulo = db.Column(db.String(180), nullable=False)
    tipo_anexo = db.Column(db.String(120))
    fecha_recepcion = db.Column(db.Date)
    persona_entrega = db.Column(db.String(180))
    rc = db.Column(db.String(80))
    providencia = db.Column(db.String(120))
    folios = db.Column(db.String(80))
    escaneado = db.Column(db.Boolean, nullable=False, default=False)
    fecha_escaneado = db.Column(db.Date)
    observaciones = db.Column(db.Text)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("anexos", lazy=True))


class PrestamoNP(db.Model):
    __tablename__ = "prestamos_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    numero_control = db.Column(db.String(80), nullable=False, unique=True)
    solicitante = db.Column(db.String(150), nullable=False)
    persona_entrega = db.Column(db.String(150), nullable=False)
    persona_recibe = db.Column(db.String(150), nullable=False)
    fecha_prestamo = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_estimada_devolucion = db.Column(db.Date)
    fecha_real_devolucion = db.Column(db.DateTime)
    persona_devuelve = db.Column(db.String(150))
    persona_recibe_devolucion = db.Column(db.String(150))
    estado = db.Column(db.String(50), nullable=False, default="En préstamo")
    observaciones = db.Column(db.Text)
    observaciones_devolucion = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("prestamos", lazy=True))
    __table_args__ = (
        db.CheckConstraint("estado IN ('En préstamo','Devuelto')", name="ck_np_prestamo_estado"),
        db.Index("uq_np_prestamo_activo", "np_id", unique=True,
                 postgresql_where=text("estado = 'En préstamo' AND activo = true"),
                 sqlite_where=text("estado = 'En préstamo' AND activo = 1")),
    )


class VerificacionNP(db.Model):
    __tablename__ = "verificaciones_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default="INTEGRAL")
    resultado = db.Column(db.String(80), nullable=False)
    folios_verificados = db.Column(db.Integer)
    observaciones = db.Column(db.Text)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("verificaciones", lazy=True))
    __table_args__ = (
        db.CheckConstraint("tipo IN ('FISICA','DOCUMENTAL','INTEGRAL')", name="ck_np_verificacion_tipo"),
        db.CheckConstraint("resultado IN ('Verificado','Con observaciones','Incompleto','No localizado')", name="ck_np_verificacion_resultado"),
    )


class AlertaNP(db.Model):
    __tablename__ = "alertas_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    tipo_alerta = db.Column(db.String(100), nullable=False)
    titulo = db.Column(db.String(180), nullable=False)
    descripcion = db.Column(db.Text)
    gravedad = db.Column(db.String(50), nullable=False, default="Media")
    estado = db.Column(db.String(50), nullable=False, default="Abierta")
    creada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    cerrada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cerrado_en = db.Column(db.DateTime)
    np = db.relationship("NoPortador", backref=db.backref("alertas", lazy=True))


class TrasladoVirtualNP(db.Model):
    __tablename__ = "traslados_virtuales_np"
    id = db.Column(db.Integer, primary_key=True)
    np_id = db.Column(db.Integer, db.ForeignKey("no_portadores.id"), nullable=False, index=True)
    numero_constancia = db.Column(db.String(80), nullable=False, unique=True)
    destinatario = db.Column(db.String(180), nullable=False)
    dependencia_destino = db.Column(db.String(220))
    plataforma = db.Column(db.String(80), nullable=False)
    enlace_corto = db.Column(db.String(500), nullable=False)
    asunto = db.Column(db.String(250), nullable=False)
    observaciones = db.Column(db.Text)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    np = db.relationship("NoPortador", backref=db.backref("traslados_virtuales", lazy=True))
