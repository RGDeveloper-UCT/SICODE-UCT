import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms.indice_documental_form import IndiceDocumentalForm
from app.models.alerta import Alerta
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.services.alertas_service import crear_alerta_si_no_existe
from app.services.bitacora_service import registrar_bitacora
from app.services.foliacion_service import es_foliacion_principal


indice_documental_bp = Blueprint("indice_documental", __name__)

ESTADOS_INCIDENCIA = {"Mal foliado", "Anexo pendiente", "Con observaciones"}
ESTADO_PENDIENTE = "Pendiente de revisión"
ESTADO_VERIFICADO = "Verificado"


def _exigir_modificacion():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)


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


def _rango_folios_recepcion(valor):
    """Convierte el dato de recepción en una sugerencia para la foliación del anexo."""
    if valor is None:
        return None, None

    texto = str(valor).strip()
    if not texto:
        return None, None

    if re.fullmatch(r"\d+", texto):
        total = int(texto)
        return (1, total) if total >= 1 else (None, None)

    coincidencia = re.fullmatch(r"\s*(\d+)\s*[-–—]\s*(\d+)\s*", texto)
    if coincidencia:
        inicio = int(coincidencia.group(1))
        fin = int(coincidencia.group(2))
        if inicio >= 1 and fin >= inicio:
            return inicio, fin

    return None, None


def _alertas_revision_abiertas(documento):
    return (
        Alerta.query
        .filter(
            Alerta.documento_id == documento.id,
            Alerta.tipo_alerta == "REVISION_INDICE_DOCUMENTAL",
            Alerta.estado.in_(["Abierta", "En revisión"]),
        )
        .order_by(Alerta.id.asc())
        .all()
    )


def _corregir_alertas_documento(documento):
    alertas = _alertas_revision_abiertas(documento)
    for alerta in alertas:
        alerta.estado = "Corregida"
        alerta.cerrado_en = None
        alerta.cerrada_por_id = None
    return [alerta.id for alerta in alertas]


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

            folios_recepcion = anexo_preseleccionado.folios or anexo_preseleccionado.registro.folios_recepcion
            folio_inicio_sugerido, folio_fin_sugerido = _rango_folios_recepcion(folios_recepcion)
            if folio_inicio_sugerido is not None:
                form.folio_inicio.data = folio_inicio_sugerido
                form.folio_fin.data = folio_fin_sugerido

    if form.validate_on_submit():
        _exigir_modificacion()
        folio_inicio = form.folio_inicio.data
        folio_fin = form.folio_fin.data
        es_anexo = form.tipo_documento.data == "Anexo"

        if folio_inicio > folio_fin:
            flash("El folio inicial no puede ser mayor que el folio final.", "danger")
            return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        if not es_anexo:
            traslape = (
                DocumentoExpediente.query
                .filter(
                    DocumentoExpediente.expediente_id == expediente.id,
                    DocumentoExpediente.activo.is_(True),
                    or_(
                        DocumentoExpediente.es_anexo.is_(False),
                        DocumentoExpediente.es_anexo.is_(None),
                    ),
                    DocumentoExpediente.folio_inicio <= folio_fin,
                    DocumentoExpediente.folio_fin >= folio_inicio,
                )
                .first()
            )
            if traslape:
                flash(
                    f"El rango se traslapa con '{traslape.nombre_documento}', folios {traslape.folio_inicio}-{traslape.folio_fin}, dentro de la foliación general del expediente.",
                    "danger",
                )
                return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

        anexo = None
        if form.anexo_coordinacion_id.data:
            anexo = _anexo_pendiente(expediente.id, form.anexo_coordinacion_id.data)
            if not anexo:
                flash("El anexo de Coordinación ya fue incorporado o no pertenece a este expediente.", "danger")
                return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
            if not es_anexo:
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
            es_anexo=es_anexo,
            observaciones=form.observaciones.data,
            activo=True,
        )
        db.session.add(documento)
        db.session.flush()

        if anexo:
            anexo.documento_expediente_id = documento.id

        ambito_foliacion = "anexo independiente" if documento.es_anexo else "expediente principal"
        registrar_bitacora(
            accion="AGREGAR_INDICE_DOCUMENTAL",
            modulo="Índice documental",
            descripcion=(
                f"Se agregó '{documento.nombre_documento}' al índice del SP {expediente.no_sp}, "
                f"folios {documento.folio_inicio}-{documento.folio_fin} ({ambito_foliacion})."
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
                "ambito_foliacion": ambito_foliacion,
                "anexo_coordinacion_id": anexo.id if anexo else None,
            },
            commit=False,
        )

        if documento.estado_revision in ESTADOS_INCIDENCIA:
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
                commit=False,
            )

        db.session.commit()

        if documento.es_anexo:
            flash("Anexo agregado correctamente con foliación independiente.", "success")
        else:
            flash("Documento agregado a la foliación general del expediente correctamente.", "success")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    documentos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=True)
        .order_by(DocumentoExpediente.folio_inicio.asc(), DocumentoExpediente.id.asc())
        .all()
    )
    documentos_inactivos = (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente.id, activo=False)
        .order_by(DocumentoExpediente.folio_inicio.asc(), DocumentoExpediente.id.asc())
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

    documentos_principales = [documento for documento in documentos if es_foliacion_principal(documento)]
    anexos_documentales = [documento for documento in documentos if documento.es_anexo]

    return render_template(
        "indice_documental/listado.html",
        expediente=expediente,
        form=form,
        documentos=documentos,
        documentos_principales=documentos_principales,
        anexos_documentales=anexos_documentales,
        documentos_inactivos=documentos_inactivos,
        anexos_pendientes=anexos_pendientes,
        estados_incidencia=ESTADOS_INCIDENCIA,
        total_folios=sum(documento.total_folios or 0 for documento in documentos_principales),
    )


