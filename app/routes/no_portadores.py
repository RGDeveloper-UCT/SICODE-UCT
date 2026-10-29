"""Control de NO PORTADORES. Todo el flujo se mantiene fuera de tablas SP."""
from datetime import date, datetime
from io import BytesIO
from urllib.parse import urlparse
from uuid import uuid4
from xml.sax.saxutils import escape

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.forms.no_portador_form import (
    AlertaNPForm, AnexoNPForm, DocumentoNPForm, NoPortadorForm,
    RectificacionNPForm, VerificacionNPForm,
)
from app.forms.prestamo_form import PrestamoForm, DevolucionForm, TrasladoVirtualForm
from app.models.no_portador import (
    AlertaNP, AnexoNP, DocumentoNP, NoPortador, PrestamoNP,
    TrasladoVirtualNP, UbicacionNP, VerificacionNP,
)
from app.services.bitacora_service import registrar_bitacora

no_portadores_bp = Blueprint("no_portadores", __name__, url_prefix="/no-portadores")

_DATOS_NP = (
    "numero_np", "codigo_interno", "nombre_referencia", "motivo_no_instalacion",
    "fecha_no_instalacion", "estado_administrativo", "expediente_fisico_registrado",
    "nombres", "apellidos", "genero", "fecha_nacimiento", "expediente_oj",
    "delito", "juez", "juzgado_tribunal", "abogado", "residencia",
    "municipio", "departamento", "telefono", "municipio_residencia",
    "departamento_residencia", "zona_inclusion", "zona_exclusion",
    "zona_prevencion", "financiamiento", "lugar_instalacion", "estado_monitoreo",
    "observaciones",
)
_UBICACION = ("archivador", "sicoin", "estante", "caja", "modulo", "posicion")
_DATOS_ANEXO = (
    "numero_anexo", "titulo", "tipo_anexo", "fecha_recepcion", "persona_entrega",
    "rc", "providencia", "folios", "escaneado", "fecha_escaneado", "observaciones",
)


def _exigir_editor():
    if not current_user.puede_modificar:
        abort(403)


def _auditar(accion, np, descripcion, anteriores=None, posteriores=None):
    registrar_bitacora(
        accion=accion, modulo="No Portadores", descripcion=descripcion,
        usuario_id=current_user.id, entidad="NoPortador", entidad_id=np.id,
        datos_anteriores=anteriores, datos_posteriores=posteriores, commit=False,
    )


def _guardar():
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        flash("No se pudo guardar: número NP, código o préstamo duplicado.", "danger")
        return False


def _form_detalle(np):
    return dict(
        np=np,
        formulario_documento=DocumentoNPForm(),
        formulario_anexo=AnexoNPForm(),
        formulario_rectificacion=RectificacionNPForm(),
        formulario_verificacion=VerificacionNPForm(),
        formulario_alerta=AlertaNPForm(),
        formulario_prestamo=PrestamoForm(),
        formulario_devolucion=DevolucionForm(),
        formulario_traslado=TrasladoVirtualForm(),
        hoy=date.today(),
    )


@no_portadores_bp.route("/")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    estado = request.args.get("estado", "").strip()
    consulta = NoPortador.query
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(or_(
            NoPortador.numero_np.ilike(patron),
            NoPortador.codigo_interno.ilike(patron),
            NoPortador.nombre_referencia.ilike(patron),
            NoPortador.nombres.ilike(patron),
            NoPortador.apellidos.ilike(patron),
            NoPortador.expediente_oj.ilike(patron),
        ))
    if estado == "disponible":
        consulta = consulta.filter(NoPortador.activo.is_(True), NoPortador.expediente_fisico_registrado.is_(True),
            ~NoPortador.id.in_(db.session.query(PrestamoNP.np_id).filter(
                PrestamoNP.estado == "En préstamo", PrestamoNP.activo.is_(True))))
    elif estado == "sin_fisico":
        consulta = consulta.filter(NoPortador.expediente_fisico_registrado.is_(False))
    elif estado == "prestado":
        consulta = consulta.filter(NoPortador.id.in_(db.session.query(PrestamoNP.np_id).filter(
            PrestamoNP.estado == "En préstamo", PrestamoNP.activo.is_(True))))
    elif estado == "inactivo":
        consulta = consulta.filter(NoPortador.activo.is_(False))
    registros = consulta.order_by(NoPortador.creado_en.desc(), NoPortador.id.desc()).all()
    return render_template("no_portadores/listado.html", registros=registros, busqueda=busqueda, estado=estado)


