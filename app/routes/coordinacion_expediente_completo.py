from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length

from app import db
from app.models.coordinacion import RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.routes.coordinacion import TIPOS_REGISTRO, coordinacion_bp
from app.services.bitacora_service import registrar_bitacora


GUATEMALA_TZ = ZoneInfo("America/Guatemala")

DOCUMENTOS_BASE = [
    (1, "Solicitud de Informe de Factibilidad", "SOLICITUD", 1, 4),
    (2, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 5, 7),
    (3, "Informe de Factibilidad", "INFORME", 8, 12),
    (4, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 13, 14),
    (5, "Orden de Instalación y pago", "ORDEN", 15, 21),
    (6, "Boleta de Instalación", "BOLETA", 22, 22),
    (7, "Actas de Instalación", "ACTA", 23, 26),
    (8, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 27, 34),
]
DOCUMENTOS_BASE_POR_NUMERO = {item[0]: item for item in DOCUMENTOS_BASE}
MAX_DOCUMENTOS_EXPEDIENTE_COMPLETO = 200

FORMAS_REGISTRO = {
    "BASE_EDITABLE": "Instalación / traslado — índice base editable",
    "PERSONALIZADO": "Personalizado — editar documentos y folios antes de guardar",
}

TIPOS_REGISTRO["expediente-completo"] = {
    "codigo": "EXPEDIENTE_COMPLETO",
    "titulo": "Expediente completo",
    "descripcion": "Recepción de expediente completo y creación individual de cada documento del índice en el SP seleccionado.",
}


class RecepcionExpedienteCompletoForm(FlaskForm):
    expediente_id = SelectField("SP al que se adjuntará", coerce=int, validators=[DataRequired()])
    forma_registro = SelectField("Forma de registro", validators=[DataRequired()])
    tipo_referencia = SelectField(
        "Tipo de referencia",
        choices=[("RC", "RC"), ("RE", "RE")],
        validators=[DataRequired()],
    )
    numero_referencia = StringField("Número RC / RE", validators=[DataRequired(), Length(max=76)])
    persona_entrega = StringField("Quién entrega / remite", validators=[DataRequired(), Length(max=180)])
    submit = SubmitField("Registrar y adjuntar documentación")


def _cargar_opciones(form):
    expedientes = Expediente.query.filter_by(activo=True).order_by(Expediente.no_sp.asc()).all()
    form.expediente_id.choices = [
        (exp.id, f"{exp.no_sp} — {exp.nombre_referencia or exp.codigo_interno or 'Expediente'}")
        for exp in expedientes
    ]
    form.forma_registro.choices = list(FORMAS_REGISTRO.items())


def _numeros_documentos_formulario():
    """Obtiene todas las filas enviadas por el navegador, incluidas las agregadas dinámicamente."""
    numeros = set()
    for clave in request.form.keys():
        coincidencia = re.fullmatch(r"documento_(\d+)", clave)
        if coincidencia:
            numero = int(coincidencia.group(1))
            if 1 <= numero <= MAX_DOCUMENTOS_EXPEDIENTE_COMPLETO:
                numeros.add(numero)
    return sorted(numeros) if numeros else [item[0] for item in DOCUMENTOS_BASE]


def _datos_base_fila(numero):
    base = DOCUMENTOS_BASE_POR_NUMERO.get(numero)
    if base:
        return base[1], base[2], base[3], base[4]
    return "", "OTRO", "", ""


def _documentos_desde_formulario():
    """Obtiene todas las filas editables y valida nombres/rangos de folios."""
    documentos = []
    errores = []
    numeros = _numeros_documentos_formulario()

    if len(numeros) > MAX_DOCUMENTOS_EXPEDIENTE_COMPLETO:
        return [], [f"No se pueden registrar más de {MAX_DOCUMENTOS_EXPEDIENTE_COMPLETO} documentos por operación."]

    for numero in numeros:
        nombre_base, tipo_documento, inicio_base, fin_base = _datos_base_fila(numero)
        nombre = (request.form.get(f"documento_{numero}") or nombre_base).strip()
        inicio_texto = (request.form.get(f"folio_inicio_{numero}") or str(inicio_base)).strip()
        fin_texto = (request.form.get(f"folio_fin_{numero}") or str(fin_base)).strip()

        if not nombre:
            errores.append(f"Fila {numero}: el nombre del documento es obligatorio.")
            continue
        try:
            folio_inicio = int(inicio_texto)
            folio_fin = int(fin_texto)
        except (TypeError, ValueError):
            errores.append(f"Fila {numero}: los folios deben ser números enteros.")
            continue
        if folio_inicio < 1 or folio_fin < 1:
            errores.append(f"Fila {numero}: los folios deben ser mayores o iguales a 1.")
            continue
        if folio_fin < folio_inicio:
            errores.append(f"Fila {numero}: el folio final no puede ser menor que el inicial.")
            continue
        documentos.append((numero, nombre, tipo_documento, folio_inicio, folio_fin))

    ordenados = sorted(documentos, key=lambda item: (item[3], item[4]))
    for anterior, actual in zip(ordenados, ordenados[1:]):
        if actual[3] <= anterior[4]:
            errores.append(
                f"Los rangos de las filas {anterior[0]} y {actual[0]} se traslapan "
                f"({anterior[3]}-{anterior[4]} y {actual[3]}-{actual[4]})."
            )
    return documentos, errores


