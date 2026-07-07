from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.forms.indice_documental_form import IndiceDocumentalForm
from app.models.expediente import Expediente
from app.models.documento_expediente import DocumentoExpediente
from app.services.bitacora_service import registrar_bitacora
from app.services.alertas_service import crear_alerta_si_no_existe

indice_documental_bp = Blueprint("indice_documental", __name__)

@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental", methods=["GET", "POST"])
@login_required
def listado(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    form = IndiceDocumentalForm()

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
                DocumentoExpediente.activo == True,
                DocumentoExpediente.folio_inicio <= folio_fin,
                DocumentoExpediente.folio_fin >= folio_inicio,
            )
            .first()
        )

        if traslape:
            flash(
                f"El rango de folios se traslapa con el documento '{traslape.nombre_documento}' "
                f"folios {traslape.folio_inicio}-{traslape.folio_fin}.",
                "danger",
            )
            return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        total_folios = folio_fin - folio_inicio + 1
        tipo_documento = form.tipo_documento.data

        documento = DocumentoExpediente(
            expediente_id=expediente.id,
            nombre_documento=form.nombre_documento.data.strip(),
            tipo_documento=tipo_documento,
            folio_inicio=folio_inicio,
            folio_fin=folio_fin,
            total_folios=total_folios,
            estado_revision=form.estado_revision.data,
            es_anexo=True if tipo_documento == "Anexo" else False,
            observaciones=form.observaciones.data,
            activo=True,
        )

        db.session.add(documento)
        db.session.commit()

        registrar_bitacora(
            accion="AGREGAR_INDICE_DOCUMENTAL",
            modulo="Índice documental",
            descripcion=(
                f"Se agregó '{documento.nombre_documento}' al índice documental del expediente "
                f"No. de SP {expediente.no_sp}, folios {documento.folio_inicio}-{documento.folio_fin}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        if documento.estado_revision in ["Mal foliado", "Anexo pendiente", "Con observaciones"]:
            gravedad = "Alta" if documento.estado_revision == "Mal foliado" else "Media"

            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                documento_id=documento.id,
                tipo_alerta="REVISION_INDICE_DOCUMENTAL",
                titulo=f"Revisión documental requerida: {documento.nombre_documento}",
                descripcion=(
                    f"El documento '{documento.nombre_documento}' fue registrado con estado "
                    f"'{documento.estado_revision}' en los folios {documento.folio_inicio}-{documento.folio_fin}."
                ),
                gravedad=gravedad,
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

    total_folios = sum(documento.total_folios or 0 for documento in documentos)

    return render_template(
        "indice_documental/listado.html",
        expediente=expediente,
        form=form,
        documentos=documentos,
        documentos_inactivos=documentos_inactivos,
        total_folios=total_folios,
    )

@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/anular", methods=["POST"])
@login_required
def anular(expediente_id, documento_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    documento = (
        DocumentoExpediente.query
        .filter_by(id=documento_id, expediente_id=expediente.id)
        .first_or_404()
    )

    if not documento.activo:
        flash("El registro documental ya se encuentra anulado.", "warning")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    documento.activo = False
    db.session.commit()

    registrar_bitacora(
        accion="ANULAR_INDICE_DOCUMENTAL",
        modulo="Índice documental",
        descripcion=(
            f"Se anuló del índice documental el registro '{documento.nombre_documento}' "
            f"del expediente No. de SP {expediente.no_sp}."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Registro documental anulado. Se conserva para trazabilidad.", "info")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
