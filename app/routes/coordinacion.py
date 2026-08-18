from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app import db
from app.forms.coordinacion_form import (
    ActividadForm,
    AnexoForm,
    ConfirmarImportacionForm,
    DocumentoEmitidoForm,
    ImportarCoordinacionForm,
    MonitoreoForm,
    MovimientoForm,
    PagoForm,
    RemisionExpedienteForm,
    RemisionForm,
)
from app.models.coordinacion import (
    ActividadCoordinacion,
    AnexoCoordinacion,
    DocumentoEmitido,
    MovimientoDispositivo,
    PagoCoordinacion,
    RegistroCoordinacion,
    RemisionCoordinacion,
    RemisionExpediente,
    ReporteMonitoreo,
)
from app.models.expediente import Expediente
from app.security import admin_required
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import determinar_estado, resolver_expediente
from app.services.importacion_coordinacion_service import ImportadorCoordinacion


coordinacion_bp = Blueprint("coordinacion", __name__, url_prefix="/coordinacion")

TIPOS_REGISTRO = {
    "pago": {"codigo": "PAGO", "titulo": "Pago", "descripcion": "Pagos recibidos y asociados al SP correspondiente."},
    "instalacion": {"codigo": "INSTALACION", "titulo": "Instalación", "descripcion": "Recepción y control administrativo de nuevas instalaciones."},
    "desinstalacion": {"codigo": "DESINSTALACION", "titulo": "Desinstalación", "descripcion": "Desinstalaciones recibidas y su control administrativo."},
    "anexo": {"codigo": "ANEXO", "titulo": "Anexo", "descripcion": "Anexos recibidos, foliación y estado de escaneo."},
    "monitoreo": {"codigo": "MONITOREO", "titulo": "Reporte de monitoreo", "descripcion": "Reportes remitidos por el Centro de Control y Monitoreo."},
    "documento-emitido": {"codigo": "DOCUMENTO_EMITIDO", "titulo": "Documento emitido", "descripcion": "Documentos generados y firmados por la Coordinación."},
    "actividad": {"codigo": "ACTIVIDAD", "titulo": "Actividad", "descripcion": "Actividades realizadas por el personal de la Coordinación."},
    "remision": {"codigo": "REMISION", "titulo": "Remisión de expediente", "descripcion": "Expedientes remitidos a Archivo/Bodega MINGOB u otro destino."},
}

CATALOGOS = {
    "tipos_anexo": ["REEMPLAZO", "MOVILIZACION", "AMPLIACION ZONA", "EXONERACION", "PRORROGA", "ZONA DE INCLUSION", "CARGADOR", "CORREA", "CARGADOR Y CORREA", "DCT, CARGADOR, CORREA", "2 CARGADORES Y CORREA", "DOS CARGADORES", "CAMBIO JUZGADO"],
    "tipos_actividad": ["DIARIA", "SOPORTE", "ESTADISTICA", "PAGOS", "REUNION", "APOYO", "TAREA", "VERIFICACION", "CAPACITACION", "CERT"],
    "tipos_evento": ["Prohibido acercarse", "Salida de zona de inclusión", "Salida", "Apertura", "Zona de inclusión", "Zona de exclusión", "Victim Proximity", "Seguimiento de proximidad", "Batería baja 30%", "Batería baja 12%", "No comunicación", "Ingreso prevención", "No aplica"],
    "destinos": ["Archivo/Bodega MINGOB", "Inspectoría MINGOB", "Dirección UCT", "Subdirección UCT", "Otra coordinación", "Otra institución"],
    "areas_apoyo": ["Monitoreo", "Analista de Riesgo", "Dirección", "Subdirección", "Administración", "Otra coordinación"],
}

TIPOS_ENTRANTES = {"PAGO", "INSTALACION", "DESINSTALACION", "ANEXO", "MONITOREO"}


def _sp_opciones():
    return Expediente.query.filter_by(activo=True).order_by(Expediente.no_sp.asc()).all()