def _documentos_para_vista():
    """Conserva lo escrito por el usuario si el POST necesita mostrarse de nuevo."""
    if request.method != "POST":
        return DOCUMENTOS_BASE

    filas = []
    for numero in _numeros_documentos_formulario():
        nombre_base, tipo_documento, inicio_base, fin_base = _datos_base_fila(numero)
        nombre = (request.form.get(f"documento_{numero}") or nombre_base).strip()
        inicio_texto = request.form.get(f"folio_inicio_{numero}")
        fin_texto = request.form.get(f"folio_fin_{numero}")

        if inicio_texto is None:
            inicio = inicio_base
        else:
            try:
                inicio = int(inicio_texto.strip())
            except (TypeError, ValueError):
                inicio = inicio_texto

        if fin_texto is None:
            fin = fin_base
        else:
            try:
                fin = int(fin_texto.strip())
            except (TypeError, ValueError):
                fin = fin_texto

        filas.append((numero, nombre, tipo_documento, inicio, fin))
    return filas


def _buscar_conflictos(expediente_id, documentos):
    if not documentos:
        return []
    inicio = min(item[3] for item in documentos)
    fin = max(item[4] for item in documentos)
    candidatos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente_id, activo=True)
        .filter(
            DocumentoExpediente.folio_inicio <= fin,
            DocumentoExpediente.folio_fin >= inicio,
        )
        .order_by(DocumentoExpediente.folio_inicio.asc())
        .all()
    )
    return [
        existente
        for existente in candidatos
        if any(
            existente.folio_inicio <= nuevo_fin and existente.folio_fin >= nuevo_inicio
            for _numero, _nombre, _tipo, nuevo_inicio, nuevo_fin in documentos
        )
    ]