@indice_documental_bp.route(
    "/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/verificar",
    methods=["POST"],
)
@login_required
def verificar_documento(expediente_id, documento_id):
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)
    documento = DocumentoExpediente.query.filter_by(
        id=documento_id,
        expediente_id=expediente.id,
        activo=True,
    ).first_or_404()

    if documento.estado_revision == ESTADO_VERIFICADO:
        flash(f"'{documento.nombre_documento}' ya se encuentra verificado.", "info")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    if documento.estado_revision in ESTADOS_INCIDENCIA:
        flash(
            "Este registro tiene una incidencia documental. Debe usar «Resolver incidencia» y dejar el motivo de la corrección; no puede sobrescribirse directamente como Verificado.",
            "warning",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    if documento.estado_revision != ESTADO_PENDIENTE:
        flash(
            f"El estado '{documento.estado_revision}' no admite verificación rápida. Revise el registro antes de continuar.",
            "warning",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    documento.estado_revision = ESTADO_VERIFICADO
    registrar_bitacora(
        accion="VERIFICAR_DOCUMENTO_INDICE",
        modulo="Índice documental",
        descripcion=(
            f"Se verificó '{documento.nombre_documento}' del índice del SP {expediente.no_sp}, "
            f"folios {documento.folio_inicio}-{documento.folio_fin}."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="DocumentoExpediente",
        entidad_id=documento.id,
        datos_anteriores={"estado_revision": ESTADO_PENDIENTE},
        datos_posteriores={"estado_revision": ESTADO_VERIFICADO},
        commit=False,
    )
    db.session.commit()

    flash(f"Documento verificado: {documento.nombre_documento}.", "success")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))


@indice_documental_bp.route(
    "/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/resolver-incidencia",
    methods=["POST"],
)
@login_required
def resolver_incidencia(expediente_id, documento_id):
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)
    documento = DocumentoExpediente.query.filter_by(
        id=documento_id,
        expediente_id=expediente.id,
        activo=True,
    ).first_or_404()

    if documento.estado_revision not in ESTADOS_INCIDENCIA:
        flash("El registro no tiene una incidencia documental pendiente de resolución.", "info")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    motivo = (request.form.get("motivo_resolucion") or "").strip()
    if len(motivo) < 8:
        flash("Explique brevemente cómo se corrigió o verificó la incidencia (mínimo 8 caracteres).", "warning")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    estado_anterior = documento.estado_revision
    documento.estado_revision = ESTADO_VERIFICADO
    alertas_corregidas = _corregir_alertas_documento(documento)

    registrar_bitacora(
        accion="RESOLVER_INCIDENCIA_INDICE",
        modulo="Índice documental",
        descripcion=(
            f"Se resolvió la incidencia '{estado_anterior}' de '{documento.nombre_documento}' "
            f"del SP {expediente.no_sp}; el registro quedó Verificado."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="DocumentoExpediente",
        entidad_id=documento.id,
        datos_anteriores={
            "estado_revision": estado_anterior,
            "alertas_abiertas": alertas_corregidas,
        },
        datos_posteriores={
            "estado_revision": ESTADO_VERIFICADO,
            "alertas_corregidas": alertas_corregidas,
        },
        motivo=motivo,
        commit=False,
    )
    db.session.commit()

    flash(f"Incidencia resuelta y trazada para: {documento.nombre_documento}.", "success")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))


