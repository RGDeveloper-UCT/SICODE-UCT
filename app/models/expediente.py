from datetime import date, datetime

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates

from app import db


class Expediente(db.Model):
    __tablename__ = "expedientes"

    id = db.Column(db.Integer, primary_key=True)
    codigo_interno = db.Column(db.String(50), unique=True, nullable=False)
    no_sp = db.Column(db.String(50), unique=True, nullable=False, index=True)

    nombre_referencia = db.Column(db.String(150), nullable=True)
    estado_administrativo = db.Column(db.String(80), nullable=False, default="Activo")

    # Compatibilidad histórica: se conserva exactamente la misma columna en BD
    # para no tocar registros previos. Desde ahora el estado visible/vigente se
    # deriva del árbol documental por medio de ``estado_fisico_documental``.
    _estado_fisico_documental_legacy = db.Column(
        "estado_fisico_documental",
        db.String(80),
        nullable=False,
        default="Pendiente de verificación",
    )

    # El registro maestro del SP y la existencia del expediente físico no son
    # sinónimos. Portadores puede conocer un SP antes de recibir su expediente.
    expediente_fisico_registrado = db.Column(db.Boolean, nullable=False, default=True, index=True)

    # Rectificación física previa a préstamo/traslado. Estos valores son el
    # conteo maestro confirmado manualmente del expediente y no se calculan a
    # partir de documentos sensibles ni archivos cargados al sistema.
    folios_rectificados = db.Column(db.Integer, nullable=True)
    anexos_rectificados = db.Column(db.Integer, nullable=True)
    rectificado_en = db.Column(db.DateTime, nullable=True)
    rectificado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    rectificado_por = db.relationship("Usuario", foreign_keys=[rectificado_por_id], lazy="joined")

    nombres = db.Column(db.String(150), nullable=True)
    apellidos = db.Column(db.String(150), nullable=True)
    genero = db.Column(db.String(30), nullable=True)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    fecha_instalacion = db.Column(db.Date, nullable=True)
    fecha_desinstalacion = db.Column(db.Date, nullable=True)
    expediente_oj = db.Column(db.String(120), nullable=True)
    delito = db.Column(db.Text, nullable=True)
    estado_portador = db.Column(db.String(100), nullable=True)
    juez = db.Column(db.String(250), nullable=True)
    juzgado_tribunal = db.Column(db.String(500), nullable=True)
    abogado = db.Column(db.String(250), nullable=True)
    residencia = db.Column(db.Text, nullable=True)
    municipio = db.Column(db.String(150), nullable=True)
    departamento = db.Column(db.String(150), nullable=True)
    zona_inclusion = db.Column(db.Text, nullable=True)
    zona_exclusion = db.Column(db.Text, nullable=True)
    zona_prevencion = db.Column(db.Text, nullable=True)
    financiamiento = db.Column(db.String(150), nullable=True)
    lugar_instalacion = db.Column(db.Text, nullable=True)
    estado_monitoreo = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(80), nullable=True)
    municipio_residencia = db.Column(db.String(150), nullable=True)
    departamento_residencia = db.Column(db.String(150), nullable=True)
    ultima_sincronizacion_portadores = db.Column(db.DateTime, nullable=True)

    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @hybrid_property
    def estado_fisico_documental(self):
        """Estado documental vigente y derivado del árbol maestro del SP."""
        from app.services.estado_documental_service import estado_documental_actual

        return estado_documental_actual(self)

    @estado_fisico_documental.setter
    def estado_fisico_documental(self, valor):
        # Las rutas históricas todavía asignan este atributo. Para no alterar
        # registros anteriores, esas asignaciones solo inicializan expedientes
        # nuevos; las verificaciones actualizan explícitamente el espejo legacy.
        if self.id is None or self._estado_fisico_documental_legacy is None:
            self._estado_fisico_documental_legacy = valor

    @estado_fisico_documental.expression
    def estado_fisico_documental(cls):
        # Consultas SQL anteriores continúan funcionando sobre la columna
        # histórica. La presentación vigente usa siempre el servicio central.
        return cls._estado_fisico_documental_legacy

    @property
    def estado_fisico_documental_legacy(self):
        return self._estado_fisico_documental_legacy

    @property
    def estado_documental_resumen(self):
        from app.services.estado_documental_service import calcular_estado_documental

        return calcular_estado_documental(self)

    @validates("no_sp")
    def _normalizar_no_sp(self, _clave, valor):
        import re

        if valor is None:
            return valor
        texto = str(valor).strip()
        texto = re.sub(r"^SP\s*[-:#]?\s*", "", texto, flags=re.IGNORECASE).strip()
        if texto.endswith(".0") and texto[:-2].isdigit():
            texto = texto[:-2]
        return str(int(texto)) if texto.isdigit() else texto.upper()

    @validates("estado_administrativo")
    def _estado_administrativo_sin_prestamo(self, _clave, valor):
        if valor in {"En préstamo", "Devuelto"}:
            return "Activo"
        return valor

    @property
    def rectificacion_completa(self):
        return bool(
            self.folios_rectificados is not None
            and self.folios_rectificados > 0
            and self.anexos_rectificados is not None
            and self.anexos_rectificados >= 0
        )

    @property
    def anexos_rectificados_activos(self):
        return [anexo for anexo in self.anexos_rectificados_detalle if anexo.activo]

    @property
    def prestamo_activo(self):
        return next(
            (prestamo for prestamo in self.prestamos if prestamo.activo and prestamo.estado == "En préstamo"),
            None,
        )

    @property
    def disponibilidad(self):
        if not self.expediente_fisico_registrado:
            return "Sin expediente físico"
        if not self.activo:
            return "Inactivo"
        return "En préstamo" if self.prestamo_activo else "Disponible"

    @property
    def documentos_activos(self):
        return [documento for documento in self.documentos_indice if documento.activo]

    @property
    def total_folios_activos(self):
        return sum(documento.total_folios or 0 for documento in self.documentos_activos)

    @property
    def alertas_pendientes(self):
        return [alerta for alerta in self.alertas if alerta.estado in {"Abierta", "En revisión"}]

    @property
    def alertas_altas_pendientes(self):
        return [alerta for alerta in self.alertas_pendientes if alerta.gravedad == "Alta"]

    @property
    def prestamos_activos(self):
        return [prestamo for prestamo in self.prestamos if prestamo.activo and prestamo.estado == "En préstamo"]

    @property
    def prestamos_vencidos(self):
        hoy = date.today()
        return [
            prestamo
            for prestamo in self.prestamos_activos
            if prestamo.fecha_estimada_devolucion and prestamo.fecha_estimada_devolucion < hoy
        ]

    @property
    def ultimo_prestamo(self):
        if not self.prestamos:
            return None
        return max(
            self.prestamos,
            key=lambda prestamo: prestamo.fecha_prestamo or datetime.min,
        )

    def __repr__(self):
        return f"<Expediente SP {self.no_sp}>"
