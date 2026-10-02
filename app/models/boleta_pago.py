from datetime import datetime

from app import db


class BoletaPagoSP(db.Model):
    """Copia histórica e inmutable de la boleta emitida para un pago de SP.

    El PDF final incluye la boleta administrativa y el comprobante bancario
    adjunto por el operador. Se conserva en PostgreSQL para que el respaldo
    institucional incluya el documento junto con sus metadatos y su hash.
    """

    __tablename__ = "boletas_pago_sp"

    id = db.Column(db.Integer, primary_key=True)
    pago_id = db.Column(
        db.Integer,
        db.ForeignKey("pagos_coordinacion.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    plantilla_version = db.Column(db.String(60), nullable=False)
    fecha_comprobante = db.Column(db.Date, nullable=False, index=True)

    expediente_numero = db.Column(db.String(120), nullable=True)
    organo_jurisdiccional = db.Column(db.String(500), nullable=True)
    nombre_sujeto = db.Column(db.String(180), nullable=False)
    dias_aplicados = db.Column(db.Integer, nullable=False, default=0)
    meses_aplicados = db.Column(db.Integer, nullable=False, default=0)
    tarifa_dia = db.Column(db.Numeric(12, 2), nullable=False)
    tarifa_mes = db.Column(db.Numeric(12, 2), nullable=False)

    banco_snapshot = db.Column(db.String(180), nullable=False)
    cuenta_snapshot = db.Column(db.String(80), nullable=False)
    cuenta_nombre_snapshot = db.Column(db.String(300), nullable=False)
    elaborado_por_snapshot = db.Column(db.String(180), nullable=True)
    contacto_snapshot = db.Column(db.String(220), nullable=True)
    base_legal_snapshot = db.Column(db.Text, nullable=False)

    comprobante_nombre = db.Column(db.String(255), nullable=False)
    comprobante_mime = db.Column(db.String(120), nullable=False)
    comprobante_sha256 = db.Column(db.String(64), nullable=False, index=True)

    pdf_nombre = db.Column(db.String(255), nullable=False)
    pdf_mime = db.Column(db.String(80), nullable=False, default="application/pdf")
    pdf_sha256 = db.Column(db.String(64), nullable=False, index=True)
    pdf_bytes = db.Column(db.LargeBinary, nullable=False)
    generado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    pago = db.relationship(
        "PagoCoordinacion",
        backref=db.backref("boleta_pdf", uselist=False, cascade="all, delete-orphan"),
    )

    @property
    def tamano_pdf(self):
        return len(self.pdf_bytes or b"")
