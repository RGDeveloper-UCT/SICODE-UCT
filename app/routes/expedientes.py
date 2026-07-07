from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app import db
from app.forms.expediente_form import ExpedienteForm
from app.models.expediente import Expediente
from app.models.ubicacion import UbicacionFisica
from app.services.bitacora_service import registrar_bitacora

expedientes_bp = Blueprint("expedientes", __name__)

@expedientes_bp.route("/expedientes")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_activo = request.args.get("activo", "").strip()
    filtro_estado_admin = request.args.get("estado_administrativo", "").strip()
    filtro_estado_fisico = request.args.get("estado_fisico_documental", "").strip()

    consulta = Expediente.query

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
            )
        )

    if filtro_activo == "si":
        consulta = consulta.filter(Expediente.activo == True)
    elif filtro_activo == "no":
        consulta = consulta.filter(Expediente.activo == False)

    if filtro_estado_admin:
        consulta = consulta.filter(Expediente.estado_administrativo == filtro_estado_admin)

    if filtro_estado_fisico:
        consulta = consulta.filter(Expediente.estado_fisico_documental == filtro_estado_fisico)

    expedientes = consulta.order_by(Expediente.creado_en.desc()).all()

    estados_administrativos = [
        "Activo",
        "En revisión",
        "En préstamo",
        "Devuelto",
        "Cerrado",
    ]

    estados_fisicos = [
        "Pendiente de verificación",
        "Verificado",
        "Con observaciones",
        "Incompleto",
        "No localizado",
    ]

    return render_template(
        "expedientes/listado.html",
        expedientes=expedientes,
        busqueda=busqueda,
        filtro_activo=filtro_activo,
        filtro_estado_admin=filtro_estado_admin,
        filtro_estado_fisico=filtro_estado_fisico,
        estados_administrativos=estados_administrativos,
        estados_fisicos=estados_fisicos,
    )

