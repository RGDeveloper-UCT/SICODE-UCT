from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


REFERENCIAS_PAGO = [("RC", "RC"), ("RE", "RE")]


class PagoSPForm(FlaskForm):
    no_sp = StringField("No. de SP", validators=[DataRequired(), Length(max=50)])
    providencia = StringField("Número de providencia", validators=[DataRequired(), Length(max=120)])
    tipo_referencia = SelectField(
        "Tipo de referencia",
        choices=REFERENCIAS_PAGO,
        validators=[DataRequired()],
        default="RC",
    )
    numero_referencia = StringField("Número RC / RE", validators=[DataRequired(), Length(max=80)])
    monto = DecimalField(
        "Monto pagado",
        validators=[DataRequired(), NumberRange(min=0.01, message="El monto debe ser mayor que cero.")],
        places=2,
    )
    boleta = StringField("Número de boleta bancaria", validators=[DataRequired(), Length(max=120)])
    banco = StringField("Banco", validators=[DataRequired(), Length(max=120)])
    periodo_desde = DateField("Período pagado desde", validators=[DataRequired()], format="%Y-%m-%d")
    periodo_hasta = DateField("Período pagado hasta", validators=[DataRequired()], format="%Y-%m-%d")
    observaciones = TextAreaField("Observaciones", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Registrar pago")

    def validate_periodo_hasta(self, field):
        if self.periodo_desde.data and field.data and field.data < self.periodo_desde.data:
            raise ValidationError("La fecha final del período no puede ser anterior a la fecha inicial.")
