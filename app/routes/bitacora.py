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
            evento.creado_en_guatemala.strftime("%d/%m/%Y %H:%M:%S") if evento.creado_en_guatemala else "",
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



@bitacora_bp.route("/bitacora/exportar/completo")
@login_required
def exportar_completo():
    """Exportación estadística íntegra de metadatos auditables; acceso exclusivo admin."""
    from collections import Counter
    from datetime import datetime
    from flask import abort
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from sqlalchemy.orm import selectinload
    import json
    import re

    if current_user.rol != Usuario.ROL_ADMINISTRADOR:
        abort(403)

    busqueda = request.args.get("q", "").strip()
    accion = request.args.get("accion", "").strip()
    modulo = request.args.get("modulo", "").strip()
    usuario = request.args.get("usuario", "").strip()

    # No exportamos claves, tokens, secretos ni contraseñas desde JSON históricos.
    secreto = re.compile(
        r"(password|passwd|contrase.na|clave_secreta|secret|token|authorization|"
        r"cookie|session|api[_-]?key|credential|credencial|password_hash)",
        re.IGNORECASE,
    )

    def seguro(valor):
        if isinstance(valor, dict):
            return {str(k): ("[REDACTADO]" if secreto.search(str(k)) else seguro(v))
                    for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [seguro(v) for v in valor]
        return valor

    def celda(valor):
        if valor is None:
            return ""
        if not isinstance(valor, (int, float, bool)):
            if isinstance(valor, (dict, list, tuple)):
                valor = json.dumps(seguro(valor), ensure_ascii=False, default=str, sort_keys=True)
            else:
                valor = str(valor)
            valor = ILLEGAL_CHARACTERS_RE.sub("", valor)
            # Impide ejecución de fórmulas al abrir Excel, incluso después de espacios.
            if valor.lstrip().startswith(("=", "+", "-", "@")):
                valor = "'" + valor
            return valor[:32767]
        return valor

    def fila(hoja, valores):
        hoja.append([celda(v) for v in valores])

    def hojas(nombre, encabezados):
        hoja = libro.create_sheet(nombre)
        fila(hoja, encabezados)
        hoja.freeze_panes = "A2"
        return hoja

    libro = Workbook(write_only=True)
    eventos_ws = hojas("Eventos completos", [
        "ID evento", "Fecha y hora Guatemala", "Fecha y hora UTC",
        "Usuario ID", "Usuario", "Nombre usuario", "Rol actual usuario",
        "Expediente ID", "No. SP", "Código interno", "Acción", "Módulo",
        "Entidad", "Entidad ID", "Descripción", "Motivo", "IP origen",
        "User-Agent", "Datos anteriores JSON", "Datos posteriores JSON",
    ])
    detalles_ws = hojas("Cambios estructurados", [
        "ID evento", "Origen", "Ruta de dato", "Valor registrado",
    ])
    acciones = Counter()
    modulos = Counter()
    usuarios = Counter()
    fechas = Counter()
    total = 0

    consulta = (
        _consulta_filtrada(busqueda, accion, modulo, usuario)
        .options(selectinload(Bitacora.usuario), selectinload(Bitacora.expediente))
        .order_by(Bitacora.creado_en.asc(), Bitacora.id.asc())
    )
    # Mantener consumo de memoria acotado y separar hojas al alcanzar el límite de Excel.
    numero_hoja_eventos = 1
    numero_hoja_detalles = 1
    filas_eventos = 0
    filas_detalles = 0

    def nuevo_detalle(evento_id, origen, ruta, dato):
        nonlocal detalles_ws, numero_hoja_detalles, filas_detalles
        if filas_detalles >= 1048575:
            numero_hoja_detalles += 1
            detalles_ws = hojas(f"Cambios {numero_hoja_detalles}", [
                "ID evento", "Origen", "Ruta de dato", "Valor registrado",
            ])
            filas_detalles = 0
        fila(detalles_ws, [evento_id, origen, ruta or "(valor)", dato])
        filas_detalles += 1

    # Reemplazar el escritor de detalle para admitir más de una hoja Excel.
    def expandir_detalles(evento_id, origen, valor):
        if valor is None:
            return
        pila = [("", seguro(valor))]
        while pila:
            ruta, dato = pila.pop()
            if isinstance(dato, dict):
                for clave, item in reversed(list(dato.items())):
                    pila.append((f"{ruta}.{clave}" if ruta else str(clave), item))
            elif isinstance(dato, list):
                for indice in range(len(dato) - 1, -1, -1):
                    pila.append((f"{ruta}[{indice}]", dato[indice]))
            else:
                nuevo_detalle(evento_id, origen, ruta, dato)

    for evento in consulta.yield_per(500):
        if filas_eventos >= 1048575:
            numero_hoja_eventos += 1
            eventos_ws = hojas(f"Eventos {numero_hoja_eventos}", [
                "ID evento", "Fecha y hora Guatemala", "Fecha y hora UTC",
                "Usuario ID", "Usuario", "Nombre usuario", "Rol actual usuario",
                "Expediente ID", "No. SP", "Código interno", "Acción", "Módulo",
                "Entidad", "Entidad ID", "Descripción", "Motivo", "IP origen",
                "User-Agent", "Datos anteriores JSON", "Datos posteriores JSON",
            ])
            filas_eventos = 0
        actor = evento.usuario
        expediente = evento.expediente
        local = evento.creado_en_guatemala
        fila(eventos_ws, [
            evento.id, local.strftime("%Y-%m-%d %H:%M:%S") if local else "",
            evento.creado_en.isoformat(sep=" ") if evento.creado_en else "",
            evento.usuario_id, actor.usuario if actor else "", actor.nombre if actor else "",
            actor.rol if actor else "", evento.expediente_id,
            expediente.no_sp if expediente else "",
            expediente.codigo_interno if expediente else "",
            evento.accion, evento.modulo, evento.entidad, evento.entidad_id,
            evento.descripcion, evento.motivo, evento.ip_origen, evento.user_agent,
            seguro(evento.datos_anteriores), seguro(evento.datos_posteriores),
        ])
        filas_eventos += 1
        total += 1
        acciones[evento.accion or "(sin acción)"] += 1
        modulos[evento.modulo or "(sin módulo)"] += 1
        usuarios[actor.usuario if actor else "Sistema / Sin usuario"] += 1
        fechas[local.strftime("%Y-%m-%d") if local else "(sin fecha)"] += 1
        expandir_detalles(evento.id, "Anterior", evento.datos_anteriores)
        expandir_detalles(evento.id, "Posterior", evento.datos_posteriores)

    resumen = hojas("Resumen", ["Concepto", "Valor", "Total"])
    fila(resumen, ["Total de eventos", "", total])
    for titulo, conteos in (
        ("Acción", acciones), ("Módulo", modulos),
        ("Usuario", usuarios), ("Fecha Guatemala", fechas),
    ):
        for clave, cantidad in sorted(conteos.items(), key=lambda par: (-par[1], par[0])):
            fila(resumen, [titulo, clave, cantidad])
    parametros = hojas("Parámetros", ["Parámetro", "Valor"])
    for clave, valor in (
        ("Exportado por", current_user.usuario),
        ("Generado Guatemala", datetime.now().astimezone().isoformat()),
        ("Búsqueda", busqueda), ("Acción", accion),
        ("Módulo", modulo), ("Usuario", usuario),
        ("Total eventos exportados", total),
        ("Nota", "Solo metadatos existentes en bitácora. Valores sensibles redactados."),
    ):
        fila(parametros, [clave, valor])

    archivo = BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    registrar_bitacora(
        accion="EXPORTAR_BITACORA_COMPLETA_ADMIN",
        modulo="Reportes",
        descripcion=f"Exportación completa de bitácora por administrador. Eventos: {total}.",
        usuario_id=current_user.id,
        datos_posteriores={
            "total_eventos": total,
            "filtros": {"q": busqueda, "accion": accion, "modulo": modulo, "usuario": usuario},
        },
    )
    return send_file(
        archivo,
        as_attachment=True,
        download_name=f"bitacora_completa_sicode_uct_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
