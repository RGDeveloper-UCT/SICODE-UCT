from datetime import date
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, DateField, DecimalField, HiddenField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

class RegistroBaseForm(FlaskForm):
    no_sp = StringField("No. de SP", validators=[DataRequired(), Length(max=50)])
    rc = StringField("RC", validators=[Optional(), Length(max=80)])
    providencia = StringField("Providencia", validators=[Optional(), Length(max=120)])
    fecha_recepcion = DateField("Fecha recibido", validators=[Optional()], default=date.today, format="%Y-%m-%d")
    observaciones = TextAreaField("Observaciones", validators=[Optional()])

class PagoForm(RegistroBaseForm):
    folios = StringField("Folios", validators=[Optional(), Length(max=80)])
    periodo_desde = DateField("Pago desde", validators=[Optional()], format="%Y-%m-%d")
    periodo_hasta = DateField("Pago hasta", validators=[Optional()], format="%Y-%m-%d")
    periodo_texto = StringField("Período si no se conoce fecha exacta", validators=[Optional(), Length(max=120)])
    boleta = StringField("Boleta", validators=[Optional(), Length(max=120)])
    total = DecimalField("Total", validators=[Optional()], places=2)
    submit = SubmitField("Guardar pago")

class MovimientoForm(RegistroBaseForm):
    descripcion = StringField("Descripción", validators=[Optional(), Length(max=180)], default="EXPEDIENTE")
    folios = StringField("Folios", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Guardar movimiento")

class AnexoForm(RegistroBaseForm):
    tipo_anexo = StringField("Tipo de anexo", validators=[Optional(), Length(max=120)])
    folios = StringField("Folios", validators=[Optional(), Length(max=80)])
    escaneado = BooleanField("Escaneado")
    fecha_escaneado = DateField("Fecha escaneado", validators=[Optional()], format="%Y-%m-%d")
    numero_anexo = StringField("Anexo No.", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Guardar anexo")

class MonitoreoForm(RegistroBaseForm):
    tipo_documento = StringField("Tipo de documento", validators=[Optional(), Length(max=80)], default="PROVIDENCIA")
    numero_reporte = StringField("Reporte No.", validators=[Optional(), Length(max=120)])
    tipo_evento = StringField("Tipo de reporte / evento", validators=[Optional(), Length(max=180)])
    submit = SubmitField("Guardar reporte")

class DocumentoEmitidoForm(FlaskForm):
    no_sp = StringField("No. de SP relacionado (opcional)", validators=[Optional(), Length(max=50)])
    numero_documento = StringField("No. de documento", validators=[DataRequired(), Length(max=120)])
    rc = StringField("RC", validators=[Optional(), Length(max=80)])
    destino = StringField("Destino", validators=[Optional(), Length(max=180)])
    fecha = DateField("Fecha", validators=[Optional()], default=date.today, format="%Y-%m-%d")
    descripcion = TextAreaField("Descripción", validators=[Optional()])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar documento emitido")

class ActividadForm(FlaskForm):
    fecha = DateField("Fecha", validators=[Optional()], default=date.today, format="%Y-%m-%d")
    tipo_actividad = StringField("Tipo de actividad", validators=[Optional(), Length(max=100)])
    area_apoyo = StringField("Coordinación / área apoyada", validators=[Optional(), Length(max=180)])
    descripcion = TextAreaField("Actividad realizada", validators=[DataRequired()])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar actividad")

class RemisionForm(FlaskForm):
    fecha = DateField("Fecha", validators=[Optional()], default=date.today, format="%Y-%m-%d")
    destino = StringField("Destino", validators=[DataRequired(), Length(max=180)], default="Archivo/Bodega MINGOB")
    numero_control = StringField("Número de control / documento", validators=[Optional(), Length(max=120)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Crear remisión")

class RemisionExpedienteForm(FlaskForm):
    no_sp = StringField("No. de SP", validators=[DataRequired(), Length(max=50)])
    folios = StringField("Folios", validators=[Optional(), Length(max=80)])
    anexos = StringField("Anexos", validators=[Optional(), Length(max=80)])
    estado_foliacion = StringField("Foliación", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Agregar expediente")

class ImportarCoordinacionForm(FlaskForm):
    archivo = FileField("Archivo Excel", validators=[FileRequired(), FileAllowed(["xlsx"], "Debe seleccionar un archivo .xlsx")])
    submit = SubmitField("Previsualizar archivo")

class ConfirmarImportacionForm(FlaskForm):
    token = HiddenField("Token", validators=[DataRequired()])
    submit = SubmitField("Confirmar importación")
