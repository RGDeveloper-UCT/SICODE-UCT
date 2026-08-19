from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class PrestamoForm(FlaskForm):
    solicitante = StringField(
        "Solicitante",
        validators=[
            DataRequired(message="Debe ingresar el nombre de la persona solicitante."),
            Length(max=150),
        ],
    )
    persona_entrega = StringField(
        "Persona que entrega",
        validators=[
            DataRequired(message="Debe ingresar la persona que entrega el expediente."),
            Length(max=150),
        ],
    )
    persona_recibe = StringField(
        "Persona que recibe",
        validators=[
            DataRequired(message="Debe ingresar la persona que recibe el expediente."),
            Length(max=150),
        ],
    )
    fecha_estimada_devolucion = DateField(
        "Fecha estimada de devolución",
        format="%Y-%m-%d",
        validators=[Optional()],
    )
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Registrar préstamo")


class DevolucionForm(FlaskForm):
    persona_devuelve = StringField(
        "Persona que devuelve",
        validators=[
            DataRequired(message="Debe ingresar la persona que devuelve el expediente."),
            Length(max=150),
        ],
    )
    persona_recibe_devolucion = StringField(
        "Persona que recibe la devolución",
        validators=[
            DataRequired(message="Debe ingresar la persona que recibe la devolución."),
            Length(max=150),
        ],
    )
    observaciones_devolucion = TextAreaField("Observaciones de devolución", validators=[Optional()])
    submit = SubmitField("Registrar devolución")


class TrasladoVirtualForm(FlaskForm):
    destinatario = StringField(
        "Persona destinataria",
        validators=[
            DataRequired(message="Debe indicar a quién se trasladó virtualmente el expediente."),
            Length(max=180),
        ],
    )
    dependencia_destino = StringField(
        "Institución, dependencia o área destinataria",
        validators=[Optional(), Length(max=220)],
    )
    plataforma = SelectField(
        "Plataforma utilizada",
        choices=[
            ("Google Drive", "Google Drive"),
            ("Proton Drive", "Proton Drive"),
            ("OneDrive", "OneDrive"),
            ("Dropbox", "Dropbox"),
            ("Correo institucional", "Correo institucional"),
            ("Otra", "Otra plataforma"),
        ],
        validators=[DataRequired()],
    )
    enlace_corto = StringField(
        "Enlace acortado o enlace de acceso",
        validators=[
            DataRequired(message="Debe registrar el enlace utilizado para el traslado virtual."),
            Length(max=500),
        ],
    )
    asunto = StringField(
        "Motivo o asunto del traslado",
        validators=[
            DataRequired(message="Debe indicar el motivo del traslado virtual."),
            Length(max=250),
        ],
    )
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Generar constancia PDF")
