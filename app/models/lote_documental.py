from datetime import datetime

from sqlalchemy import event

from app import db


class SegmentoDocumental(db.Model):
    """Documento lógico detectado dentro de un PDF multipágina.

    No almacena el PDF, imágenes ni texto OCR. Solo conserva página/rango,
    clasificación, metadatos autorizados, confianza y la decisión humana.
    """

    __tablename__ = "segmentos_documentales"

    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(
        db.Integer,
        db.ForeignKey("analisis_documentales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expediente_id = db.Column(
        db.Integer,
        db.ForeignKey("expedientes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    orden = db.Column(db.Integer, nullable=False)
    pagina_inicio = db.Column(db.Integer, nullable=False)
    pagina_fin = db.Column(db.Integer, nullable=False)
    tipo_detectado = db.Column(db.String(40), nullable=False, default="OTRO", index=True)
    tipo_confirmado = db.Column(db.String(40), nullable=True)
    estado = db.Column(db.String(30), nullable=False, default="PENDIENTE_VALIDACION", index=True)
    calidad_global = db.Column(db.Integer, nullable=False, default=0)
    datos_detectados = db.Column(db.JSON, nullable=False, default=dict)
    confianzas = db.Column(db.JSON, nullable=False, default=dict)
    fuentes_campos = db.Column(db.JSON, nullable=False, default=dict)
    discrepancias = db.Column(db.JSON, nullable=False, default=list)
    caracteristicas_clasificacion = db.Column(db.JSON, nullable=False, default=list)
    datos_confirmados = db.Column(db.JSON, nullable=True)
    ia_utilizada = db.Column(db.Boolean, nullable=False, default=False)
    ia_modelo = db.Column(db.String(80), nullable=True)
    registro_id = db.Column(
        db.Integer,
        db.ForeignKey("registros_coordinacion.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    documento_expediente_id = db.Column(
        db.Integer,
        db.ForeignKey("documentos_expediente.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    confirmado_en = db.Column(db.DateTime, nullable=True)

    analisis = db.relationship(
        "AnalisisDocumental",
        backref=db.backref("segmentos", lazy="select", cascade="all, delete-orphan", order_by="SegmentoDocumental.orden"),
    )
    expediente = db.relationship("Expediente", foreign_keys=[expediente_id])
    registro = db.relationship("RegistroCoordinacion", foreign_keys=[registro_id])
    documento_expediente = db.relationship("DocumentoExpediente", foreign_keys=[documento_expediente_id])

    @property
    def paginas(self):
        return max(0, int(self.pagina_fin or 0) - int(self.pagina_inicio or 0) + 1)

    @property
    def pendiente(self):
        return self.estado == "PENDIENTE_VALIDACION"


@event.listens_for(SegmentoDocumental, "before_insert")
def _blindar_dpi_antes_de_persistir(_mapper, _connection, target):
    """Defensa adicional para impedir persistencia accidental de PII desde DPI.

    La asociación administrativa posterior (por ejemplo SP confirmado por el
    usuario) se guarda en `datos_confirmados`, no en la propuesta OCR inicial.
    """
    datos = dict(target.datos_detectados or {})
    tipo = str(target.tipo_detectado or datos.get("tipo_documento_lote") or "").upper()
    if tipo != "DPI":
        return

    target.datos_detectados = {
        "tipo_documento_lote": "DPI",
        "pagina_inicio_pdf": datos.get("pagina_inicio_pdf"),
        "pagina_fin_pdf": datos.get("pagina_fin_pdf"),
    }
    target.confianzas = {
        "tipo_documento_lote": (target.confianzas or {}).get("tipo_documento_lote", 0.0)
    }
    target.fuentes_campos = {
        "tipo_documento_lote": (target.fuentes_campos or {}).get("tipo_documento_lote", [])
    }


class AprendizajeDocumental(db.Model):
    """Métricas agregadas de retroalimentación humana por tipo documental."""

    __tablename__ = "aprendizaje_documental"

    id = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(40), nullable=False, unique=True, index=True)
    muestras_confirmadas = db.Column(db.Integer, nullable=False, default=0)
    clasificaciones_correctas = db.Column(db.Integer, nullable=False, default=0)
    reclasificaciones = db.Column(db.Integer, nullable=False, default=0)
    campos_confirmados = db.Column(db.Integer, nullable=False, default=0)
    campos_corregidos = db.Column(db.Integer, nullable=False, default=0)
    nivel_aprendizaje = db.Column(db.Integer, nullable=False, default=0)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PatronAprendizajeDocumental(db.Model):
    """Peso aprendido para características seguras y predefinidas.

    `caracteristica` nunca contiene texto libre ni datos personales; solo claves
    internas como kw_boleta, kw_providencia, kw_dpi o kw_acta.
    """

    __tablename__ = "patrones_aprendizaje_documental"

    id = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(40), nullable=False, index=True)
    caracteristica = db.Column(db.String(80), nullable=False, index=True)
    aciertos = db.Column(db.Integer, nullable=False, default=0)
    errores = db.Column(db.Integer, nullable=False, default=0)
    peso = db.Column(db.Float, nullable=False, default=1.0)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("tipo_documento", "caracteristica", name="uq_patron_aprendizaje_tipo_caracteristica"),
    )
