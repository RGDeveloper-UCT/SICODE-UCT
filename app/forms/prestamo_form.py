from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

class PrestamoForm(FlaskForm):
    solicitante = StringField(
        "Solicitante",
        validators=[
            DataRequired(message="Debe ingresar el nombre de la persona solicitante."),
            Length(max=150)
        ],
    )

    persona_entrega = StringField(
        "Persona que entrega",
        validators=[
            DataRequired(message="Debe ingresar la persona que entrega el expediente."),
            Length(max=150)
        ],
    )

    persona_recibe = StringField(
        "Persona que recibe",
        validators=[
            DataRequired(message="Debe ingresar la persona que recibe el expediente."),
            Length(max=150)
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
            Length(max=150)
        ],
    )

    persona_recibe_devolucion = StringField(
        "Persona que recibe la devolución",
        validators=[
            DataRequired(message="Debe ingresar la persona que recibe la devolución."),
            Length(max=150)
        ],
    )

    observaciones_devolucion = TextAreaField("Observaciones de devolución", validators=[Optional()])

    submit = SubmitField("Registrar devolución")