@indice_documental_bp.route(
    "/expedientes/<int:expediente_id>/indice-documental/verificar-todos",
    methods=["POST"],
)
@login_required
def verificar_todos(expediente_id):
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)

    pendientes = (
        DocumentoExpediente.query
        .filter(
            DocumentoExpediente.expediente_id == expediente.id,
            DocumentoExpediente.activo.is_(True),
            DocumentoExpediente.estado_revision == ESTADO_PENDIENTE,
        )
        .order_by(DocumentoExpediente.id.asc())
        .all()
    )

    if not pendientes:
        flash("No hay documentos pendientes de revisión para verificar.", "info")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    ids_verificados = []
    for documento in pendientes:
        documento.estado_revision = ESTADO_VERIFICADO
        ids_verificados.append(documento.id)

    registrar_bitacora(
        accion="VERIFICAR_TODOS_DOCUMENTOS_INDICE",
        modulo="Índice documental",
        descripcion=(
            f"Se verificaron {len(pendientes)} documentos pendientes del índice del SP {expediente.no_sp}. "
            "Los documentos con observaciones o incidencias conservaron su estado."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
        datos_anteriores={
            "estado_revision": ESTADO_PENDIENTE,
            "documentos": ids_verificados,
        },
        datos_posteriores={
            "estado_revision": ESTADO_VERIFICADO,
            "cantidad": len(ids_verificados),
            "documentos": ids_verificados,
        },
        commit=False,
    )
    db.session.commit()

    flash(
        f"Se verificaron {len(ids_verificados)} documentos pendientes. "
        "Los registros con observaciones o incidencias no fueron modificados.",
        "success",
    )
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))


@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/anular", methods=["POST"])
@login_required
def anular(expediente_id, documento_id):
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)
    documento = DocumentoExpediente.query.filter_by(id=documento_id, expediente_id=expediente.id).first_or_404()

    if not documento.activo:
        flash("El registro documental ya se encuentra anulado.", "warning")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    anexo = documento.anexo_recepcion
    anexo_id = anexo.id if anexo else None
    alertas_corregidas = _corregir_alertas_documento(documento)

    documento.activo = False
    if anexo:
        anexo.documento_expediente_id = None

    registrar_bitacora(
        accion="ANULAR_INDICE_DOCUMENTAL",
        modulo="Índice documental",
        descripcion=(
            f"Se anuló '{documento.nombre_documento}' del índice del SP {expediente.no_sp}."
            + (" El anexo de Coordinación quedó disponible para reincorporación." if anexo else "")
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="DocumentoExpediente",
        entidad_id=documento.id,
        datos_anteriores={
            "activo": True,
            "anexo_coordinacion_id": anexo_id,
            "alertas_abiertas": alertas_corregidas,
        },
        datos_posteriores={
            "activo": False,
            "anexo_reincorporable": bool(anexo),
            "alertas_corregidas": alertas_corregidas,
        },
        commit=False,
    )
    db.session.commit()

    if anexo:
        flash("Registro anulado. El anexo volvió a quedar disponible para incorporarlo correctamente al índice.", "info")
    else:
        flash("Registro documental anulado. Se conserva para trazabilidad.", "info")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
