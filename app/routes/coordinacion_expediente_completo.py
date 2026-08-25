from datetime import date

from flask import flash, redirect, render_template, url_for
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


PLANTILLA_INSTALACION_TRASLADO = {
    "codigo": "INSTALACION_TRASLADO_8_DOCS",
    "nombre": "Instalación / traslado — 8 documentos, folios 1-34",
    "documentos": [
        (1, "Solicitud de Informe de Factibilidad", "SOLICITUD", 1, 4),
        (2, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 5, 7),
        (3, "Informe de Factibilidad", "INFORME", 8, 12),
        (4, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 13, 14),
        (5, "Orden de Instalación y pago", "ORDEN", 15, 21),
        (6, "Boleta de Instalación", "BOLETA", 22, 22),
        (7, "Actas de Instalación", "ACTA", 23, 26),
        (8, "Providencias de traslados entre coordinaciones", "PROVIDENCIA", 27, 34),
    ],
}

PLANTILLAS = {
    PLANTILLA_INSTALACION_TRASLADO["codigo"]: PLANTILLA_INSTALACION_TRASLADO,
}

# Extiende el catálogo ya usado por el panel de Registros. Así se incorpora la
# tarjeta sin duplicar el dashboard ni crear un segundo panel de Coordinación.
TIPOS_REGISTRO["expediente-completo"] = {
    "codigo": "EXPEDIENTE_COMPLETO",
    "titulo": "Expediente completo",
    "descripcion": "Recepción de expediente completo y carga automática de su índice documental al SP seleccionado.",
}


class RecepcionExpedienteCompletoForm(FlaskForm):
    expediente_id = SelectField("SP al que se adjuntará", coerce=int, validators=[DataRequired()])
    plantilla = SelectField("Plantilla documental", validators=[DataRequired()])
    rc = StringField("RC", validators=[DataRequired(), Length(max=80)])
    persona_entrega = StringField("Quién entrega / remite", validators=[DataRequired(), Length(max=180)])
    submit = SubmitField("Registrar y adjuntar documentación")


def _cargar_opciones(form):
    expedientes = Expediente.query.filter_by(activo=True).order_by(Expediente.no_sp.asc()).all()
    form.expediente_id.choices = [
        (exp.id, f"{exp.no_sp} — {exp.nombre_referencia or exp.codigo_interno or 'Expediente'}")
        for exp in expedientes
    ]
    form.plantilla.choices = [
        (codigo, plantilla["nombre"])
        for codigo, plantilla in PLANTILLAS.items()
    ]


def _buscar_conflictos(expediente_id, documentos):
    inicio = min(item[3] for item in documentos)
    fin = max(item[4] for item in documentos)
    return (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente_id, activo=True)
        .filter(
            DocumentoExpediente.folio_inicio <= fin,
            DocumentoExpediente.folio_fin >= inicio,
        )
        .order_by(DocumentoExpediente.folio_inicio.asc())
        .all()
    )


@coordinacion_bp.route("/registrar/expediente-completo", methods=["GET", "POST"], endpoint="registrar_expediente_completo")
@login_required
def registrar_expediente_completo():
    form = RecepcionExpedienteCompletoForm()
    _cargar_opciones(form)

    plantilla_codigo = form.plantilla.data or PLANTILLA_INSTALACION_TRASLADO["codigo"]
    plantilla = PLANTILLAS.get(plantilla_codigo, PLANTILLA_INSTALACION_TRASLADO)

    if form.validate_on_submit():
        expediente = Expediente.query.filter_by(id=form.expediente_id.data, activo=True).first()
        if not expediente:
            flash("El SP seleccionado no existe o se encuentra inactivo.", "danger")
            return render_template(
                "coordinacion/expediente_completo.html",
                form=form,
                plantilla=plantilla,
            )

        plantilla = PLANTILLAS.get(form.plantilla.data)
        if not plantilla:
            flash("La plantilla documental seleccionada no es válida.", "danger")
            return render_template(
                "coordinacion/expediente_completo.html",
                form=form,
                plantilla=PLANTILLA_INSTALACION_TRASLADO,
            )

        conflictos = _buscar_conflictos(expediente.id, plantilla["documentos"])
        if conflictos:
            rangos = ", ".join(
                f"{doc.folio_inicio}-{doc.folio_fin}" if doc.folio_inicio != doc.folio_fin else str(doc.folio_inicio)
                for doc in conflictos[:6]
            )
            flash(
                f"No se adjuntó la plantilla porque el SP {expediente.no_sp} ya tiene documentos activos en los folios {rangos}. Revise primero su índice documental.",
                "warning",
            )
            return render_template(
                "coordinacion/expediente_completo.html",
                form=form,
                plantilla=plantilla,
            )

        registro = RegistroCoordinacion(
            tipo="EXPEDIENTE_COMPLETO",
            expediente_id=expediente.id,
            no_sp_referencia=expediente.no_sp,
            rc=form.rc.data.strip(),
            fecha_recepcion=date.today(),
            persona_entrega=form.persona_entrega.data.strip(),
            folios_recepcion="1-34 (34 folios)",
            usuario_id=current_user.id,
            usuario_origen=current_user.nombre,
            estado="Completo",
            observaciones=(
                f"Recepción de expediente completo. Plantilla: {plantilla['nombre']}. "
                f"Se incorporaron {len(plantilla['documentos'])} documentos al índice documental del SP."
            ),
            origen_registro="MANUAL",
        )
        db.session.add(registro)
        db.session.flush()

        for numero, nombre, tipo_documento, folio_inicio, folio_fin in plantilla["documentos"]:
            db.session.add(
                DocumentoExpediente(
                    expediente_id=expediente.id,
                    nombre_documento=nombre,
                    tipo_documento=tipo_documento,
                    folio_inicio=folio_inicio,
                    folio_fin=folio_fin,
                    total_folios=folio_fin - folio_inicio + 1,
                    estado_revision="Pendiente de revisión",
                    es_anexo=False,
                    observaciones=(
                        f"Documento #{numero} incorporado automáticamente desde la recepción "
                        f"de expediente completo No. {registro.id}."
                    ),
                )
            )

        registrar_bitacora(
            accion="REGISTRAR_EXPEDIENTE_COMPLETO",
            modulo="Coordinación",
            descripcion=(
                f"Se recibió expediente completo del SP {expediente.no_sp}; "
                f"RC {registro.rc}; se incorporaron 8 documentos, folios 1-34, al índice documental."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="RegistroCoordinacion",
            entidad_id=registro.id,
            datos_posteriores={
                "tipo": registro.tipo,
                "sp": expediente.no_sp,
                "rc": registro.rc,
                "plantilla": plantilla["codigo"],
                "documentos": len(plantilla["documentos"]),
                "folios": "1-34",
            },
            commit=False,
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        flash(
            f"Expediente completo recibido. Se adjuntaron 8 documentos (folios 1-34) al SP {expediente.no_sp}.",
            "success",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    return render_template(
        "coordinacion/expediente_completo.html",
        form=form,
        plantilla=plantilla,
    )