@expedientes_bp.route("/expedientes/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    form = ExpedienteForm()

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = Expediente.query.filter_by(codigo_interno=codigo_interno).first()
        existe_sp = Expediente.query.filter_by(no_sp=no_sp).first()

        if existe_codigo:
            flash("Ya existe un expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        if existe_sp:
            flash("Ya existe un expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

        expediente = Expediente(
            codigo_interno=codigo_interno,
            no_sp=no_sp,
            nombre_referencia=form.nombre_referencia.data.strip() if form.nombre_referencia.data else None,
            estado_administrativo=form.estado_administrativo.data,
            estado_fisico_documental=form.estado_fisico_documental.data,
            observaciones=form.observaciones.data,
            activo=True,
        )

        db.session.add(expediente)
        db.session.flush()

        ubicacion = UbicacionFisica(
            expediente_id=expediente.id,
            archivador=form.archivador.data,
            sicoin=form.sicoin.data,
            estante=form.estante.data,
            caja=form.caja.data,
            modulo=form.modulo.data,
            posicion=form.posicion.data,
            observaciones=form.observaciones.data,
        )

        db.session.add(ubicacion)
        db.session.commit()

        registrar_bitacora(
            accion="CREAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se creó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Expediente creado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    return render_template("expedientes/formulario.html", form=form, modo="Nuevo")

@expedientes_bp.route("/expedientes/<int:expediente_id>")
@login_required
def detalle(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    return render_template(
        "expedientes/detalle.html",
        expediente=expediente,
        ubicacion=ubicacion,
    )

@expedientes_bp.route("/expedientes/<int:expediente_id>/editar", methods=["GET", "POST"])
@login_required
def editar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    ubicacion = (
        UbicacionFisica.query
        .filter_by(expediente_id=expediente.id)
        .order_by(UbicacionFisica.creado_en.desc())
        .first()
    )

    form = ExpedienteForm()
    form.submit.label.text = "Actualizar expediente"

    if form.validate_on_submit():
        codigo_interno = form.codigo_interno.data.strip()
        no_sp = form.no_sp.data.strip()

        existe_codigo = (
            Expediente.query
            .filter(Expediente.codigo_interno == codigo_interno, Expediente.id != expediente.id)
            .first()
        )

        existe_sp = (
            Expediente.query
            .filter(Expediente.no_sp == no_sp, Expediente.id != expediente.id)
            .first()
        )

        if existe_codigo:
            flash("Ya existe otro expediente con ese código interno.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        if existe_sp:
            flash("Ya existe otro expediente con ese No. de SP.", "danger")
            return render_template("expedientes/formulario.html", form=form, modo="Editar")

        expediente.codigo_interno = codigo_interno
        expediente.no_sp = no_sp
        expediente.nombre_referencia = form.nombre_referencia.data.strip() if form.nombre_referencia.data else None
        expediente.estado_administrativo = form.estado_administrativo.data
        expediente.estado_fisico_documental = form.estado_fisico_documental.data
        expediente.observaciones = form.observaciones.data

        if not ubicacion:
            ubicacion = UbicacionFisica(expediente_id=expediente.id)
            db.session.add(ubicacion)

        ubicacion.archivador = form.archivador.data
        ubicacion.sicoin = form.sicoin.data
        ubicacion.estante = form.estante.data
        ubicacion.caja = form.caja.data
        ubicacion.modulo = form.modulo.data
        ubicacion.posicion = form.posicion.data
        ubicacion.observaciones = form.observaciones.data

        db.session.commit()

        registrar_bitacora(
            accion="EDITAR_EXPEDIENTE",
            modulo="Expedientes",
            descripcion=f"Se actualizó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
            usuario_id=current_user.id,
            expediente_id=expediente.id,
        )

        flash("Expediente actualizado correctamente.", "success")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    if request.method == "GET":
        form.codigo_interno.data = expediente.codigo_interno
        form.no_sp.data = expediente.no_sp
        form.nombre_referencia.data = expediente.nombre_referencia
        form.estado_administrativo.data = expediente.estado_administrativo
        form.estado_fisico_documental.data = expediente.estado_fisico_documental
        form.observaciones.data = expediente.observaciones

        if ubicacion:
            form.archivador.data = ubicacion.archivador
            form.sicoin.data = ubicacion.sicoin
            form.estante.data = ubicacion.estante
            form.caja.data = ubicacion.caja
            form.modulo.data = ubicacion.modulo
            form.posicion.data = ubicacion.posicion

    return render_template("expedientes/formulario.html", form=form, modo="Editar")

@expedientes_bp.route("/expedientes/<int:expediente_id>/desactivar", methods=["POST"])
@login_required
def desactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.activo:
        flash("El expediente ya se encuentra desactivado.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = False
    db.session.commit()

    registrar_bitacora(
        accion="DESACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se desactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente desactivado correctamente. El registro se conserva para trazabilidad.", "info")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

@expedientes_bp.route("/expedientes/<int:expediente_id>/reactivar", methods=["POST"])
@login_required
def reactivar(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if expediente.activo:
        flash("El expediente ya se encuentra activo.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    expediente.activo = True
    db.session.commit()

    registrar_bitacora(
        accion="REACTIVAR_EXPEDIENTE",
        modulo="Expedientes",
        descripcion=f"Se reactivó el expediente con No. de SP {expediente.no_sp} y código interno {expediente.codigo_interno}.",
        usuario_id=current_user.id,
        expediente_id=expediente.id,
    )

    flash("Expediente reactivado correctamente.", "success")
    return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

@expedientes_bp.route("/expedientes/exportar/excel")
@login_required
def exportar_excel():
    busqueda = request.args.get("q", "").strip()
    filtro_activo = request.args.get("activo", "").strip()
    filtro_estado_admin = request.args.get("estado_administrativo", "").strip()
    filtro_estado_fisico = request.args.get("estado_fisico_documental", "").strip()

    consulta = Expediente.query

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                Expediente.nombre_referencia.ilike(filtro),
            )
        )

    if filtro_activo == "si":
        consulta = consulta.filter(Expediente.activo == True)
    elif filtro_activo == "no":
        consulta = consulta.filter(Expediente.activo == False)

    if filtro_estado_admin:
        consulta = consulta.filter(Expediente.estado_administrativo == filtro_estado_admin)

    if filtro_estado_fisico:
        consulta = consulta.filter(Expediente.estado_fisico_documental == filtro_estado_fisico)

    expedientes = consulta.order_by(Expediente.creado_en.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expedientes"

    encabezados = [
        "ID",
        "Código interno",
        "No. de SP",
        "Nombre referencia",
        "Estado administrativo",
        "Estado físico/documental",
        "Activo",
        "Archivador",
        "SICOIN",
        "Estante",
        "Caja",
        "Módulo",
        "Posición",
        "Observaciones",
        "Fecha creación",
    ]

    ws.append(encabezados)

    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for expediente in expedientes:
        ubicacion = (
            UbicacionFisica.query
            .filter_by(expediente_id=expediente.id)
            .order_by(UbicacionFisica.creado_en.desc())
            .first()
        )

        ws.append([
            expediente.id,
            expediente.codigo_interno,
            expediente.no_sp,
            expediente.nombre_referencia or "",
            expediente.estado_administrativo,
            expediente.estado_fisico_documental,
            "Sí" if expediente.activo else "No",
            ubicacion.archivador if ubicacion else "",
            ubicacion.sicoin if ubicacion else "",
            ubicacion.estante if ubicacion else "",
            ubicacion.caja if ubicacion else "",
            ubicacion.modulo if ubicacion else "",
            ubicacion.posicion if ubicacion else "",
            expediente.observaciones or "",
            expediente.creado_en.strftime("%d/%m/%Y %H:%M") if expediente.creado_en else "",
        ])

    anchos = {
        "A": 8,
        "B": 22,
        "C": 16,
        "D": 28,
        "E": 24,
        "F": 28,
        "G": 12,
        "H": 16,
        "I": 16,
        "J": 16,
        "K": 16,
        "L": 16,
        "M": 16,
        "N": 40,
        "O": 22,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    registrar_bitacora(
        accion="EXPORTAR_EXPEDIENTES_EXCEL",
        modulo="Reportes",
        descripcion=f"Se exportó listado de expedientes a Excel. Registros exportados: {len(expedientes)}.",
        usuario_id=current_user.id,
    )

    archivo_excel = BytesIO()
    wb.save(archivo_excel)
    archivo_excel.seek(0)

    return send_file(
        archivo_excel,
        as_attachment=True,
        download_name="reporte_expedientes_sicode_uct.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
