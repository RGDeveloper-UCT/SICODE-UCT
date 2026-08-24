from datetime import date, datetime

from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    DateTimeLocalField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import DataRequired, Length, Optional


class ListaCasillas(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


TIPOS_SERVICIO = [
    ("GESTION_USUARIO", "Creación / modificación / baja de usuario"),
    ("HARDWARE", "Mantenimiento de hardware"),
    ("SOFTWARE", "Mantenimiento de software"),
    ("INSTALACION", "Instalación de equipo"),
    ("TRASLADO", "Traslado de equipo"),
    ("REVISION", "Revisión y diagnóstico de equipo"),
    ("OTRO_TI", "Otro servicio TI"),
]

GESTION_USUARIO = [
    ("CUENTA_RED", "Cuenta de red / dominio"),
    ("CORREO", "Correo institucional"),
    ("CONTRASENA", "Cambio o restablecimiento de contraseña"),
    ("PERMISOS", "Asignación de permisos / accesos"),
    ("PERFIL", "Configuración de perfil"),
    ("BAJA_CUENTA", "Baja o deshabilitación de cuenta"),
]

HARDWARE = [
    ("LIMPIEZA", "Limpieza externa e interna"),
    ("DISCO", "Disco y almacenamiento"),
    ("RAM", "Memoria RAM"),
    ("TEMPERATURA", "Temperatura y rendimiento"),
    ("PUERTOS", "Puertos, cables y periféricos"),
    ("PANTALLA", "Pantalla, teclado y mouse"),
    ("IMPRESORA", "Impresora / escáner"),
    ("CAMARAS", "Revisión de cámaras"),
    ("TELEFONO", "Revisión de aparato telefónico"),
]

SOFTWARE = [
    ("SISTEMA_OPERATIVO", "Actualización del sistema operativo"),
    ("SOFTWARE_AUTORIZADO", "Instalación / actualización de software autorizado"),
    ("CONTROLADORES", "Revisión de controladores"),
    ("ANTIVIRUS", "Análisis antivirus / malware"),
    ("RENDIMIENTO", "Optimización de rendimiento"),
    ("ESPACIO_DISCO", "Revisión de espacio en disco"),
    ("IMPRESORA_ESCANER", "Configuración de impresora / escáner"),
    ("LINEA_TELEFONICA", "Revisión y verificación de línea telefónica"),
    ("BACKUP", "Backup de archivos de información"),
]

INSTALACION = [
    ("EQUIPO_NUEVO", "Equipo nuevo / reinstalación"),
    ("ENERGIA_DATOS", "Conexión de energía y datos"),
    ("RED", "Configuración de red"),
    ("PERIFERICOS", "Instalación de periféricos"),
    ("PRUEBAS", "Pruebas de funcionamiento"),
    ("OTRO", "Otro"),
]

TRASLADO = [
    ("CAMBIO_OFICINA", "Cambio de oficina / área"),
    ("DESCONEXION", "Desconexión segura"),
    ("TRASLADO_FISICO", "Traslado físico"),
    ("RECONEXION", "Reconexión de red y energía"),
    ("PRUEBA_POSTERIOR", "Prueba posterior al traslado"),
    ("OTRO", "Otro"),
]

REVISION = [
    ("NO_ENCIENDE", "No enciende"),
    ("BAJO_RENDIMIENTO", "Bajo rendimiento"),
    ("RED_INTERNET", "Falla de red / Internet"),
    ("IMPRESION_ESCANEO", "Falla de impresión / escaneo"),
    ("SISTEMA_PERIFERICO", "Falla de sistema o periférico"),
    ("OTRO", "Otro"),
]

TIPOS_EQUIPO = [
    ("", "No aplica / sin identificar"),
    ("PC", "PC"),
    ("LAPTOP", "Laptop"),
    ("IMPRESORA", "Impresora"),
    ("ESCANER", "Escáner"),
    ("OTRO", "Otro"),
]

ESTADOS = [
    ("PENDIENTE", "Pendiente"),
    ("RESUELTO", "Resuelto"),
    ("PARCIAL", "Parcial"),
    ("ESCALADO", "Escalado"),
]

SEGUIMIENTO = [("NO", "No"), ("SI", "Sí")]


class SoporteTecnicoForm(FlaskForm):
    fecha_hora_solicitud = DateTimeLocalField(
        "Fecha y hora",
        validators=[DataRequired()],
        format="%Y-%m-%dT%H:%M",
        default=lambda: datetime.now().replace(second=0, microsecond=0),
    )
    usuario_solicitante = StringField(
        "Nombre del usuario",
        validators=[DataRequired(), Length(max=180)],
    )
    puesto_cargo = StringField("Puesto / cargo", validators=[Optional(), Length(max=160)])
    coordinacion_area = StringField(
        "Coordinación / área",
        validators=[DataRequired(), Length(max=180)],
    )
    tecnico_asignado = StringField(
        "Técnico asignado",
        validators=[DataRequired(), Length(max=180)],
    )

    tipos_servicio = ListaCasillas(
        "Tipo de servicio solicitado",
        choices=TIPOS_SERVICIO,
        validators=[DataRequired(message="Seleccione al menos un tipo de servicio.")],
    )
    gestion_usuario_detalles = ListaCasillas("Gestión de usuario", choices=GESTION_USUARIO)
    hardware_detalles = ListaCasillas("Mantenimiento de hardware", choices=HARDWARE)
    software_detalles = ListaCasillas("Mantenimiento de software", choices=SOFTWARE)
    instalacion_detalles = ListaCasillas("Instalación", choices=INSTALACION)
    traslado_detalles = ListaCasillas("Traslado", choices=TRASLADO)
    revision_detalles = ListaCasillas("Revisión", choices=REVISION)
    otro_servicio_ti = StringField("Otro servicio TI", validators=[Optional(), Length(max=220)])
    otro_instalacion = StringField("Otro detalle de instalación", validators=[Optional(), Length(max=220)])
    otro_traslado = StringField("Otro detalle de traslado", validators=[Optional(), Length(max=220)])
    otro_revision = StringField("Otro detalle de revisión", validators=[Optional(), Length(max=220)])

    tipo_equipo = SelectField("Tipo de equipo", choices=TIPOS_EQUIPO, validators=[Optional()])
    tipo_equipo_otro = StringField("Otro tipo de equipo", validators=[Optional(), Length(max=80)])
    marca_modelo = StringField("Marca / modelo", validators=[Optional(), Length(max=180)])
    numero_serie = StringField("No. de serie", validators=[Optional(), Length(max=120)])
    inventario = StringField("SICOIN", validators=[Optional(), Length(max=120)])
    ip_nombre_equipo = StringField("IP / nombre de equipo", validators=[Optional(), Length(max=180)])

    descripcion_solicitud = TextAreaField(
        "Descripción de la solicitud / falla reportada",
        validators=[DataRequired()],
    )
    diagnostico_trabajo = TextAreaField("Diagnóstico y trabajo realizado", validators=[Optional()])

    estado_final = SelectField("Estado final", choices=ESTADOS, validators=[DataRequired()], default="PENDIENTE")
    seguimiento = SelectField("Seguimiento", choices=SEGUIMIENTO, validators=[DataRequired()], default="NO")
    fecha_hora_cierre = DateTimeLocalField(
        "Fecha / hora cierre",
        validators=[Optional()],
        format="%Y-%m-%dT%H:%M",
    )
    tiempo_empleado = StringField("Tiempo de resolución", validators=[Optional(), Length(max=80)])
    observaciones_cierre = TextAreaField("Observaciones", validators=[Optional()])

    nombre_firma_usuario = StringField("Nombre del usuario / solicitante", validators=[Optional(), Length(max=180)])
    fecha_firma_usuario = DateField("Fecha usuario", validators=[Optional()], format="%Y-%m-%d")
    nombre_firma_tecnico = StringField("Nombre del técnico", validators=[Optional(), Length(max=180)])
    fecha_firma_tecnico = DateField(
        "Fecha técnico",
        validators=[Optional()],
        default=date.today,
        format="%Y-%m-%d",
    )

    submit = SubmitField("Guardar boleta")
