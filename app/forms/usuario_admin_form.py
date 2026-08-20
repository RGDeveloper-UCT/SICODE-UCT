from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, EqualTo


ROLES_USUARIO = [
    ("usuario_autorizado", "Usuario autorizado"),
    ("visor", "Visor · solo consulta"),
    ("administrador", "Administrador"),
]


class UsuarioCrearForm(FlaskForm):
    nombre = StringField(
        "Nombre completo",
        validators=[
            DataRequired(message="Debe ingresar el nombre completo."),
            Length(max=120),
        ],
    )

    usuario = StringField(
        "Usuario",
        validators=[
            DataRequired(message="Debe ingresar el nombre de usuario."),
            Length(max=80),
        ],
    )

    correo = StringField(
        "Correo institucional",
        validators=[
            Optional(),
            Length(max=120),
        ],
    )

    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired()],
    )

    password = PasswordField(
        "Contraseña temporal",
        validators=[
            DataRequired(message="Debe ingresar una contraseña temporal."),
            Length(min=8, message="La contraseña debe tener al menos 8 caracteres."),
        ],
    )

    submit = SubmitField("Crear usuario")


class UsuarioEditarForm(FlaskForm):
    nombre = StringField(
        "Nombre completo",
        validators=[
            DataRequired(message="Debe ingresar el nombre completo."),
            Length(max=120),
        ],
    )

    usuario = StringField(
        "Usuario",
        validators=[
            DataRequired(message="Debe ingresar el nombre de usuario."),
            Length(max=80),
        ],
    )

    correo = StringField(
        "Correo institucional",
        validators=[
            Optional(),
            Length(max=120),
        ],
    )

    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired()],
    )

    submit = SubmitField("Guardar cambios")


class CambiarPasswordUsuarioForm(FlaskForm):
    password = PasswordField(
        "Nueva contraseña temporal",
        validators=[
            DataRequired(message="Debe ingresar la nueva contraseña."),
            Length(min=8, message="La contraseña debe tener al menos 8 caracteres."),
        ],
    )

    confirmar_password = PasswordField(
        "Confirmar contraseña",
        validators=[
            DataRequired(message="Debe confirmar la contraseña."),
            EqualTo("password", message="Las contraseñas no coinciden."),
        ],
    )

    submit = SubmitField("Actualizar contraseña")
