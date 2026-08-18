from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import HiddenField, SubmitField
from wtforms.validators import DataRequired


class ImportarPortadoresForm(FlaskForm):
    archivo = FileField(
        "Manta de Sujetos Portadores (.xls)",
        validators=[
            FileRequired(message="Debe seleccionar el archivo de Sujetos Portadores."),
            FileAllowed(["xls"], "El archivo debe estar en formato .xls."),
        ],
    )
    submit = SubmitField("Previsualizar")


class ConfirmarImportacionPortadoresForm(FlaskForm):
    token = HiddenField("Token", validators=[DataRequired()])
    submit = SubmitField("Confirmar sincronización")
