from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional


class VerificacionExpedienteForm(FlaskForm):
    tipo = SelectField(
        "Tipo de verificación",
        choices=[
            ("INTEGRAL", "Integral"),
            ("FISICA", "Física"),
            ("DOCUMENTAL", "Documental / foliación"),
        ],
        validators=[DataRequired()],
        default="INTEGRAL",
    )
    resultado = SelectField(
        "Resultado",
        choices=[
            ("Verificado", "Verificado"),
            ("Con observaciones", "Con observaciones"),
            ("Incompleto", "Incompleto"),
            ("No localizado", "No localizado"),
        ],
        validators=[DataRequired()],
    )
    folios_verificados = IntegerField(
        "Folios verificados (opcional)",
        validators=[Optional(), NumberRange(min=0)],
    )
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Registrar verificación")
