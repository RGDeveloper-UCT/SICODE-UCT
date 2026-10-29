"""Formularios del módulo NP; reutiliza las validaciones de SICODE."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

from app.models.no_portador import normalizar_np


def _filtro_np(valor):
    return normalizar_np(valor)


def _numero_np(form, field):
    if not field.data:
        raise ValidationError("Indique un No. NP válido, por ejemplo NP-0001.")


class NoPortadorForm(FlaskForm):
    numero_np = StringField("No. de NP", filters=[_filtro_np], validators=[DataRequired(), Length(max=50), _numero_np])
    codigo_interno = StringField("Código interno del NP", validators=[DataRequired(), Length(max=50)])
    nombre_referencia = StringField("Nombre de referencia", validators=[Optional(), Length(max=150)])
    motivo_no_instalacion = TextAreaField("Motivo por el que no se instaló", validators=[DataRequired(), Length(max=2500)])
    fecha_no_instalacion = DateField("Fecha de no instalación", validators=[Optional()])
    estado_administrativo = SelectField("Estado administrativo", choices=[
        ("Activo", "Activo"), ("En revisión", "En revisión"), ("Cerrado", "Cerrado"),
    ])
    expediente_fisico_registrado = BooleanField("Existe expediente físico en UCT")
    nombres = StringField("Nombres", validators=[Optional(), Length(max=150)])
    apellidos = StringField("Apellidos", validators=[Optional(), Length(max=150)])
    genero = StringField("Género", validators=[Optional(), Length(max=30)])
    fecha_nacimiento = DateField("Fecha de nacimiento", validators=[Optional()])
    expediente_oj = StringField("Expediente OJ", validators=[Optional(), Length(max=120)])
    delito = TextAreaField("Delito", validators=[Optional()])
    juez = StringField("Juez", validators=[Optional(), Length(max=250)])
    juzgado_tribunal = StringField("Juzgado/Tribunal", validators=[Optional(), Length(max=500)])
    abogado = StringField("Abogado", validators=[Optional(), Length(max=250)])
    residencia = TextAreaField("Residencia", validators=[Optional()])
    municipio = StringField("Municipio", validators=[Optional(), Length(max=150)])
    departamento = StringField("Departamento", validators=[Optional(), Length(max=150)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=80)])
    municipio_residencia = StringField("Municipio de residencia", validators=[Optional(), Length(max=150)])
    departamento_residencia = StringField("Departamento de residencia", validators=[Optional(), Length(max=150)])
    zona_inclusion = TextAreaField("Zona de inclusión", validators=[Optional()])
    zona_exclusion = TextAreaField("Zona de exclusión", validators=[Optional()])
    zona_prevencion = TextAreaField("Zona de prevención", validators=[Optional()])
    financiamiento = StringField("Financiamiento", validators=[Optional(), Length(max=150)])
    lugar_instalacion = TextAreaField("Lugar previsto de instalación", validators=[Optional()])
    estado_monitoreo = StringField("Estado de monitoreo", validators=[Optional(), Length(max=120)])
    archivador = StringField("Archivador", validators=[Optional(), Length(max=80)])
    sicoin = StringField("SICOIN", validators=[Optional(), Length(max=80)])
    estante = StringField("Estante", validators=[Optional(), Length(max=80)])
    caja = StringField("Caja", validators=[Optional(), Length(max=80)])
    modulo = StringField("Módulo", validators=[Optional(), Length(max=80)])
    posicion = StringField("Posición", validators=[Optional(), Length(max=80)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar NP")


class DocumentoNPForm(FlaskForm):
    nombre_documento = StringField("Nombre del documento", validators=[DataRequired(), Length(max=180)])
    tipo_documento = StringField("Tipo documental", validators=[DataRequired(), Length(max=80)], default="Documento")
    folio_inicio = IntegerField("Folio inicial", validators=[DataRequired(), NumberRange(min=1)])
    folio_fin = IntegerField("Folio final", validators=[DataRequired(), NumberRange(min=1)])
    es_anexo = BooleanField("Es anexo")
    indice_numero_anexo = IntegerField("Número de anexo", validators=[Optional(), NumberRange(min=1)])
    estado_revision = SelectField("Revisión", choices=[
        ("Pendiente de revisión", "Pendiente de revisión"),
        ("Verificado", "Verificado"), ("Con observaciones", "Con observaciones"),
    ])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Guardar documento")


class AnexoNPForm(FlaskForm):
    numero_anexo = StringField("No. anexo", validators=[Optional(), Length(max=50)])
    titulo = StringField("Título del anexo", validators=[DataRequired(), Length(max=180)])
    tipo_anexo = StringField("Tipo de anexo", validators=[Optional(), Length(max=120)])
    fecha_recepcion = DateField("Fecha de recepción", validators=[Optional()])
    persona_entrega = StringField("Persona que entrega", validators=[Optional(), Length(max=180)])
    rc = StringField("RC", validators=[Optional(), Length(max=80)])
    providencia = StringField("Providencia", validators=[Optional(), Length(max=120)])
    folios = StringField("Folios", validators=[Optional(), Length(max=80)])
    escaneado = BooleanField("Escaneado (solo dato administrativo)")
    fecha_escaneado = DateField("Fecha de escaneo", validators=[Optional()])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Registrar anexo")


class RectificacionNPForm(FlaskForm):
    folios_rectificados = IntegerField("Total de folios físicos", validators=[DataRequired(), NumberRange(min=1)])
    anexos_rectificados = IntegerField("Total de anexos físicos", validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Confirmar rectificación")


class VerificacionNPForm(FlaskForm):
    tipo = SelectField("Tipo de verificación", choices=[
        ("FISICA", "Física"), ("DOCUMENTAL", "Documental"), ("INTEGRAL", "Integral"),
    ])
    resultado = SelectField("Resultado", choices=[
        ("Verificado", "Verificado"), ("Con observaciones", "Con observaciones"),
        ("Incompleto", "Incompleto"), ("No localizado", "No localizado"),
    ])
    folios_verificados = IntegerField("Folios verificados", validators=[Optional(), NumberRange(min=0)])
    observaciones = TextAreaField("Observaciones", validators=[Optional()])
    submit = SubmitField("Registrar verificación")


class AlertaNPForm(FlaskForm):
    tipo_alerta = StringField("Tipo", validators=[DataRequired(), Length(max=100)])
    titulo = StringField("Título", validators=[DataRequired(), Length(max=180)])
    descripcion = TextAreaField("Descripción", validators=[Optional()])
    gravedad = SelectField("Gravedad", choices=[("Baja","Baja"),("Media","Media"),("Alta","Alta")])
    submit = SubmitField("Registrar alerta")
