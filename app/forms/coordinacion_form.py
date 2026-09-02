from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import BooleanField, DateField, DecimalField, HiddenField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


REFERENCIAS_CHOICES = [("RC", "RC"), ("RE", "RE")]


def _normalizar_referencia(tipo, numero):
    """Guarda la referencia completa en la columna histórica `rc` sin cambiar el esquema de BD."""
    numero = (numero or "").strip()
    if not numero:
        return None

    # Evita valores duplicados como "RC RC 2026..." cuando alguien pega el prefijo.
    partes = numero.split(maxsplit=1)
    if partes and partes[0].upper() in {"RC", "RE"}:
        numero = partes[1].strip() if len(partes) > 1 else ""
    if not numero:
        return None

    tipo = (tipo or "RC").strip().upper()
    if tipo not in {"RC", "RE"}:
        tipo = "RC"
    return f"{tipo} {numero}"


class ReferenciaRCREMixin:
    """Añade selector RC/RE y entrega a las rutas el valor ya normalizado."""
    tipo_referencia = SelectField("Tipo de referencia", choices=REFERENCIAS_CHOICES, default="RC", validators=[DataRequired()])

    def validate(self, extra_validators=None):
        valido = super().validate(extra_validators=extra_validators)
        if valido and hasattr(self, "rc"):
            self.rc.data = _normalizar_referencia(self.tipo_referencia.data, self.rc.data)
        return valido


class RegistroBaseForm(ReferenciaRCREMixin, FlaskForm):
    no_sp = StringField("No. de SP", validators=[DataRequired(), Length(max=50)])
    rc = StringField("Número RC / RE", validators=[Optional(), Length(max=80)])
    providencia = StringField("Providencia", validators=[Optional(), Length(max=120)])
    fecha_recepcion = DateField("Fecha recibido", validators=[Optional()], default=date.today, format="%Y-%m-%d")
    persona_entrega = StringField("Quién entrega / remite", validators=[Optional(), Length(max=180)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])


class ExpedienteCompletoForm(RegistroBaseForm):
    rc = StringField("Número RC / RE", validators=[DataRequired(), Length(max=80)])
    fecha_recepcion = DateField("Fecha de recepción", validators=[DataRequired()], default=date.today, format="%Y-%m-%d")
    persona_entrega = StringField("Quién entrega / remite", validators=[DataRequired(), Length(max=180)])
    folios = StringField("Folios del expediente", validators=[DataRequired(), Length(max=80)])
    submit = SubmitField("Registrar expediente completo")


class PagoForm(RegistroBaseForm):
    folios = StringField("Folios recibidos", validators=[Optional(), Length(max=80)])
    periodo_desde = DateField("Pago desde", validators=[Optional()], format="%Y-%m-%d")
    periodo_hasta = DateField("Pago hasta", validators=[Optional()], format="%Y-%m-%d")
    periodo_texto = StringField("Período si no se conoce fecha exacta", validators=[Optional(), Length(max=120)])
    boleta = StringField("Boleta", validators=[Optional(), Length(max=120)])
    total = DecimalField("Total", validators=[Optional()], places=2)
    submit = SubmitField("Guardar pago")


class MovimientoForm(RegistroBaseForm):
    descripcion = StringField("Descripción", validators=[Optional(), Length(max=180)], default="EXPEDIENTE")
    folios = StringField("Folios recibidos", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Guardar movimiento")


class AnexoForm(RegistroBaseForm):
    tipo_anexo = StringField("Tipo de anexo", validators=[Optional(), Length(max=120)])
    folios = StringField("Folios recibidos", validators=[Optional(), Length(max=80)])
    escaneado = BooleanField("Escaneado")
    fecha_escaneado = DateField("Fecha escaneado", validators=[Optional()], format="%Y-%m-%d")
    numero_anexo = StringField("Anexo No.", validators=[DataRequired(), Length(max=50)])
    anexo_vencido = BooleanField("ANEXO VENCIDO / HISTÓRICO")
    confirmacion_file_server = BooleanField(
        "Confirmé en File Server el número de anexo",
        validators=[DataRequired(message="Debe confirmar el número de anexo contra File Server.")],
    )
    submit = SubmitField("Guardar anexo")


class MonitoreoForm(RegistroBaseForm):
    folios = StringField("Folios recibidos", validators=[Optional(), Length(max=80)])
    numero_anexo_monitoreo = IntegerField(
        "Anexo que corresponde",
        validators=[DataRequired(), NumberRange(min=1, max=200)],
    )
    anexo_vencido = BooleanField("ANEXO VENCIDO / HISTÓRICO")
    confirmacion_file_server = BooleanField(
        "Confirmé en File Server el número de anexo",
        validators=[DataRequired(message="Debe confirmar el número de anexo contra File Server.")],
    )
    tipo_documento = StringField("Tipo de documento", validators=[Optional(), Length(max=80)], default="PROVIDENCIA")
    numero_reporte = StringField("Reporte No.", validators=[Optional(), Length(max=120)])
    tipo_evento = StringField("Tipo de reporte / evento", validators=[Optional(), Length(max=180)])
    submit = SubmitField("Guardar reporte")


class DocumentoEmitidoForm(ReferenciaRCREMixin, FlaskForm):
    no_sp = StringField("No. de SP relacionado (opcional)", validators=[Optional(), Length(max=50)])
    numero_documento = StringField("No. de documento", validators=[DataRequired(), Length(max=120)])
    rc = StringField("Número RC / RE", validators=[Optional(), Length(max=80)])
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
