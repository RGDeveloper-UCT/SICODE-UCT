from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo

class CambiarPasswordPropiaForm(FlaskForm):
    password_actual = PasswordField(
        "Contraseña actual",
        validators=[
            DataRequired(message="Debe ingresar su contraseña actual."),
        ],
    )

    nueva_password = PasswordField(
        "Nueva contraseña",
        validators=[
            DataRequired(message="Debe ingresar la nueva contraseña."),
            Length(min=8, message="La contraseña debe tener al menos 8 caracteres."),
        ],
    )

    confirmar_password = PasswordField(
        "Confirmar nueva contraseña",
        validators=[
            DataRequired(message="Debe confirmar la nueva contraseña."),
            EqualTo("nueva_password", message="Las contraseñas no coinciden."),
        ],
    )

    submit = SubmitField("Actualizar contraseña")