@no_portadores_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    _exigir_editor()
    form = NoPortadorForm()
    if form.validate_on_submit():
        if NoPortador.query.filter(or_(
            NoPortador.numero_np == form.numero_np.data,
            NoPortador.codigo_interno == form.codigo_interno.data.strip(),
        )).first():
            flash("El número NP o el código interno ya existen dentro de No Portadores.", "danger")
        else:
            np = NoPortador()
            for campo in _DATOS_NP:
                valor = getattr(form, campo).data
                if isinstance(valor, str):
                    valor = valor.strip() or None
                setattr(np, campo, valor)
            db.session.add(np)
            db.session.flush()
            ubicacion = UbicacionNP(np_id=np.id)
            for campo in _UBICACION:
                setattr(ubicacion, campo, getattr(form, campo).data or None)
            db.session.add(ubicacion)
            _auditar("CREAR_NP", np, f"Se creó No Portador {np.numero_np}.")
            if _guardar():
                flash("NP creado correctamente.", "success")
                return redirect(url_for(".detalle", np_id=np.id))
    return render_template("no_portadores/formulario.html", form=form, modo="Nuevo")


@no_portadores_bp.route("/<int:np_id>")
@login_required
def detalle(np_id):
    np = NoPortador.query.get_or_404(np_id)
    return render_template("no_portadores/detalle.html", **_form_detalle(np))