def _limpiar(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def _crear_base(tipo, no_sp=None, rc=None, providencia=None, fecha=None, observaciones=None, campos_clave=None):
    expediente, no_sp_norm = resolver_expediente(no_sp)
    estado = determinar_estado(expediente, no_sp_norm, campos_clave=campos_clave)

    # Los formularios entrantes comparten estos nombres. Se capturan aquí una
    # sola vez para que "Recepción" sea una capacidad transversal de
    # Coordinación y no otro panel duplicado.
    persona_entrega = _limpiar(request.form.get("persona_entrega")) if tipo in TIPOS_ENTRANTES else None
    folios_recepcion = _limpiar(request.form.get("folios")) if tipo in TIPOS_ENTRANTES else None

    registro = RegistroCoordinacion(
        tipo=tipo,
        expediente_id=expediente.id if expediente else None,
        no_sp_referencia=no_sp_norm,
        rc=_limpiar(rc),
        providencia=_limpiar(providencia),
        fecha_recepcion=fecha,
        persona_entrega=persona_entrega,
        folios_recepcion=folios_recepcion,
        usuario_id=current_user.id,
        usuario_origen=current_user.nombre,
        estado=estado,
        observaciones=observaciones,
        origen_registro="MANUAL",
    )
    db.session.add(registro)
    db.session.flush()
    return registro


def _registrar_bitacora_nuevo(registro, etiqueta):
    registrar_bitacora(
        accion=f"REGISTRAR_{registro.tipo}",
        modulo="Coordinación",
        descripcion=(
            f"Se registró {etiqueta}. SP: {registro.no_sp_referencia or 'Sin SP'}. "
            f"Recibe: {registro.usuario_origen or current_user.nombre}. "
            f"Entrega/remite: {registro.persona_entrega or 'No consignado'}. Estado: {registro.estado}."
        ),
        usuario_id=current_user.id,
        expediente_id=registro.expediente_id,
        entidad="RegistroCoordinacion",
        entidad_id=registro.id,
        datos_posteriores={
            "tipo": registro.tipo,
            "sp": registro.no_sp_referencia,
            "rc": registro.rc,
            "providencia": registro.providencia,
            "persona_entrega": registro.persona_entrega,
            "folios_recepcion": registro.folios_recepcion,
            "estado": registro.estado,
        },
    )


def _recalcular_estado_remision(remision):
    detalles = RemisionExpediente.query.filter_by(remision_id=remision.id).all()
    if not detalles:
        remision.registro.estado = "Información pendiente"
    elif any(detalle.expediente_id is None for detalle in detalles):
        remision.registro.estado = "Pendiente de vincular"
    else:
        remision.registro.estado = "Completo"


@coordinacion_bp.route("")
@coordinacion_bp.route("/")
@login_required
def inicio():
    conteos = dict(
        db.session.query(RegistroCoordinacion.tipo, func.count(RegistroCoordinacion.id))
        .group_by(RegistroCoordinacion.tipo)
        .all()
    )
    pendientes = RegistroCoordinacion.query.filter(RegistroCoordinacion.estado != "Completo").count()
    recientes = RegistroCoordinacion.query.order_by(RegistroCoordinacion.creado_en.desc()).limit(10).all()
    return render_template(
        "coordinacion/inicio.html",
        tipos_registro=TIPOS_REGISTRO,
        conteos=conteos,
        pendientes=pendientes,
        recientes=recientes,
    )


@coordinacion_bp.route("/registros")
@login_required
def listado():
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    estado = request.args.get("estado", "").strip()
    pagina = request.args.get("page", 1, type=int)

    consulta = RegistroCoordinacion.query
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(or_(
            RegistroCoordinacion.no_sp_referencia.ilike(patron),
            RegistroCoordinacion.rc.ilike(patron),
            RegistroCoordinacion.providencia.ilike(patron),
            RegistroCoordinacion.persona_entrega.ilike(patron),
            RegistroCoordinacion.observaciones.ilike(patron),
        ))
    if tipo:
        consulta = consulta.filter(RegistroCoordinacion.tipo == tipo)
    if estado:
        consulta = consulta.filter(RegistroCoordinacion.estado == estado)

    paginacion = consulta.order_by(
        RegistroCoordinacion.fecha_recepcion.desc().nullslast(),
        RegistroCoordinacion.creado_en.desc(),
    ).paginate(page=max(pagina, 1), per_page=75, error_out=False)

    return render_template(
        "coordinacion/listado.html",
        registros=paginacion.items,
        paginacion=paginacion,
        q=q,
        tipo=tipo,
        estado=estado,
        tipos=TIPOS_REGISTRO,
    )


@coordinacion_bp.route("/registros/<int:registro_id>")
@login_required
def detalle(registro_id):
    return render_template(
        "coordinacion/detalle.html",
        registro=RegistroCoordinacion.query.get_or_404(registro_id),
    )


@coordinacion_bp.route("/registrar/<tipo>", methods=["GET", "POST"])
@login_required
def registrar(tipo):
    configuracion = TIPOS_REGISTRO.get(tipo)
    if not configuracion:
        abort(404)

    form = None
    if tipo == "pago":
        form = PagoForm()
        if form.validate_on_submit():
            periodo = form.periodo_desde.data or form.periodo_texto.data
            registro = _crear_base(
                "PAGO", form.no_sp.data, form.rc.data, form.providencia.data,
                form.fecha_recepcion.data, form.observaciones.data,
                [form.no_sp.data, form.rc.data, form.providencia.data, form.fecha_recepcion.data, periodo, form.boleta.data, form.total.data],
            )
            db.session.add(PagoCoordinacion(
                registro_id=registro.id,
                folios=form.folios.data,
                periodo_desde=form.periodo_desde.data,
                periodo_hasta=form.periodo_hasta.data,
                periodo_texto=form.periodo_texto.data,
                boleta=form.boleta.data,
                total=form.total.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "un pago")
            flash("Pago registrado correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo in ("instalacion", "desinstalacion"):
        form = MovimientoForm()
        if form.validate_on_submit():
            codigo = "INSTALACION" if tipo == "instalacion" else "DESINSTALACION"
            registro = _crear_base(
                codigo, form.no_sp.data, form.rc.data, form.providencia.data,
                form.fecha_recepcion.data, form.observaciones.data,
                [form.no_sp.data, form.rc.data, form.providencia.data, form.fecha_recepcion.data],
            )
            db.session.add(MovimientoDispositivo(
                registro_id=registro.id,
                movimiento=codigo,
                descripcion=form.descripcion.data,
                folios=form.folios.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "una instalación" if tipo == "instalacion" else "una desinstalación")
            flash("Movimiento registrado correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo == "anexo":
        form = AnexoForm()
        if form.validate_on_submit():
            registro = _crear_base(
                "ANEXO", form.no_sp.data, form.rc.data, form.providencia.data,
                form.fecha_recepcion.data, form.observaciones.data,
                [form.no_sp.data, form.rc.data, form.providencia.data, form.tipo_anexo.data,
                 form.fecha_recepcion.data, form.fecha_escaneado.data if form.escaneado.data else None],
            )
            db.session.add(AnexoCoordinacion(
                registro_id=registro.id,
                tipo_anexo=form.tipo_anexo.data,
                folios=form.folios.data,
                escaneado=form.escaneado.data,
                fecha_escaneado=form.fecha_escaneado.data,
                numero_anexo=form.numero_anexo.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "un anexo")
            flash("Anexo registrado correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo == "monitoreo":
        form = MonitoreoForm()
        if form.validate_on_submit():
            registro = _crear_base(
                "MONITOREO", form.no_sp.data, form.rc.data, form.providencia.data,
                form.fecha_recepcion.data, form.observaciones.data,
                [form.no_sp.data, form.rc.data, form.providencia.data, form.fecha_recepcion.data,
                 form.numero_reporte.data, form.tipo_evento.data],
            )
            db.session.add(ReporteMonitoreo(
                registro_id=registro.id,
                tipo_documento=form.tipo_documento.data or "PROVIDENCIA",
                numero_reporte=form.numero_reporte.data,
                tipo_evento=form.tipo_evento.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "un reporte de monitoreo")
            flash("Reporte de monitoreo registrado correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo == "documento-emitido":
        form = DocumentoEmitidoForm()
        if form.validate_on_submit():
            registro = _crear_base(
                "DOCUMENTO_EMITIDO", form.no_sp.data, form.rc.data, None,
                form.fecha.data, form.observaciones.data,
                [form.numero_documento.data, form.fecha.data, form.descripcion.data, form.destino.data],
            )
            db.session.add(DocumentoEmitido(
                registro_id=registro.id,
                numero_documento=form.numero_documento.data,
                descripcion=form.descripcion.data,
                destino=form.destino.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "un documento emitido")
            flash("Documento emitido registrado correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo == "actividad":
        form = ActividadForm()
        if form.validate_on_submit():
            registro = _crear_base(
                "ACTIVIDAD",
                fecha=form.fecha.data,
                observaciones=form.observaciones.data,
                campos_clave=[form.descripcion.data, form.fecha.data, form.tipo_actividad.data],
            )
            db.session.add(ActividadCoordinacion(
                registro_id=registro.id,
                tipo_actividad=form.tipo_actividad.data,
                area_apoyo=form.area_apoyo.data,
                descripcion=form.descripcion.data,
            ))
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "una actividad")
            flash("Actividad registrada correctamente.", "success")
            return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    elif tipo == "remision":
        form = RemisionForm()
        if form.validate_on_submit():
            registro = _crear_base(
                "REMISION",
                fecha=form.fecha.data,
                observaciones=form.observaciones.data,
                campos_clave=[form.destino.data, form.fecha.data],
            )
            registro.estado = "Información pendiente"
            remision = RemisionCoordinacion(
                registro_id=registro.id,
                destino=form.destino.data,
                numero_control=form.numero_control.data,
            )
            db.session.add(remision)
            db.session.commit()
            _registrar_bitacora_nuevo(registro, "una remisión")
            flash("Remisión creada. Ahora agregue los expedientes incluidos.", "success")
            return redirect(url_for("coordinacion.remision_detalle", remision_id=remision.id))

    return render_template(
        "coordinacion/formulario.html",
        tipo=tipo,
        configuracion=configuracion,
        form=form,
        expedientes=_sp_opciones(),
        catalogos=CATALOGOS,
    )


@coordinacion_bp.route("/remisiones/<int:remision_id>", methods=["GET", "POST"])
@login_required
def remision_detalle(remision_id):
    remision = RemisionCoordinacion.query.get_or_404(remision_id)
    form = RemisionExpedienteForm()
    if form.validate_on_submit():
        expediente, no_sp = resolver_expediente(form.no_sp.data)
        detalle = RemisionExpediente(
            remision_id=remision.id,
            expediente_id=expediente.id if expediente else None,
            no_sp_referencia=no_sp or form.no_sp.data.strip(),
            folios=form.folios.data,
            anexos=form.anexos.data,
            estado_foliacion=form.estado_foliacion.data,
            observaciones=form.observaciones.data,
        )
        db.session.add(detalle)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            flash("Ese SP ya está incluido en la remisión.", "warning")
            return redirect(url_for("coordinacion.remision_detalle", remision_id=remision.id))

        _recalcular_estado_remision(remision)
        registrar_bitacora(
            accion="AGREGAR_EXPEDIENTE_REMISION",
            modulo="Coordinación",
            descripcion=f"Se agregó el SP {detalle.no_sp_referencia} a la remisión {remision.id}.",
            usuario_id=current_user.id,
            expediente_id=detalle.expediente_id,
            entidad="RemisionExpediente",
            entidad_id=detalle.id,
            commit=False,
        )
        db.session.commit()
        flash("Expediente agregado a la remisión.", "success")
        return redirect(url_for("coordinacion.remision_detalle", remision_id=remision.id))

    return render_template(
        "coordinacion/remision_detalle.html",
        remision=remision,
        form=form,
        expedientes=_sp_opciones(),
    )


@coordinacion_bp.route("/remisiones/<int:remision_id>/expedientes/<int:detalle_id>/eliminar", methods=["POST"])
@login_required
def remision_eliminar_expediente(remision_id, detalle_id):
    remision = RemisionCoordinacion.query.get_or_404(remision_id)
    detalle = RemisionExpediente.query.filter_by(id=detalle_id, remision_id=remision.id).first_or_404()
    sp, expediente_id = detalle.no_sp_referencia, detalle.expediente_id
    db.session.delete(detalle)
    db.session.flush()
    _recalcular_estado_remision(remision)
    registrar_bitacora(
        accion="QUITAR_EXPEDIENTE_REMISION",
        modulo="Coordinación",
        descripcion=f"Se quitó el SP {sp} de la remisión {remision.id}.",
        usuario_id=current_user.id,
        expediente_id=expediente_id,
        entidad="RemisionExpediente",
        entidad_id=detalle_id,
        datos_anteriores={"sp": sp},
        commit=False,
    )
    db.session.commit()
    flash("Expediente retirado de la remisión.", "info")
    return redirect(url_for("coordinacion.remision_detalle", remision_id=remision.id))


def _carpeta_importaciones():
    carpeta = Path(current_app.instance_path) / "importaciones_coordinacion"
    carpeta.mkdir(parents=True, exist_ok=True)
    limite = datetime.now() - timedelta(hours=24)
    for archivo in carpeta.glob("*"):
        try:
            if datetime.fromtimestamp(archivo.stat().st_mtime) < limite:
                archivo.unlink(missing_ok=True)
        except OSError:
            pass
    return carpeta


@coordinacion_bp.route("/importar", methods=["GET", "POST"])
@login_required
@admin_required
def importar_excel():
    form = ImportarCoordinacionForm()
    resumen = confirmar = None
    if form.validate_on_submit():
        archivo = form.archivo.data
        nombre_original = secure_filename(archivo.filename) or "ACTIVIDADESCSOD.xlsx"
        token = uuid4().hex
        carpeta = _carpeta_importaciones()
        ruta = carpeta / f"{token}.xlsx"
        meta = carpeta / f"{token}.txt"
        archivo.save(ruta)
        meta.write_text(nombre_original, encoding="utf-8")
        try:
            resumen = ImportadorCoordinacion(ruta, current_user.id, nombre_original).procesar(importar=False)
            confirmar = ConfirmarImportacionForm()
            confirmar.token.data = token
        except Exception:
            ruta.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            current_app.logger.exception("Error al previsualizar importación histórica de Coordinación")
            flash("No fue posible analizar el archivo. Revise el formato e inténtelo nuevamente.", "danger")
    return render_template("coordinacion/importar.html", form=form, resumen=resumen, confirmar=confirmar)


@coordinacion_bp.route("/importar/confirmar", methods=["POST"])
@login_required
@admin_required
def confirmar_importacion():
    form = ConfirmarImportacionForm()
    if not form.validate_on_submit():
        flash("No fue posible validar la importación.", "danger")
        return redirect(url_for("coordinacion.importar_excel"))

    token = form.token.data.strip()
    if not token.isalnum() or len(token) != 32:
        abort(400)

    carpeta = _carpeta_importaciones()
    ruta = carpeta / f"{token}.xlsx"
    meta = carpeta / f"{token}.txt"
    if not ruta.exists() or not meta.exists():
        flash("La previsualización venció o el archivo temporal ya no existe.", "warning")
        return redirect(url_for("coordinacion.importar_excel"))

    nombre_original = meta.read_text(encoding="utf-8").strip() or "ACTIVIDADESCSOD.xlsx"
    try:
        resumen = ImportadorCoordinacion(ruta, current_user.id, nombre_original).procesar(importar=True)
        registrar_bitacora(
            accion="IMPORTAR_COORDINACION_EXCEL",
            modulo="Coordinación",
            descripcion=(
                f"Importación histórica desde {nombre_original}. Filas: {resumen['total']}; "
                f"completas: {resumen['completos']}; pendientes: {resumen['pendientes']}; "
                f"sin vincular: {resumen['sin_vincular']}; ya importadas: {resumen['ya_importados']}"
            ),
            usuario_id=current_user.id,
        )
        flash("Importación histórica completada.", "success")
    except Exception:
        current_app.logger.exception("Error al confirmar importación histórica de Coordinación")
        flash("La importación fue cancelada y no se guardaron cambios.", "danger")
        return redirect(url_for("coordinacion.importar_excel"))
    finally:
        ruta.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)

    return redirect(url_for("coordinacion.listado"))
