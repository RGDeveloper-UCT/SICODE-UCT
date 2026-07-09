from io import BytesIO
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app.models.bitacora import Bitacora
from app.models.usuario import Usuario
from app.models.expediente import Expediente

bitacora_bp = Blueprint("bitacora", __name__)

@bitacora_bp.route("/bitacora")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_accion = request.args.get("accion", "").strip()
    filtro_modulo = request.args.get("modulo", "").strip()
    filtro_usuario = request.args.get("usuario", "").strip()

    consulta = (
        Bitacora.query
        .outerjoin(Usuario, Bitacora.usuario_id == Usuario.id)
        .outerjoin(Expediente, Bitacora.expediente_id == Expediente.id)
    )

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Bitacora.descripcion.ilike(filtro),
                Bitacora.accion.ilike(filtro),
                Bitacora.modulo.ilike(filtro),
                Usuario.usuario.ilike(filtro),
                Usuario.nombre.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
            )
        )

    if filtro_accion:
        consulta = consulta.filter(Bitacora.accion == filtro_accion)

    if filtro_modulo:
        consulta = consulta.filter(Bitacora.modulo == filtro_modulo)

    if filtro_usuario:
        consulta = consulta.filter(Usuario.usuario == filtro_usuario)

    eventos = consulta.order_by(Bitacora.creado_en.desc()).limit(100).all()

    acciones = [
        accion[0]
        for accion in Bitacora.query.with_entities(Bitacora.accion)
        .distinct()
        .order_by(Bitacora.accion.asc())
        .all()
    ]

    modulos = [
        modulo[0]
        for modulo in Bitacora.query.with_entities(Bitacora.modulo)
        .distinct()
        .order_by(Bitacora.modulo.asc())
        .all()
    ]

    usuarios = Usuario.query.order_by(Usuario.nombre.asc()).all()

    return render_template(
        "bitacora/listado.html",
        eventos=eventos,
        busqueda=busqueda,
        filtro_accion=filtro_accion,
        filtro_modulo=filtro_modulo,
        filtro_usuario=filtro_usuario,
        acciones=acciones,
        modulos=modulos,
        usuarios=usuarios,
    )


@bitacora_bp.route("/bitacora/exportar/excel")
@login_required
def exportar_excel():
    accion = request.args.get("accion", "").strip()
    modulo = request.args.get("modulo", "").strip()
    usuario = request.args.get("usuario", "").strip()
    busqueda = request.args.get("q", "").strip()

    consulta = Bitacora.query.outerjoin(Usuario).outerjoin(Expediente)

    if accion:
        consulta = consulta.filter(Bitacora.accion.ilike(f"%{accion}%"))

    if modulo:
        consulta = consulta.filter(Bitacora.modulo.ilike(f"%{modulo}%"))

    if usuario:
        consulta = consulta.filter(Usuario.usuario.ilike(f"%{usuario}%"))

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Bitacora.descripcion.ilike(filtro),
                Bitacora.accion.ilike(filtro),
                Bitacora.modulo.ilike(filtro),
                Usuario.nombre.ilike(filtro),
                Usuario.usuario.ilike(filtro),
                Expediente.no_sp.ilike(filtro),
                Expediente.codigo_interno.ilike(filtro),
            )
        )

    eventos = consulta.order_by(Bitacora.creado_en.desc()).limit(5000).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Bitacora"

    encabezados = [
        "ID",
        "Fecha",
        "Usuario",
        "Nombre usuario",
        "Acción",
        "Módulo",
        "Expediente No. SP",
        "Código interno",
        "IP origen",
        "Descripción",
    ]

    ws.append(encabezados)

    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for evento in eventos:
        usuario_evento = evento.usuario if evento.usuario else None
        expediente_evento = evento.expediente if evento.expediente else None

        ws.append([
            evento.id,
            evento.creado_en.strftime("%d/%m/%Y %H:%M:%S") if evento.creado_en else "",
            usuario_evento.usuario if usuario_evento else "Sistema / Sin usuario",
            usuario_evento.nombre if usuario_evento else "",
            evento.accion,
            evento.modulo,
            expediente_evento.no_sp if expediente_evento else "",
            expediente_evento.codigo_interno if expediente_evento else "",
            evento.ip_origen or "",
            evento.descripcion or "",
        ])

    anchos = {
        "A": 8,
        "B": 22,
        "C": 22,
        "D": 28,
        "E": 32,
        "F": 22,
        "G": 18,
        "H": 24,
        "I": 18,
        "J": 80,
    }

    for columna, ancho in anchos.items():
        ws.column_dimensions[columna].width = ancho

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    registrar_bitacora(
        accion="EXPORTAR_BITACORA_EXCEL",
        modulo="Reportes",
        descripcion=f"Se exportó la bitácora a Excel. Registros exportados: {len(eventos)}.",
        usuario_id=current_user.id,
    )

    archivo_excel = BytesIO()
    wb.save(archivo_excel)
    archivo_excel.seek(0)

    return send_file(
        archivo_excel,
        as_attachment=True,
        download_name="reporte_bitacora_sicode_uct.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
