from datetime import datetime

from app import db


class AnalisisDocumental(db.Model):
    """Resultado persistido de una lectura temporal de PDF.

    Nunca almacena el archivo, imágenes, texto OCR completo ni el nombre del
    documento. Solo conserva metadatos administrativos autorizados, porcentajes
    y diagnósticos técnicos no sensibles para que el usuario valide la propuesta.
    """

    __tablename__ = "analisis_documentales"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey("expedientes.id"), nullable=True, index=True)
    registro_id = db.Column(
        db.Integer,
        db.ForeignKey("registros_coordinacion.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    tipo_objetivo = db.Column(db.String(30), nullable=False, default="AUTO")
    tipo_detectado = db.Column(db.String(30), nullable=False, default="DOCUMENTO")
    estado = db.Column(db.String(30), nullable=False, default="PENDIENTE_VALIDACION", index=True)

    paginas_pdf = db.Column(db.Integer, nullable=False, default=0)
    paginas_ocr = db.Column(db.Integer, nullable=False, default=0)
    metodo_extraccion = db.Column(db.String(30), nullable=False, default="TEXTO_PDF")

    # Exclusivamente metadatos en lista blanca; jamás texto OCR completo.
    datos_detectados = db.Column(db.JSON, nullable=False, default=dict)
    confianzas = db.Column(db.JSON, nullable=False, default=dict)
    discrepancias = db.Column(db.JSON, nullable=False, default=list)
    datos_confirmados = db.Column(db.JSON, nullable=True)

    # Diagnóstico visual seguro de la Fase 2. No contiene el texto OCR ni
    # fragmentos del documento: solo etapas, porcentajes, fuentes y tiempos.
    calidad_global = db.Column(db.Integer, nullable=True)
    pipeline_diagnostico = db.Column(db.JSON, nullable=True)
    fuentes_campos = db.Column(db.JSON, nullable=True)
    explicaciones_campos = db.Column(db.JSON, nullable=True)
    ia_utilizada = db.Column(db.Boolean, nullable=False, default=False)
    ia_modelo = db.Column(db.String(80), nullable=True)
    duracion_ms = db.Column(db.Integer, nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmado_en = db.Column(db.DateTime, nullable=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id], lazy="joined")
    expediente = db.relationship("Expediente", foreign_keys=[expediente_id], lazy="joined")
    registro = db.relationship("RegistroCoordinacion", foreign_keys=[registro_id], lazy="joined")

    @property
    def pendiente(self):
        return self.estado == "PENDIENTE_VALIDACION"

    @property
    def calidad_etiqueta(self):
        valor = int(self.calidad_global or 0)
        if valor >= 90:
            return "Alta"
        if valor >= 70:
            return "Media"
        return "Revisión necesaria"

    def __repr__(self):
        return f"<AnalisisDocumental {self.id} {self.tipo_detectado} {self.estado}>"
