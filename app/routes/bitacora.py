from io import BytesIO

from flask import Blueprint, render_template, request, send_file
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from sqlalchemy import or_

from app.models.bitacora import Bitacora
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.services.bitacora_service import registrar_bitacora


bitacora_bp = Blueprint("bitacora", __name__)


def _consulta_filtrada(busqueda="", accion="", modulo="", usuario=""):
    consulta = (
        Bitacora.query
        .outerjoin(Usuario, Bitacora.usuario_id == Usuario.id)
        .outerjoin(Expediente, Bitacora.expediente_id == Expediente.id)
    )

    if busqueda:
        filtro = f"%{busqueda}%"
        consulta = consulta.filter(or_(
            Bitacora.descripcion.ilike(filtro),
            Bitacora.accion.ilike(filtro),
            Bitacora.modulo.ilike(filtro),
            Bitacora.entidad.ilike(filtro),
            Bitacora.entidad_id.ilike(filtro),
            Usuario.usuario.ilike(filtro),
            Usuario.nombre.ilike(filtro),
            Expediente.no_sp.ilike(filtro),
            Expediente.codigo_interno.ilike(filtro),
        ))

    if accion:
        consulta = consulta.filter(Bitacora.accion == accion)
    if modulo:
        consulta = consulta.filter(Bitacora.modulo == modulo)
    if usuario:
        consulta = consulta.filter(Usuario.usuario == usuario)
    return consulta


@bitacora_bp.route("/bitacora")
@login_required
def listado():
    busqueda = request.args.get("q", "").strip()
    filtro_accion = request.args.get("accion", "").strip()
    filtro_modulo = request.args.get("modulo", "").strip()
    filtro_usuario = request.args.get("usuario", "").strip()
    pagina = request.args.get("page", 1, type=int)

    paginacion = (
        _consulta_filtrada(busqueda, filtro_accion, filtro_modulo, filtro_usuario)
        .order_by(Bitacora.creado_en.desc())
        .paginate(page=max(pagina, 1), per_page=100, error_out=False)
    )

    acciones = [valor[0] for valor in Bitacora.query.with_entities(Bitacora.accion).distinct().order_by(Bitacora.accion.asc()).all()]
    modulos = [valor[0] for valor in Bitacora.query.with_entities(Bitacora.modulo).distinct().order_by(Bitacora.modulo.asc()).all()]
    usuarios = Usuario.query.order_by(Usuario.nombre.asc()).all()

    return render_template(
        "bitacora/listado.html",
        eventos=paginacion.items,
        paginacion=paginacion,
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

    eventos = (
        _consulta_filtrada(busqueda, accion, modulo, usuario)
        .order_by(Bitacora.creado_en.desc())
        .limit(5000)
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Bitacora"
    encabezados = [
        "ID", "Fecha", "Usuario", "Nombre usuario", "Acción", "Módulo",
        "Entidad", "Entidad ID", "Expediente No. SP", "Código interno",
        "IP origen", "User-Agent", "Motivo", "Descripción",
        "Datos anteriores", "Datos posteriores",
    ]
    ws.append(encabezados)

    for celda in ws[1]:
        celda.font = Font(bold=True)
        celda.alignment = Alignment(horizontal="center")

    for evento in eventos:
        usuario_evento = evento.usuario
        expediente_evento = evento.expediente
        ws.append([
            evento.id,
            evento.creado_en.strftime("%d/%m/%Y %H:%M:%S") if evento.creado_en else "",
            usuario_evento.usuario if usuario_evento else "Sistema / Sin usuario",
            usuario_evento.nombre if usuario_evento else "",
            evento.accion,
            evento.modulo,
            evento.entidad or "",
            evento.entidad_id or "",
            expediente_evento.no_sp if expediente_evento else "",
            expediente_evento.codigo_interno if expediente_evento else "",
            evento.ip_origen or "",
            evento.user_agent or "",
            evento.motivo or "",
            evento.descripcion or "",
            str(evento.datos_anteriores or ""),
            str(evento.datos_posteriores or ""),
        ])

    for columna, ancho in {
        "A": 8, "B": 22, "C": 20, "D": 26, "E": 32, "F": 22,
        "G": 22, "H": 14, "I": 18, "J": 24, "K": 18, "L": 45,
        "M": 35, "N": 70, "O": 60, "P": 60,
    }.items():
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
