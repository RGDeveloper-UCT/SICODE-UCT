from datetime import datetime
from app import db


class Expediente(db.Model):
    __tablename__ = "expedientes"

    id = db.Column(db.Integer, primary_key=True)

    codigo_interno = db.Column(db.String(50), unique=True, nullable=False)
    no_sp = db.Column(db.String(50), unique=True, nullable=False)

    nombre_referencia = db.Column(db.String(150), nullable=True)
    estado_administrativo = db.Column(db.String(80), nullable=False, default="Activo")
    estado_fisico_documental = db.Column(db.String(80), nullable=False, default="Pendiente de verificación")

    # Datos maestros provenientes de la manta diaria de Sujetos Portadores.
    # Se mantienen separados de los estados administrativos/documentales de SICODE.
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

    def __repr__(self):
        return f"<Expediente SP {self.no_sp}>"