def _crear_documentos_individuales(expediente, registro, documentos):
    """Crea una fila real e independiente en DocumentoExpediente por cada fila del índice."""
    creados = []
    for numero, nombre, tipo_documento, folio_inicio, folio_fin in documentos:
        documento = DocumentoExpediente(
            expediente_id=expediente.id,
            registro_coordinacion_id=registro.id,
            nombre_documento=nombre,
            tipo_documento=tipo_documento,
            folio_inicio=folio_inicio,
            folio_fin=folio_fin,
            total_folios=folio_fin - folio_inicio + 1,
            estado_revision="Pendiente de revisión",
            es_anexo=False,
            observaciones=(
                f"Documento individual #{numero} incorporado desde la recepción de expediente completo "
                f"No. {registro.id}; folios confirmados manualmente por el usuario."
            ),
        )
        db.session.add(documento)
        db.session.flush()
        creados.append(documento)
        registrar_bitacora(
            accion="REGISTRAR_DOCUMENTO_EXPEDIENTE",
            modulo="Índice documental",
            descripcion=(
                f"Se incorporó como documento independiente '{documento.nombre_documento}' "
                f"al SP {expediente.no_sp}, folios {documento.folio_inicio}-{documento.folio_fin}, "
                f"desde la recepción de expediente completo No. {registro.id}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="DocumentoExpediente",
            entidad_id=documento.id,
            datos_posteriores={
                "documento_id": documento.id,
                "registro_recepcion_id": registro.id,
                "numero_indice": numero,
                "nombre": documento.nombre_documento,
                "tipo_documento": documento.tipo_documento,
                "folio_inicio": documento.folio_inicio,
                "folio_fin": documento.folio_fin,
                "total_folios": documento.total_folios,
            },
            commit=False,
        )
    return creados


@coordinacion_bp.route(
    "/registrar/expediente-completo",
    methods=["GET", "POST"],
    endpoint="registrar_expediente_completo",
)
@login_required
def registrar_expediente_completo():
    form = RecepcionExpedienteCompletoForm()
    _cargar_opciones(form)
    documentos_vista = _documentos_para_vista()

    if form.validate_on_submit():
        expediente = Expediente.query.filter_by(id=form.expediente_id.data, activo=True).first()
        if not expediente:
            flash("El SP seleccionado no existe o se encuentra inactivo.", "danger")
            return render_template("coordinacion/expediente_completo.html", form=form, documentos=documentos_vista)

        documentos, errores = _documentos_desde_formulario()
        if errores:
            for error in errores[:6]:
                flash(error, "warning")
            return render_template("coordinacion/expediente_completo.html", form=form, documentos=documentos_vista)

        conflictos = _buscar_conflictos(expediente.id, documentos)
        if conflictos:
            rangos = ", ".join(
                f"{doc.folio_inicio}-{doc.folio_fin}" if doc.folio_inicio != doc.folio_fin else str(doc.folio_inicio)
                for doc in conflictos[:6]
            )
            flash(
                f"No se adjuntó la documentación porque el SP {expediente.no_sp} ya tiene "
                f"documentos activos en los folios {rangos}. Revise primero su índice documental.",
                "warning",
            )
            return render_template("coordinacion/expediente_completo.html", form=form, documentos=documentos_vista)

        ahora_gt = datetime.now(GUATEMALA_TZ)
        ahora_utc = ahora_gt.astimezone(timezone.utc).replace(tzinfo=None)
        fecha_hora_legible = ahora_gt.strftime("%d/%m/%Y %H:%M:%S")

        referencia = f"{form.tipo_referencia.data} {form.numero_referencia.data.strip()}"
        folio_min = min(item[3] for item in documentos)
        folio_max = max(item[4] for item in documentos)
        total_folios_documentados = sum(item[4] - item[3] + 1 for item in documentos)
        forma_legible = FORMAS_REGISTRO.get(form.forma_registro.data, form.forma_registro.data)

        registro = RegistroCoordinacion(
            tipo="EXPEDIENTE_COMPLETO",
            expediente_id=expediente.id,
            no_sp_referencia=expediente.no_sp,
            rc=referencia,
            fecha_recepcion=ahora_gt.date(),
            persona_entrega=form.persona_entrega.data.strip(),
            folios_recepcion=(
                f"{len(documentos)} documentos individuales; rango general {folio_min}-{folio_max}; "
                f"{total_folios_documentados} folios documentados"
            ),
            usuario_id=current_user.id,
            usuario_origen=current_user.nombre,
            estado="Completo",
            observaciones=(
                f"Recepción de expediente completo. Fecha y hora automática: {fecha_hora_legible} "
                f"(America/Guatemala). Forma de registro: {forma_legible}. "
                f"Cada una de las {len(documentos)} filas del índice se creó como un documento independiente del SP."
            ),
            origen_registro="MANUAL",
            creado_en=ahora_utc,
            actualizado_en=ahora_utc,
        )
        db.session.add(registro)
        db.session.flush()

        documentos_creados = _crear_documentos_individuales(expediente, registro, documentos)

        registrar_bitacora(
            accion="REGISTRAR_EXPEDIENTE_COMPLETO",
            modulo="Coordinación",
            descripcion=(
                f"Se recibió expediente completo del SP {expediente.no_sp} el {fecha_hora_legible} "
                f"(Guatemala); referencia {referencia}; se crearon {len(documentos_creados)} documentos "
                f"independientes en el índice documental."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="RegistroCoordinacion",
            entidad_id=registro.id,
            datos_posteriores={
                "tipo": registro.tipo,
                "sp": expediente.no_sp,
                "referencia": referencia,
                "fecha_recepcion": ahora_gt.strftime("%Y-%m-%d"),
                "hora_recepcion": ahora_gt.strftime("%H:%M:%S"),
                "fecha_hora_recepcion": ahora_gt.isoformat(),
                "zona_horaria": "America/Guatemala",
                "forma_registro": form.forma_registro.data,
                "documentos_independientes": len(documentos_creados),
                "documentos_creados": [
                    {
                        "id": doc.id,
                        "nombre": doc.nombre_documento,
                        "tipo": doc.tipo_documento,
                        "folio_inicio": doc.folio_inicio,
                        "folio_fin": doc.folio_fin,
                    }
                    for doc in documentos_creados
                ],
                "rango_general": f"{folio_min}-{folio_max}",
                "folios_documentados": total_folios_documentados,
            },
            commit=False,
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        flash(
            f"Expediente completo recibido el {fecha_hora_legible}. Se crearon {len(documentos_creados)} "
            f"documentos independientes en el SP {expediente.no_sp} con referencia {referencia}.",
            "success",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    return render_template("coordinacion/expediente_completo.html", form=form, documentos=documentos_vista)
