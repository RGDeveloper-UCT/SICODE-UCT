from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

class LoginForm(FlaskForm):
    usuario = StringField(
        "Usuario",
        validators=[
            DataRequired(message="Debe ingresar su usuario."),
            Length(min=3, max=80, message="El usuario debe tener entre 3 y 80 caracteres.")
        ],
    )

    password = PasswordField(
        "Contraseña",
        validators=[
            DataRequired(message="Debe ingresar su contraseña.")
        ],
    )

    submit = SubmitField("Ingresar")
