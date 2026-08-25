from flask_wtf import FlaskForm
from wtforms import HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.services.sp_service import normalizar_sp


ESTADOS_ADMINISTRATIVOS = [
    ("Activo", "Activo"),
    ("En revisión", "En revisión"),
    ("Cerrado", "Cerrado"),
]

# Se conserva el campo oculto para compatibilidad con rutas y registros
# históricos. El estado documental vigente ya no se elige manualmente: se
# deriva del árbol Expediente -> Índice -> Rectificación -> Verificación.
ESTADO_DOCUMENTAL_LEGACY_DEFAULT = "Pendiente de verificación"


class ExpedienteForm(FlaskForm):
    codigo_interno = StringField(
        "Código interno",
        validators=[DataRequired(message="Debe ingresar el código interno."), Length(max=50)],
    )
    no_sp = StringField(
        "No. de SP",
        filters=[normalizar_sp],
        validators=[DataRequired(message="Debe ingresar el No. de SP."), Length(max=50)],
    )
    nombre_referencia = StringField("Nombre de referencia", validators=[Optional(), Length(max=150)])
    estado_administrativo = SelectField("Estado administrativo", choices=ESTADOS_ADMINISTRATIVOS, default="Activo")
    estado_fisico_documental = HiddenField(default=ESTADO_DOCUMENTAL_LEGACY_DEFAULT)
    archivador = StringField("Archivador", validators=[Optional(), Length(max=80)])
    sicoin = StringField("SICOIN", validators=[Optional(), Length(max=80)])
    estante = StringField("Estante", validators=[Optional(), Length(max=80)])
    caja = StringField("Caja", validators=[Optional(), Length(max=80)])
    modulo = StringField("Módulo", validators=[Optional(), Length(max=80)])
    posicion = StringField("Posición", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar expediente")


class RegistrarExpedienteFisicoForm(FlaskForm):
    estado_administrativo = SelectField("Estado administrativo", choices=ESTADOS_ADMINISTRATIVOS, default="Activo")
    estado_fisico_documental = HiddenField(default=ESTADO_DOCUMENTAL_LEGACY_DEFAULT)
    archivador = StringField("Archivador", validators=[Optional(), Length(max=80)])
    sicoin = StringField("SICOIN", validators=[Optional(), Length(max=80)])
    estante = StringField("Estante", validators=[Optional(), Length(max=80)])
    caja = StringField("Caja", validators=[Optional(), Length(max=80)])
    modulo = StringField("Módulo", validators=[Optional(), Length(max=80)])
    posicion = StringField("Posición", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones del expediente físico", validators=[Optional()])
    submit = SubmitField("Registrar expediente físico")
