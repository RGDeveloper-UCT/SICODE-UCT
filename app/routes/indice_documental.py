from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.indice_documental_form import IndiceDocumentalForm
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.services.alertas_service import crear_alerta_si_no_existe
from app.services.bitacora_service import registrar_bitacora


indice_documental_bp = Blueprint("indice_documental", __name__)


def _anexo_pendiente(expediente_id, anexo_id):
    if not anexo_id:
        return None
    try:
        identificador = int(anexo_id)
    except (TypeError, ValueError):
        return None

    return (
        AnexoCoordinacion.query
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            AnexoCoordinacion.id == identificador,
            RegistroCoordinacion.expediente_id == expediente_id,
            AnexoCoordinacion.documento_expediente_id.is_(None),
        )
        .first()
    )


@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental", methods=["GET", "POST"])
@login_required
def listado(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.expediente_fisico_registrado:
        flash("Primero debe registrar la existencia física del expediente antes de crear su índice documental.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    form = IndiceDocumentalForm()

    if request.method == "GET":
        anexo_preseleccionado = _anexo_pendiente(expediente.id, request.args.get("anexo_id"))
        if anexo_preseleccionado:
            form.anexo_coordinacion_id.data = str(anexo_preseleccionado.id)
            form.tipo_documento.data = "Anexo"
            form.nombre_documento.data = (
                f"Anexo {anexo_preseleccionado.numero_anexo or ''} - {anexo_preseleccionado.tipo_anexo or 'Sin tipo'}"
            ).strip(" -")
            if anexo_preseleccionado.registro.observaciones:
                form.observaciones.data = anexo_preseleccionado.registro.observaciones

    if form.validate_on_submit():
        folio_inicio = form.folio_inicio.data
        folio_fin = form.folio_fin.data

        if folio_inicio > folio_fin:
            flash("El folio inicial no puede ser mayor que el folio final.", "danger")
            return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        traslape = (
            DocumentoExpediente.query
            .filter(
                DocumentoExpediente.expediente_id == expediente.id,
                DocumentoExpediente.activo.is_(True),
                DocumentoExpediente.folio_inicio <= folio_fin,
                DocumentoExpediente.folio_fin >= folio_inicio,
            )
            .first()
        )
        if traslape:
            flash(
                f"El rango se traslapa con '{traslape.nombre_documento}', folios {traslape.folio_inicio}-{traslape.folio_fin}.",
                "danger",
            )
            return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        anexo = None
        if form.anexo_coordinacion_id.data:
            anexo = _anexo_pendiente(expediente.id, form.anexo_coordinacion_id.data)
            if not anexo:
                flash("El anexo de Coordinación ya fue incorporado o no pertenece a este expediente.", "danger")
                return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
            if form.tipo_documento.data != "Anexo":
                flash("Un registro proveniente de Anexos debe incorporarse al índice con tipo Anexo.", "danger")
                return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        documento = DocumentoExpediente(
            expediente_id=expediente.id,
            nombre_documento=form.nombre_documento.data.strip(),
            tipo_documento=form.tipo_documento.data,
            folio_inicio=folio_inicio,
            folio_fin=folio_fin,
            total_folios=folio_fin - folio_inicio + 1,
            estado_revision=form.estado_revision.data,
            es_anexo=form.tipo_documento.data == "Anexo",
            observaciones=form.observaciones.data,
            activo=True,
        )
        db.session.add(documento)
        db.session.flush()

        if anexo:
            anexo.documento_expediente_id = documento.id

        registrar_bitacora(
            accion="AGREGAR_INDICE_DOCUMENTAL",
            modulo="Índice documental",
            descripcion=(
                f"Se agregó '{documento.nombre_documento}' al índice del SP {expediente.no_sp}, "
                f"folios {documento.folio_inicio}-{documento.folio_fin}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="DocumentoExpediente",
            entidad_id=documento.id,
            datos_posteriores={
                "nombre": documento.nombre_documento,
                "tipo": documento.tipo_documento,
                "folio_inicio": documento.folio_inicio,
                "folio_fin": documento.folio_fin,
                "anexo_coordinacion_id": anexo.id if anexo else None,
            },
            commit=False,
        )
        db.session.commit()

        if documento.estado_revision in {"Mal foliado", "Anexo pendiente", "Con observaciones"}:
            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                documento_id=documento.id,
                tipo_alerta="REVISION_INDICE_DOCUMENTAL",
                titulo=f"Revisión documental requerida: {documento.nombre_documento}",
                descripcion=(
                    f"El documento fue registrado con estado '{documento.estado_revision}' "
                    f"en los folios {documento.folio_inicio}-{documento.folio_fin}."
                ),
                gravedad="Alta" if documento.estado_revision == "Mal foliado" else "Media",
                usuario_id=current_user.id,
            )

        flash("Documento agregado al índice correctamente.", "success")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    documentos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=True)
        .order_by(DocumentoExpediente.folio_inicio.asc())
        .all()
    )
    documentos_inactivos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=False)
        .order_by(DocumentoExpediente.folio_inicio.asc())
        .all()
    )
    anexos_pendientes = (
        AnexoCoordinacion.query
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id == expediente.id,
            AnexoCoordinacion.documento_expediente_id.is_(None),
        )
        .order_by(RegistroCoordinacion.fecha_recepcion.asc().nullslast(), AnexoCoordinacion.id.asc())
        .all()
    )

    return render_template(
        "indice_documental/listado.html",
        expediente=expediente,
        form=form,
        documentos=documentos,
        documentos_inactivos=documentos_inactivos,
        anexos_pendientes=anexos_pendientes,
        total_folios=sum(documento.total_folios or 0 for documento in documentos),
    )


@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/anular", methods=["POST"])
@login_required
def anular(expediente_id, documento_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    documento = DocumentoExpediente.query.filter_by(id=documento_id, expediente_id=expediente.id).first_or_404()

    if not documento.activo:
        flash("El registro documental ya se encuentra anulado.", "warning")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    documento.activo = False
    registrar_bitacora(
        accion="ANULAR_INDICE_DOCUMENTAL",
        modulo="Índice documental",
        descripcion=f"Se anuló '{documento.nombre_documento}' del índice del SP {expediente.no_sp}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="DocumentoExpediente",
        entidad_id=documento.id,
        datos_anteriores={"activo": True},
        datos_posteriores={"activo": False},
        commit=False,
    )
    db.session.commit()

    flash("Registro documental anulado. Se conserva para trazabilidad.", "info")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
