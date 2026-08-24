from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


PLATAFORMAS_VIRTUALES = [
    ("", "Seleccione una plataforma"),
    ("Google Drive", "Google Drive"),
    ("Proton Drive", "Proton Drive"),
    ("OneDrive", "OneDrive"),
    ("Dropbox", "Dropbox"),
    ("Correo institucional", "Correo institucional"),
    ("Otra", "Otra plataforma"),
]


class PrestamoGrupalForm(FlaskForm):
    sp_desde = IntegerField(
        "SP inicial",
        validators=[DataRequired(message="Debe indicar el SP inicial."), NumberRange(min=1)],
    )
    sp_hasta = IntegerField(
        "SP final",
        validators=[DataRequired(message="Debe indicar el SP final."), NumberRange(min=1)],
    )
    modalidad = SelectField(
        "Modalidad del movimiento",
        choices=[
            ("FISICO", "Físico — préstamo de expedientes"),
            ("VIRTUAL", "Virtual — traslado/compartición de expedientes"),
        ],
        validators=[DataRequired()],
        default="FISICO",
    )
    solicitante = StringField(
        "Solicitante / responsable",
        validators=[DataRequired(message="Debe ingresar la persona solicitante."), Length(max=150)],
    )
    persona_entrega = StringField(
        "Persona que entrega / comparte",
        validators=[DataRequired(message="Debe ingresar la persona que entrega o comparte los expedientes."), Length(max=150)],
    )
    persona_recibe = StringField(
        "Persona que recibe / destinataria",
        validators=[DataRequired(message="Debe ingresar la persona que recibe los expedientes."), Length(max=150)],
    )
    fecha_estimada_devolucion = DateField(
        "Fecha estimada de devolución",
        format="%Y-%m-%d",
        validators=[Optional()],
    )
    plataforma = SelectField(
        "Plataforma utilizada",
        choices=PLATAFORMAS_VIRTUALES,
        validators=[Optional()],
    )
    enlace_virtual = StringField(
        "Enlace de acceso compartido",
        validators=[Optional(), Length(max=500)],
    )
    asunto_virtual = StringField(
        "Motivo o asunto del traslado virtual",
        validators=[Optional(), Length(max=250)],
    )
    observaciones = TextAreaField("Observaciones generales", validators=[Optional()])
    submit = SubmitField("Generar movimiento por rango y constancia")