@no_portadores_bp.route("/<int:np_id>/editar", methods=["GET", "POST"])
@login_required
def editar(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    ubicacion = np.ubicacion or UbicacionNP(np=np)
    form = NoPortadorForm()
    if form.validate_on_submit():
        existe = NoPortador.query.filter(
            NoPortador.id != np.id,
            or_(NoPortador.numero_np == form.numero_np.data,
                NoPortador.codigo_interno == form.codigo_interno.data.strip())
        ).first()
        if existe:
            flash("Ya existe otro NP con ese número o código interno.", "danger")
        elif not form.expediente_fisico_registrado.data and np.prestamo_activo:
            flash("No se puede quitar el expediente físico mientras esté prestado.", "danger")
        else:
            previos = {"numero_np": np.numero_np, "estado": np.estado_administrativo,
                        "motivo_no_instalacion": np.motivo_no_instalacion}
            for campo in _DATOS_NP:
                valor = getattr(form, campo).data
                if isinstance(valor, str):
                    valor = valor.strip() or None
                setattr(np, campo, valor)
            if ubicacion.id is None:
                db.session.add(ubicacion)
            for campo in _UBICACION:
                setattr(ubicacion, campo, getattr(form, campo).data or None)
            _auditar("EDITAR_NP", np, f"Se actualizó NP {np.numero_np}.",
                     anteriores=previos, posteriores={"numero_np": np.numero_np, "estado": np.estado_administrativo,
                     "motivo_no_instalacion": np.motivo_no_instalacion})
            if _guardar():
                flash("NP actualizado.", "success")
                return redirect(url_for(".detalle", np_id=np.id))
    elif request.method == "GET":
        for campo in _DATOS_NP:
            getattr(form, campo).data = getattr(np, campo)
        for campo in _UBICACION:
            getattr(form, campo).data = getattr(ubicacion, campo)
    return render_template("no_portadores/formulario.html", form=form, modo="Editar", np=np)


@no_portadores_bp.route("/<int:np_id>/rectificar", methods=["POST"])
@login_required
def rectificar(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = RectificacionNPForm()
    if not np.expediente_fisico_registrado:
        flash("Registre primero la existencia física del expediente NP.", "warning")
    elif form.validate_on_submit():
        previos = {"folios": np.folios_rectificados, "anexos": np.anexos_rectificados}
        np.folios_rectificados = form.folios_rectificados.data
        np.anexos_rectificados = form.anexos_rectificados.data
        np.rectificado_en = datetime.utcnow()
        np.rectificado_por_id = current_user.id
        np.estado_fisico_documental = "Pendiente de verificación"
        _auditar("RECTIFICAR_NP", np, f"Rectificación NP {np.numero_np}.",
                 anteriores=previos, posteriores={"folios": np.folios_rectificados, "anexos": np.anexos_rectificados})
        if _guardar():
            flash("Rectificación de folios y anexos confirmada.", "success")
    else:
        flash("Indique folios mayores que cero y anexos iguales o mayores que cero.", "danger")
    return redirect(url_for(".detalle", np_id=np.id))


@no_portadores_bp.route("/<int:np_id>/documentos/nuevo", methods=["POST"])
@login_required
def agregar_documento(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = DocumentoNPForm()
    if form.validate_on_submit():
        ini, fin = form.folio_inicio.data, form.folio_fin.data
        if fin < ini:
            flash("El folio final no puede ser menor que el inicial.", "danger")
        else:
            # Bloqueo del NP para serializar dos capturas concurrentes en PostgreSQL.
            db.session.query(NoPortador).filter_by(id=np_id).with_for_update().first()
            traslape = DocumentoNP.query.filter_by(np_id=np_id, activo=True).filter(
                DocumentoNP.folio_inicio <= fin, DocumentoNP.folio_fin >= ini).first()
            if traslape:
                flash(f"El rango se superpone con '{traslape.nombre_documento}'.", "danger")
            else:
                doc = DocumentoNP(np_id=np.id, nombre_documento=form.nombre_documento.data.strip(),
                    tipo_documento=form.tipo_documento.data.strip(), folio_inicio=ini,
                    folio_fin=fin, total_folios=fin - ini + 1, es_anexo=form.es_anexo.data,
                    indice_numero_anexo=form.indice_numero_anexo.data,
                    indice_titulo_anexo=form.nombre_documento.data.strip() if form.es_anexo.data else None,
                    estado_revision=form.estado_revision.data, observaciones=form.observaciones.data)
                db.session.add(doc)
                np.estado_fisico_documental = "Pendiente de verificación"
                _auditar("AGREGAR_DOCUMENTO_NP", np, f"Documento {doc.nombre_documento}, folios {ini}-{fin}.")
                if _guardar():
                    flash("Documento incorporado al índice NP.", "success")
    else:
        flash("Revise el documento y el rango de folios.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/documentos/<int:doc_id>/desactivar", methods=["POST"])
@login_required
def desactivar_documento(np_id, doc_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    doc = DocumentoNP.query.filter_by(id=doc_id, np_id=np_id, activo=True).first_or_404()
    doc.activo = False
    np.estado_fisico_documental = "Pendiente de verificación"
    _auditar("DESACTIVAR_DOCUMENTO_NP", np, f"Documento NP desactivado: {doc.nombre_documento}.")
    _guardar()
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/anexos/nuevo", methods=["POST"])
@login_required
def agregar_anexo(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = AnexoNPForm()
    if form.validate_on_submit():
        anexo = AnexoNP(np_id=np.id, creado_por_id=current_user.id)
        for campo in _DATOS_ANEXO:
            valor = getattr(form, campo).data
            if isinstance(valor, str):
                valor = valor.strip() or None
            setattr(anexo, campo, valor)
        db.session.add(anexo)
        np.estado_fisico_documental = "Pendiente de verificación"
        _auditar("AGREGAR_ANEXO_NP", np, f"Anexo NP registrado: {anexo.titulo}.")
        if _guardar():
            flash("Anexo NP registrado.", "success")
    else:
        flash("Revise los datos del anexo.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/anexos/<int:anexo_id>/desactivar", methods=["POST"])
@login_required
def desactivar_anexo(np_id, anexo_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    anexo = AnexoNP.query.filter_by(np_id=np_id, id=anexo_id, activo=True).first_or_404()
    anexo.activo = False
    np.estado_fisico_documental = "Pendiente de verificación"
    _auditar("DESACTIVAR_ANEXO_NP", np, f"Anexo desactivado: {anexo.titulo}.")
    _guardar()
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/verificar", methods=["POST"])
@login_required
def verificar(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = VerificacionNPForm()
    if form.validate_on_submit():
        verificacion = VerificacionNP(np_id=np.id, usuario_id=current_user.id,
            tipo=form.tipo.data, resultado=form.resultado.data,
            folios_verificados=form.folios_verificados.data,
            observaciones=form.observaciones.data)
        db.session.add(verificacion)
        np.estado_fisico_documental = form.resultado.data
        _auditar("VERIFICAR_NP", np, f"NP {np.numero_np}: {form.tipo.data} = {form.resultado.data}.")
        if _guardar():
            flash("Verificación registrada en el historial NP.", "success")
    else:
        flash("No fue posible validar la verificación.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/alertas/nueva", methods=["POST"])
@login_required
def crear_alerta(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = AlertaNPForm()
    if form.validate_on_submit():
        alerta = AlertaNP(np_id=np.id, tipo_alerta=form.tipo_alerta.data.strip(),
                         titulo=form.titulo.data.strip(), descripcion=form.descripcion.data,
                         gravedad=form.gravedad.data, creada_por_id=current_user.id)
        db.session.add(alerta)
        _auditar("CREAR_ALERTA_NP", np, f"Alerta NP: {alerta.titulo}.")
        if _guardar():
            flash("Alerta NP registrada.", "success")
    else:
        flash("Revise los datos de la alerta.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/alertas/<int:alerta_id>/resolver", methods=["POST"])
@login_required
def resolver_alerta(np_id, alerta_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    alerta = AlertaNP.query.filter_by(np_id=np_id, id=alerta_id).first_or_404()
    if alerta.estado != "Cerrada":
        alerta.estado = "Cerrada"
        alerta.cerrada_por_id = current_user.id
        alerta.cerrado_en = datetime.utcnow()
        _auditar("RESOLVER_ALERTA_NP", np, f"Alerta NP cerrada: {alerta.titulo}.")
        _guardar()
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/prestamos/nuevo", methods=["POST"])
@login_required
def nuevo_prestamo(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = PrestamoForm()
    if not np.activo or not np.expediente_fisico_registrado or not np.rectificacion_completa:
        flash("Para prestar NP necesita expediente físico activo y rectificación vigente.", "warning")
    elif form.validate_on_submit():
        db.session.query(NoPortador).filter_by(id=np_id).with_for_update().first()
        if np.prestamo_activo:
            flash("Este NP ya tiene un préstamo activo.", "danger")
        elif form.fecha_estimada_devolucion.data and form.fecha_estimada_devolucion.data < date.today():
            flash("La devolución estimada no puede ser anterior a hoy.", "danger")
        else:
            control = f"PRE-NP-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"
            prestamo = PrestamoNP(np_id=np.id, numero_control=control,
                solicitante=form.solicitante.data.strip(),
                persona_entrega=form.persona_entrega.data.strip(),
                persona_recibe=form.persona_recibe.data.strip(),
                fecha_estimada_devolucion=form.fecha_estimada_devolucion.data,
                observaciones=form.observaciones.data)
            db.session.add(prestamo)
            _auditar("PRESTAR_NP", np, f"Préstamo {control} de NP {np.numero_np}.")
            if _guardar():
                flash("Préstamo NP registrado.", "success")
                return redirect(url_for(".comprobante_pdf", np_id=np.id, prestamo_id=prestamo.id))
    else:
        flash("Complete los datos de solicitante, entrega y recepción.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/prestamos/<int:prestamo_id>/devolver", methods=["POST"])
@login_required
def devolver(np_id, prestamo_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    prestamo = PrestamoNP.query.filter_by(np_id=np_id, id=prestamo_id, activo=True).first_or_404()
    form = DevolucionForm()
    if prestamo.estado != "En préstamo":
        flash("Este préstamo NP ya fue devuelto.", "warning")
    elif form.validate_on_submit():
        prestamo.estado = "Devuelto"
        prestamo.fecha_real_devolucion = datetime.utcnow()
        prestamo.persona_devuelve = form.persona_devuelve.data.strip()
        prestamo.persona_recibe_devolucion = form.persona_recibe_devolucion.data.strip()
        prestamo.observaciones_devolucion = form.observaciones_devolucion.data
        _auditar("DEVOLVER_NP", np, f"Devolución NP, control {prestamo.numero_control}.")
        if _guardar():
            flash("Devolución de NP registrada.", "success")
    else:
        flash("Indique quién devuelve y quién recibe.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


def _pdf_descarga(titulo, filas, nombre):
    archivo = BytesIO()
    doc = SimpleDocTemplate(archivo, pagesize=letter, topMargin=32, bottomMargin=32)
    estilos = getSampleStyleSheet()
    story = [Paragraph(escape(titulo), estilos["Title"]), Spacer(1, 14)]
    datos = []
    for etiqueta, valor in filas:
        datos.append([Paragraph(escape(str(etiqueta)), estilos["Normal"]),
                      Paragraph(escape(str(valor if valor is not None else "—")), estilos["Normal"])])
    tabla = Table(datos, colWidths=[180, 335], hAlign="LEFT")
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tabla)
    doc.build(story)
    archivo.seek(0)
    return send_file(archivo, mimetype="application/pdf", as_attachment=True, download_name=nombre)


@no_portadores_bp.route("/<int:np_id>/prestamos/<int:prestamo_id>/comprobante/pdf")
@login_required
def comprobante_pdf(np_id, prestamo_id):
    np = NoPortador.query.get_or_404(np_id)
    prestamo = PrestamoNP.query.filter_by(np_id=np_id, id=prestamo_id).first_or_404()
    return _pdf_descarga("SICODE-UCT / Comprobante de préstamo NP", [
        ("No. NP", np.numero_np), ("Código interno", np.codigo_interno),
        ("Número de control", prestamo.numero_control),
        ("Solicitante", prestamo.solicitante), ("Entrega", prestamo.persona_entrega),
        ("Recibe", prestamo.persona_recibe),
        ("Fecha de préstamo", prestamo.fecha_prestamo),
        ("Devolución estimada", prestamo.fecha_estimada_devolucion),
        ("Folios rectificados", np.folios_rectificados),
        ("Anexos rectificados", np.anexos_rectificados),
        ("Estado", prestamo.estado),
        ("Observaciones", prestamo.observaciones),
    ], f"prestamo_{prestamo.numero_control}.pdf")


@no_portadores_bp.route("/<int:np_id>/traslados/nuevo", methods=["POST"])
@login_required
def nuevo_traslado(np_id):
    _exigir_editor()
    np = NoPortador.query.get_or_404(np_id)
    form = TrasladoVirtualForm()
    if not np.activo or not np.expediente_fisico_registrado or not np.rectificacion_completa:
        flash("Debe registrar y rectificar el expediente físico NP antes del traslado virtual.", "warning")
    elif form.validate_on_submit():
        enlace = (form.enlace_corto.data or "").strip()
        url = urlparse(enlace)
        if url.scheme not in {"https", "http"} or not url.netloc:
            flash("El enlace de traslado debe comenzar con https:// o http://.", "danger")
        else:
            traslado = TrasladoVirtualNP(np_id=np.id,
                numero_constancia=f"TV-NP-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}",
                destinatario=form.destinatario.data.strip(), dependencia_destino=form.dependencia_destino.data,
                plataforma=form.plataforma.data, enlace_corto=enlace, asunto=form.asunto.data.strip(),
                observaciones=form.observaciones.data, creado_por_id=current_user.id)
            db.session.add(traslado)
            _auditar("TRASLADAR_VIRTUAL_NP", np, f"Constancia virtual NP {traslado.numero_constancia}.")
            if _guardar():
                flash("Traslado virtual NP registrado.", "success")
                return redirect(url_for(".traslado_pdf", np_id=np_id, traslado_id=traslado.id))
    else:
        flash("Complete los datos del traslado virtual.", "danger")
    return redirect(url_for(".detalle", np_id=np_id))


@no_portadores_bp.route("/<int:np_id>/traslados/<int:traslado_id>/constancia/pdf")
@login_required
def traslado_pdf(np_id, traslado_id):
    np = NoPortador.query.get_or_404(np_id)
    t = TrasladoVirtualNP.query.filter_by(np_id=np_id, id=traslado_id).first_or_404()
    return _pdf_descarga("SICODE-UCT / Constancia de traslado virtual NP", [
        ("No. NP", np.numero_np), ("Constancia", t.numero_constancia),
        ("Destinatario", t.destinatario), ("Dependencia", t.dependencia_destino),
        ("Plataforma", t.plataforma), ("Enlace registrado", t.enlace_corto),
        ("Asunto", t.asunto), ("Fecha", t.creado_en),
        ("Folios rectificados", np.folios_rectificados),
        ("Anexos rectificados", np.anexos_rectificados),
        ("Observaciones", t.observaciones),
    ], f"traslado_{t.numero_constancia}.pdf")


@no_portadores_bp.route("/<int:np_id>/ficha/pdf")
@login_required
def ficha_pdf(np_id):
    np = NoPortador.query.get_or_404(np_id)
    return _pdf_descarga("SICODE-UCT / Ficha de No Portador", [
        ("No. NP", np.numero_np), ("Código interno", np.codigo_interno),
        ("Nombre", np.nombre_referencia or f"{np.nombres or ''} {np.apellidos or ''}".strip()),
        ("Motivo de no instalación", np.motivo_no_instalacion),
        ("Fecha de no instalación", np.fecha_no_instalacion),
        ("Estado administrativo", np.estado_administrativo),
        ("Disponibilidad", np.disponibilidad),
        ("Folios rectificados", np.folios_rectificados),
        ("Anexos rectificados", np.anexos_rectificados),
    ], f"ficha_{np.numero_np}.pdf")


@no_portadores_bp.route("/exportar/excel")
@login_required
def exportar_excel():
    _exigir_editor()
    consulta = NoPortador.query.order_by(NoPortador.numero_np)
    wb = Workbook()
    ws = wb.active
    ws.title = "No Portadores"
    ws.append(["Número NP", "Código interno", "Nombre", "Motivo no instalación",
               "Fecha no instalación", "Estado", "Expediente físico", "Disponibilidad",
               "Folios rectificados", "Anexos rectificados", "Expediente OJ"])
    for np in consulta.all():
        ws.append([np.numero_np, np.codigo_interno, np.nombre_referencia or
                   f"{np.nombres or ''} {np.apellidos or ''}".strip(),
                   np.motivo_no_instalacion,
                   np.fecha_no_instalacion.isoformat() if np.fecha_no_instalacion else "",
                   np.estado_administrativo, "Sí" if np.expediente_fisico_registrado else "No",
                   np.disponibilidad, np.folios_rectificados, np.anexos_rectificados, np.expediente_oj])
    for celda in ws[1]:
        celda.font = Font(bold=True)
    for columna in ws.columns:
        letra = columna[0].column_letter
        ws.column_dimensions[letra].width = min(45, max(13, max(len(str(c.value or "")) for c in columna[:200]) + 3))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    salida = BytesIO()
    wb.save(salida)
    salida.seek(0)
    return send_file(salida, as_attachment=True, download_name="no_portadores.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
