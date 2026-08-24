from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class PrestamoGrupalForm(FlaskForm):
    sp_desde = IntegerField(
        "SP inicial",
        validators=[DataRequired(message="Debe indicar el SP inicial."), NumberRange(min=1)],
    )
    sp_hasta = IntegerField(
        "SP final",
        validators=[DataRequired(message="Debe indicar el SP final."), NumberRange(min=1)],
    )
    solicitante = StringField(
        "Solicitante",
        validators=[DataRequired(message="Debe ingresar la persona solicitante."), Length(max=150)],
    )
    persona_entrega = StringField(
        "Persona que entrega",
        validators=[DataRequired(message="Debe ingresar la persona que entrega los expedientes."), Length(max=150)],
    )
    persona_recibe = StringField(
        "Persona que recibe",
        validators=[DataRequired(message="Debe ingresar la persona que recibe los expedientes."), Length(max=150)],
    )
    fecha_estimada_devolucion = DateField(
        "Fecha estimada de devolución",
        format="%Y-%m-%d",
        validators=[Optional()],
    )
    observaciones = TextAreaField("Observaciones generales", validators=[Optional()])
    submit = SubmitField("Generar préstamo grupal y constancia")
