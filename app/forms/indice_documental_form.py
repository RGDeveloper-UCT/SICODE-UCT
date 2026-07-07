from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, NumberRange

class IndiceDocumentalForm(FlaskForm):
    nombre_documento = StringField(
        "Nombre del documento",
        validators=[
            DataRequired(message="Debe ingresar el nombre del documento."),
            Length(max=180)
        ],
    )

    tipo_documento = SelectField(
        "Tipo de documento",
        choices=[
            ("Documento", "Documento"),
            ("Anexo", "Anexo"),
            ("Oficio", "Oficio"),
            ("Resolución", "Resolución"),
            ("Acta", "Acta"),
            ("Informe", "Informe"),
            ("Otro", "Otro"),
        ],
        default="Documento",
    )

    folio_inicio = IntegerField(
        "Folio inicial",
        validators=[
            DataRequired(message="Debe ingresar el folio inicial."),
            NumberRange(min=1, message="El folio inicial debe ser mayor o igual a 1.")
        ],
    )

    folio_fin = IntegerField(
        "Folio final",
        validators=[
            DataRequired(message="Debe ingresar el folio final."),
            NumberRange(min=1, message="El folio final debe ser mayor o igual a 1.")
        ],
    )

    estado_revision = SelectField(
        "Estado de revisión",
        choices=[
            ("Pendiente de revisión", "Pendiente de revisión"),
            ("Verificado", "Verificado"),
            ("Con observaciones", "Con observaciones"),
            ("Mal foliado", "Mal foliado"),
            ("Anexo pendiente", "Anexo pendiente"),
        ],
        default="Pendiente de revisión",
    )

    observaciones = TextAreaField("Observaciones", validators=[Optional()])

    submit = SubmitField("Agregar al índice")
