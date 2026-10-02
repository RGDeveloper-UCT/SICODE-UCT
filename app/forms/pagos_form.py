from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import DateField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


REFERENCIAS_PAGO = [("RC", "RC"), ("RE", "RE")]
COMPROBANTES_PERMITIDOS = ["jpg", "jpeg", "png", "pdf"]


class PagoSPForm(FlaskForm):
    no_sp = StringField("No. de SP", validators=[DataRequired(), Length(max=50)])
    fecha_comprobante = DateField(
        "Fecha de comprobante",
        validators=[DataRequired()],
        format="%Y-%m-%d",
    )

    expediente_oj = StringField("Número único de expediente", validators=[Optional(), Length(max=120)])
    organo_jurisdiccional = TextAreaField("Órgano jurisdiccional", validators=[Optional(), Length(max=500)])
    nombre_sujeto = StringField("Nombre del Sujeto Portador", validators=[Optional(), Length(max=180)])

    providencia = StringField("Número de providencia", validators=[DataRequired(), Length(max=120)])
    tipo_referencia = SelectField(
        "Tipo de referencia",
        choices=REFERENCIAS_PAGO,
        validators=[DataRequired()],
        default="RC",
    )
    numero_referencia = StringField("Número RC / RE", validators=[DataRequired(), Length(max=80)])

    periodo_desde = DateField("Período pagado desde", validators=[DataRequired()], format="%Y-%m-%d")
    periodo_hasta = DateField("Período pagado hasta", validators=[DataRequired()], format="%Y-%m-%d")
    dias_aplicados = IntegerField(
        "Días aplicados",
        validators=[DataRequired(), NumberRange(min=0, max=3660)],
        default=0,
    )
    meses_aplicados = IntegerField(
        "Meses aplicados",
        validators=[DataRequired(), NumberRange(min=0, max=120)],
        default=1,
    )

    # El monto se conserva por compatibilidad del formulario, pero el servidor
    # lo calcula con las tarifas impresas en la boleta para evitar diferencias.
    monto = DecimalField("Cantidad a pagar", validators=[Optional()], places=2)

    boleta = StringField("Número de boleta bancaria", validators=[DataRequired(), Length(max=120)])
    banco = StringField(
        "Banco",
        validators=[DataRequired(), Length(max=120)],
        default="Banco de los Trabajadores (BANTRAB)",
    )
    contacto = StringField("Contacto para la boleta", validators=[Optional(), Length(max=220)])
    comprobante = FileField(
        "Comprobante bancario",
        validators=[
            FileRequired(message="Adjunte el comprobante bancario que quedará integrado en la boleta."),
            FileAllowed(
                COMPROBANTES_PERMITIDOS,
                message="El comprobante debe ser JPG, JPEG, PNG o PDF.",
            ),
        ],
    )

    observaciones = TextAreaField("Observaciones", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Registrar pago y generar boleta PDF")

    def validate_periodo_hasta(self, field):
        if self.periodo_desde.data and field.data and field.data < self.periodo_desde.data:
            raise ValidationError("La fecha final del período no puede ser anterior a la fecha inicial.")

    def validate_meses_aplicados(self, field):
        dias = self.dias_aplicados.data or 0
        meses = field.data or 0
        if dias <= 0 and meses <= 0:
            raise ValidationError("Debe registrar al menos un día o un mes aplicado.")
