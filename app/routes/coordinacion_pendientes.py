from datetime import date
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.models.coordinacion import RegistroCoordinacion
from app.routes.coordinacion import coordinacion_bp
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente


TIPOS_ENTRANTES = {"EXPEDIENTE_COMPLETO", "PAGO", "INSTALACION", "DESINSTALACION", "ANEXO", "MONITOREO", "ANALISIS_RIESGO"}


def _texto(valor, limite=None):
    texto = str(valor or "").strip()
    if not texto:
        return None
    return texto[:limite] if limite else texto


def _fecha(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ValueError("La fecha indicada no es válida.")


def _decimal(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return Decimal(texto.replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError("El monto indicado no es válido.")


def _motivo_pendiente(registro):
    if not registro.no_sp_referencia:
        return "Falta identificar el SP"
    if registro.expediente_id is None:
        return "SP pendiente de vincular"
    if registro.tipo in TIPOS_ENTRANTES and not registro.fecha_recepcion:
        return "Falta fecha de recepción"
    if registro.tipo == "ANEXO" and registro.anexo_coordinacion and registro.anexo_coordinacion.documento_expediente_id is None:
        return "Anexo pendiente de incorporar al índice"
    if registro.estado and registro.estado != "Completo":
        return registro.estado
    return "Pendiente de verificación"


def _datos_registro(registro):
    datos = {
        "tipo": registro.tipo,
        "sp": registro.no_sp_referencia,
        "expediente_id": registro.expediente_id,
        "rc": registro.rc,
        "providencia": registro.providencia,
        "fecha_recepcion": registro.fecha_recepcion.isoformat() if registro.fecha_recepcion else None,
        "persona_entrega": registro.persona_entrega,
        "folios_recepcion": registro.folios_recepcion,
        "observaciones": registro.observaciones,
        "estado": registro.estado,
        "origen_registro": registro.origen_registro,
    }

    detalle = None
    if registro.pago:
        detalle = {
            "modelo": "PAGO",
            "periodo_desde": registro.pago.periodo_desde.isoformat() if registro.pago.periodo_desde else None,
            "periodo_hasta": registro.pago.periodo_hasta.isoformat() if registro.pago.periodo_hasta else None,
            "periodo_texto": registro.pago.periodo_texto,
            "boleta": registro.pago.boleta,
            "banco": registro.pago.banco,
            "total": str(registro.pago.total) if registro.pago.total is not None else None,
        }
    elif registro.movimiento_dispositivo:
        detalle = {
            "modelo": "MOVIMIENTO",
            "movimiento": registro.movimiento_dispositivo.movimiento,
            "descripcion": registro.movimiento_dispositivo.descripcion,
            "folios": registro.movimiento_dispositivo.folios,
        }
    elif registro.anexo_coordinacion:
        anexo = registro.anexo_coordinacion
        detalle = {
            "modelo": "ANEXO",
            "tipo_anexo": anexo.tipo_anexo,
            "titulo": anexo.titulo,
            "folios": anexo.folios,
            "numero_anexo": anexo.numero_anexo,
            "escaneado": bool(anexo.escaneado),
            "fecha_escaneado": anexo.fecha_escaneado.isoformat() if anexo.fecha_escaneado else None,
            "documento_expediente_id": anexo.documento_expediente_id,
            "es_vencido": bool(anexo.es_vencido),
        }
    elif registro.reporte_monitoreo:
        detalle = {
            "modelo": "MONITOREO",
            "tipo_documento": registro.reporte_monitoreo.tipo_documento,
            "numero_reporte": registro.reporte_monitoreo.numero_reporte,
            "tipo_evento": registro.reporte_monitoreo.tipo_evento,
        }
    elif registro.analisis_riesgo:
        detalle = {
            "modelo": "ANALISIS_RIESGO",
            "tipo_documento": registro.analisis_riesgo.tipo_documento,
            "correlativo": registro.analisis_riesgo.correlativo,
            "tipo_evento": registro.analisis_riesgo.tipo_evento,
        }
    elif registro.documento_emitido:
        detalle = {
            "modelo": "DOCUMENTO_EMITIDO",
            "numero_documento": registro.documento_emitido.numero_documento,
            "descripcion": registro.documento_emitido.descripcion,
            "destino": registro.documento_emitido.destino,
        }
    elif registro.actividad_coordinacion:
        detalle = {
            "modelo": "ACTIVIDAD",
            "tipo_actividad": registro.actividad_coordinacion.tipo_actividad,
            "area_apoyo": registro.actividad_coordinacion.area_apoyo,
            "descripcion": registro.actividad_coordinacion.descripcion,
        }
    elif registro.remision_coordinacion:
        detalle = {
            "modelo": "REMISION",
            "destino": registro.remision_coordinacion.destino,
            "numero_control": registro.remision_coordinacion.numero_control,
        }

    datos["detalle"] = detalle
    return datos


def _actualizar_comunes(registro):
    sp = _texto(request.form.get("no_sp"), 50)
    if sp:
        expediente, sp_normalizado = resolver_expediente(sp)
        if not expediente:
            raise ValueError(f"El SP {sp} no existe o está inactivo. No se puede vincular sin una referencia maestra válida.")
        registro.expediente_id = expediente.id
        registro.no_sp_referencia = sp_normalizado
    else:
        registro.expediente_id = None
        registro.no_sp_referencia = None

    registro.rc = _texto(request.form.get("rc"), 80)
    registro.providencia = _texto(request.form.get("providencia"), 120)
    registro.fecha_recepcion = _fecha(request.form.get("fecha_recepcion"))
    registro.persona_entrega = _texto(request.form.get("persona_entrega"), 180)
    registro.folios_recepcion = _texto(request.form.get("folios_recepcion"), 80)
    registro.observaciones = _texto(request.form.get("observaciones"))


def _actualizar_detalle(registro):
    if registro.pago:
        pago = registro.pago
        pago.periodo_desde = _fecha(request.form.get("periodo_desde"))
        pago.periodo_hasta = _fecha(request.form.get("periodo_hasta"))
        pago.periodo_texto = _texto(request.form.get("periodo_texto"), 120)
        pago.boleta = _texto(request.form.get("boleta"), 120)
        pago.banco = _texto(request.form.get("banco"), 120)
        pago.total = _decimal(request.form.get("total"))
    elif registro.movimiento_dispositivo:
        movimiento = registro.movimiento_dispositivo
        movimiento.descripcion = _texto(request.form.get("descripcion"), 180)
        movimiento.folios = _texto(request.form.get("folios_detalle"), 80)
    elif registro.anexo_coordinacion:
        anexo = registro.anexo_coordinacion
        anexo.tipo_anexo = _texto(request.form.get("tipo_anexo"), 120)
        anexo.titulo = _texto(request.form.get("titulo"), 180)
        anexo.folios = _texto(request.form.get("folios_detalle"), 80)
        anexo.escaneado = request.form.get("escaneado") == "1"
        anexo.fecha_escaneado = _fecha(request.form.get("fecha_escaneado"))
        # El número de anexo, su condición histórica y el vínculo al índice son
        # estructurales. Se muestran en la bandeja, pero se corrigen únicamente
        # mediante el flujo canónico de anexos para no romper secuencia/índice.
    elif registro.reporte_monitoreo:
        reporte = registro.reporte_monitoreo
        reporte.tipo_documento = _texto(request.form.get("tipo_documento"), 80)
        reporte.numero_reporte = _texto(request.form.get("numero_reporte"), 120)
        reporte.tipo_evento = _texto(request.form.get("tipo_evento"), 180)
    elif registro.analisis_riesgo:
        analisis = registro.analisis_riesgo
        analisis.tipo_documento = _texto(request.form.get("tipo_documento"), 80)
        analisis.correlativo = _texto(request.form.get("correlativo"), 120)
        analisis.tipo_evento = _texto(request.form.get("tipo_evento"), 180)
    elif registro.documento_emitido:
        documento = registro.documento_emitido
        documento.numero_documento = _texto(request.form.get("numero_documento"), 120) or documento.numero_documento
        documento.descripcion = _texto(request.form.get("descripcion"))
        documento.destino = _texto(request.form.get("destino"), 180)
    elif registro.actividad_coordinacion:
        actividad = registro.actividad_coordinacion
        actividad.tipo_actividad = _texto(request.form.get("tipo_actividad"), 100)
        actividad.area_apoyo = _texto(request.form.get("area_apoyo"), 180)
        actividad.descripcion = _texto(request.form.get("descripcion")) or actividad.descripcion
    elif registro.remision_coordinacion:
        remision = registro.remision_coordinacion
        remision.destino = _texto(request.form.get("destino"), 180) or remision.destino
        remision.numero_control = _texto(request.form.get("numero_control"), 120)


def _siguiente_pendiente(registro_id):
    return (
        RegistroCoordinacion.query
        .filter(RegistroCoordinacion.estado != "Completo", RegistroCoordinacion.id > registro_id)
        .order_by(RegistroCoordinacion.id.asc())
        .first()
        or RegistroCoordinacion.query
        .filter(RegistroCoordinacion.estado != "Completo", RegistroCoordinacion.id != registro_id)
        .order_by(RegistroCoordinacion.id.asc())
        .first()
    )


@coordinacion_bp.route("/pendientes")
@login_required
def pendientes():
    q = _texto(request.args.get("q")) or ""
    tipo = _texto(request.args.get("tipo")) or ""
    origen = _texto(request.args.get("origen")) or ""
    pagina = max(request.args.get("page", 1, type=int), 1)

    consulta = RegistroCoordinacion.query.filter(RegistroCoordinacion.estado != "Completo")
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
    if origen:
        consulta = consulta.filter(RegistroCoordinacion.origen_registro == origen)

    paginacion = consulta.order_by(
        RegistroCoordinacion.fecha_recepcion.asc().nullsfirst(),
        RegistroCoordinacion.creado_en.asc(),
    ).paginate(page=pagina, per_page=60, error_out=False)

    tipos = [valor for (valor,) in db.session.query(RegistroCoordinacion.tipo).filter(RegistroCoordinacion.estado != "Completo").distinct().order_by(RegistroCoordinacion.tipo).all()]
    origenes = [valor for (valor,) in db.session.query(RegistroCoordinacion.origen_registro).filter(RegistroCoordinacion.estado != "Completo").distinct().order_by(RegistroCoordinacion.origen_registro).all() if valor]

    return render_template(
        "coordinacion/pendientes.html",
        registros=paginacion.items,
        paginacion=paginacion,
        q=q,
        tipo=tipo,
        origen=origen,
        tipos=tipos,
        origenes=origenes,
        motivo_pendiente=_motivo_pendiente,
    )


@coordinacion_bp.route("/pendientes/<int:registro_id>", methods=["GET", "POST"])
@login_required
def verificar_pendiente(registro_id):
    registro = RegistroCoordinacion.query.get_or_404(registro_id)
    if request.method == "POST":
        if not getattr(current_user, "puede_modificar", False):
            abort(403)
        if request.form.get("confirmacion_file_server") != "1":
            flash("Debe confirmar que revisó el registro contra File Server antes de finalizar la verificación.", "danger")
            return render_template(
                "coordinacion/verificar_pendiente.html",
                registro=registro,
                datos=_datos_registro(registro),
                motivo_pendiente=_motivo_pendiente(registro),
                siguiente=_siguiente_pendiente(registro.id),
            ), 400

        anteriores = _datos_registro(registro)
        try:
            _actualizar_comunes(registro)
            _actualizar_detalle(registro)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template(
                "coordinacion/verificar_pendiente.html",
                registro=registro,
                datos=_datos_registro(registro),
                motivo_pendiente=_motivo_pendiente(registro),
                siguiente=_siguiente_pendiente(registro.id),
            ), 400

        posteriores = _datos_registro(registro)
        hubo_cambios = anteriores != posteriores
        motivo = _texto(request.form.get("motivo_rectificacion"))
        if hubo_cambios and not motivo:
            db.session.rollback()
            flash("Indique el motivo de la rectificación porque se modificaron datos del registro.", "danger")
            return render_template(
                "coordinacion/verificar_pendiente.html",
                registro=registro,
                datos=_datos_registro(registro),
                motivo_pendiente=_motivo_pendiente(registro),
                siguiente=_siguiente_pendiente(registro.id),
            ), 400

        # Confirmar File Server no inventa evidencia: deja explícito que fue una
        # comprobación humana y quién la realizó. Si luego de corregir existe SP
        # maestro y fecha para registros entrantes, el registro queda completo.
        faltantes = []
        if registro.tipo in TIPOS_ENTRANTES:
            if not registro.expediente_id:
                faltantes.append("SP vinculado")
            if not registro.fecha_recepcion:
                faltantes.append("fecha de recepción")
        if faltantes:
            registro.estado = "Información pendiente"
        else:
            registro.estado = "Completo"

        posteriores = _datos_registro(registro)
        accion = "VERIFICAR_Y_RECTIFICAR_COORDINACION" if hubo_cambios else "VERIFICAR_COORDINACION_FILE_SERVER"
        registrar_bitacora(
            accion=accion,
            modulo="Coordinación",
            descripcion=(
                f"Se verificó contra File Server el registro #{registro.id} ({registro.tipo})"
                + (" y se rectificaron datos." if hubo_cambios else "; la información coincidió con lo revisado.")
            ),
            usuario_id=current_user.id,
            expediente_id=registro.expediente_id,
            entidad="RegistroCoordinacion",
            entidad_id=registro.id,
            datos_anteriores=anteriores,
            datos_posteriores=posteriores,
            motivo=motivo or "Verificación humana contra File Server",
            commit=False,
        )
        db.session.commit()

        if registro.estado == "Completo":
            flash(f"Registro #{registro.id} verificado correctamente contra File Server.", "success")
        else:
            flash(
                f"La verificación se guardó, pero el registro continúa pendiente: falta {', '.join(faltantes)}.",
                "warning",
            )

        siguiente = _siguiente_pendiente(registro.id)
        if request.form.get("continuar") == "1" and siguiente:
            return redirect(url_for("coordinacion.verificar_pendiente", registro_id=siguiente.id))
        return redirect(url_for("coordinacion.pendientes"))

    return render_template(
        "coordinacion/verificar_pendiente.html",
        registro=registro,
        datos=_datos_registro(registro),
        motivo_pendiente=_motivo_pendiente(registro),
        siguiente=_siguiente_pendiente(registro.id),
    )
