from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


ESTADOS_ADMINISTRATIVOS = [
    ("Activo", "Activo"),
    ("En revisión", "En revisión"),
    ("Cerrado", "Cerrado"),
]

ESTADOS_FISICOS = [
    ("Pendiente de verificación", "Pendiente de verificación"),
    ("Verificado", "Verificado"),
    ("Con observaciones", "Con observaciones"),
    ("Incompleto", "Incompleto"),
    ("No localizado", "No localizado"),
]


class ExpedienteForm(FlaskForm):
    codigo_interno = StringField(
        "Código interno",
        validators=[DataRequired(message="Debe ingresar el código interno."), Length(max=50)],
    )
    no_sp = StringField(
        "No. de SP",
        validators=[DataRequired(message="Debe ingresar el No. de SP."), Length(max=50)],
    )
    nombre_referencia = StringField("Nombre de referencia", validators=[Optional(), Length(max=150)])
    estado_administrativo = SelectField("Estado administrativo", choices=ESTADOS_ADMINISTRATIVOS, default="Activo")
    estado_fisico_documental = SelectField(
        "Estado físico/documental",
        choices=ESTADOS_FISICOS,
        default="Pendiente de verificación",
    )
    archivador = StringField("Archivador", validators=[Optional(), Length(max=80)])
    sicoin = StringField("SICOIN", validators=[Optional(), Length(max=80)])
    estante = StringField("Estante", validators=[Optional(), Length(max=80)])
    caja = StringField("Caja", validators=[Optional(), Length(max=80)])
    modulo = StringField("Módulo", validators=[Optional(), Length(max=80)])
    posicion = StringField("Posición", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar expediente")


class RegistrarExpedienteFisicoForm(FlaskForm):
    """Completa un SP ya conocido sin duplicar su registro maestro."""

    estado_administrativo = SelectField("Estado administrativo", choices=ESTADOS_ADMINISTRATIVOS, default="Activo")
    estado_fisico_documental = SelectField(
        "Estado físico/documental",
        choices=ESTADOS_FISICOS,
        default="Pendiente de verificación",
    )
    archivador = StringField("Archivador", validators=[Optional(), Length(max=80)])
    sicoin = StringField("SICOIN", validators=[Optional(), Length(max=80)])
    estante = StringField("Estante", validators=[Optional(), Length(max=80)])
    caja = StringField("Caja", validators=[Optional(), Length(max=80)])
    modulo = StringField("Módulo", validators=[Optional(), Length(max=80)])
    posicion = StringField("Posición", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones del expediente físico", validators=[Optional()])
    submit = SubmitField("Registrar expediente físico")
