from io import BytesIO
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app import db
from app.models.alerta import Alerta
from app.models.expediente import Expediente
from app.models.documento_expediente import DocumentoExpediente
from app.services.bitacora_service import registrar_bitacora

alertas_bp = Blueprint("alertas", __name__)

@alertas_bp.route("/alertas")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()
    filtro_gravedad = request.args.get("gravedad", "").strip()
    filtro_tipo = request.args.get("tipo", "").strip()

    consulta = (
        Alerta.query
        .join(Expediente, Alerta.expediente_id == Expediente.id)
        .outerjoin(DocumentoExpediente, Alerta.documento_id == DocumentoExpediente.id)
    )

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Alerta.titulo.ilike(filtro),
                Alerta.descripcion.ilike(filtro),
                Alerta.tipo_alerta.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                DocumentoExpediente.nombre_documento.ilike(filtro),
            )
        )

    if filtro_estado:
        consulta = consulta.filter(Alerta.estado == filtro_estado)

    if filtro_gravedad:
        consulta = consulta.filter(Alerta.gravedad == filtro_gravedad)

    if filtro_tipo:
        consulta = consulta.filter(Alerta.tipo_alerta == filtro_tipo)

    alertas = consulta.order_by(Alerta.creado_en.desc()).limit(150).all()

    estados = ["Abierta", "En revisión", "Corregida", "Cerrada"]
    gravedades = ["Alta", "Media", "Baja"]

    tipos = [
        tipo[0]
        for tipo in Alerta.query.with_entities(Alerta.tipo_alerta)
        .distinct()
        .order_by(Alerta.tipo_alerta.asc())
        .all()
    ]

    return render_template(
        "alertas/listado.html",
        alertas=alertas,
        busqueda=busqueda,
        filtro_estado=filtro_estado,
        filtro_gravedad=filtro_gravedad,
        filtro_tipo=filtro_tipo,
        estados=estados,
        gravedades=gravedades,
        tipos=tipos,
    )

@alertas_bp.route("/alertas/<int:alerta_id>/estado/<nuevo_estado>", methods=["POST"])
@login_required
def cambiar_estado(alerta_id, nuevo_estado):
    alerta = Alerta.query.get_or_404(alerta_id)

    estados_permitidos = ["Abierta", "En revisión", "Corregida", "Cerrada"]

    if nuevo_estado not in estados_permitidos:
        flash("Estado de alerta no permitido.", "danger")
        return redirect(url_for("alertas.listado"))

    estado_anterior = alerta.estado
    alerta.estado = nuevo_estado

    if nuevo_estado == "Cerrada":
        alerta.cerrado_en = datetime.utcnow()
        alerta.cerrada_por_id = current_user.id
    else:
        alerta.cerrado_en = None
        alerta.cerrada_por_id = None

    db.session.commit()

    registrar_bitacora(
        accion="CAMBIAR_ESTADO_ALERTA",
        modulo="Alertas",
        descripcion=f"Se cambió la alerta '{alerta.titulo}' de '{estado_anterior}' a '{nuevo_estado}'.",
        usuario_id=current_user.id,
        expediente_id=alerta.expediente_id,
    )

    flash("Estado de alerta actualizado correctamente.", "success")
    return redirect(url_for("alertas.listado"))


@alertas_bp.route("/alertas/exportar/excel")
@login_required
def exportar_excel():
    busqueda = request.args.get("q", "").strip()
    filtro_estado = request.args.get("estado", "").strip()
    filtro_gravedad = request.args.get("gravedad", "").strip()
    filtro_tipo = request.args.get("tipo", "").strip()

    consulta = Alerta.query.join(Expediente).outerjoin(DocumentoExpediente)

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Alerta.titulo.ilike(filtro),
                Alerta.descripcion.ilike(filtro),
                Alerta.tipo_alerta.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
                DocumentoExpediente.nombre_documento.ilike(filtro),
            )
        )

    if filtro_estado:
        consulta = consulta.filter(Alerta.estado == filtro_estado)

    if filtro_gravedad:
        consulta = consulta.filter(Alerta.gravedad == filtro_gravedad)

    if filtro_tipo:
        consulta = consulta.filter(Alerta.tipo_alerta == filtro_tipo)

    alertas = consulta.order_by(Alerta.creado_en.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Alertas"

    encabezados = [
        "ID",
        "Fecha creación",
        "Expediente No. SP",
        "Código interno",
        "Documento relacionado",
        "Tipo alerta",
        "Título",
        "Descripción",
        "Gravedad",
        "Estado",
        "Origen",
        "Fecha cierre",
        "Creada por",
        "Cerrada por",
    ]

    ws.append(encabezados)

    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for alerta in alertas:
        expediente = alerta.expediente
        documento = alerta.documento if alerta.documento else None
        creada_por = alerta.creada_por if alerta.creada_por else None
        cerrada_por = alerta.cerrada_por if alerta.cerrada_por else None

        ws.append([
            alerta.id,
            alerta.creado_en.strftime("%d/%m/%Y %H:%M:%S") if alerta.creado_en else "",
            expediente.no_sp if expediente else "",
            expediente.codigo_interno if expediente else "",
            documento.nombre_documento if documento else "",
            alerta.tipo_alerta,
            alerta.titulo,
            alerta.descripcion or "",
            alerta.gravedad,
            alerta.estado,
            alerta.origen,
            alerta.cerrado_en.strftime("%d/%m/%Y %H:%M:%S") if alerta.cerrado_en else "",
            creada_por.usuario if creada_por else "",
            cerrada_por.usuario if cerrada_por else "",
        ])

    anchos = {
        "A": 8,
        "B": 22,
        "C": 18,
        "D": 24,
        "E": 32,
        "F": 28,
        "G": 40,
        "H": 70,
        "I": 14,
        "J": 16,
        "K": 18,
        "L": 22,
        "M": 18,
        "N": 18,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    registrar_bitacora(
        accion="EXPORTAR_ALERTAS_EXCEL",
        modulo="Reportes",
        descripcion=f"Se exportó listado de alertas a Excel. Registros exportados: {len(alertas)}.",
        usuario_id=current_user.id,
    )

    archivo_excel = BytesIO()
    wb.save(archivo_excel)
    archivo_excel.seek(0)

    return send_file(
        archivo_excel,
        as_attachment=True,
        download_name="reporte_alertas_sicode_uct.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
