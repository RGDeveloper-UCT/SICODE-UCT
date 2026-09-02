from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.coordinacion_form import AnexoForm, MonitoreoForm
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.models.expediente import Expediente
from app.routes.coordinacion import CATALOGOS, TIPOS_REGISTRO, _crear_base, _sp_opciones
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente


monitoreo_anexos_bp = Blueprint(
    "monitoreo_anexos",
    __name__,
    url_prefix="/coordinacion/monitoreo",
)

MAX_ANEXOS_MONITOREO = 200


def _entero_anexo(valor):
    try:
        numero = int(str(valor or "").strip())
    except (TypeError, ValueError):
        return None
    return numero if numero >= 1 else None


def _anexo_coordinacion_existente(expediente, numero):
    """Evita registrar dos veces el mismo número operativo para un SP."""
    return (
        db.session.query(AnexoCoordinacion)
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id == expediente.id,
            AnexoCoordinacion.numero_anexo == str(numero),
        )
        .first()
    )


def _anexo_rectificado_existente(expediente, numero):
    return (
        AnexoRectificado.query
        .filter_by(expediente_id=expediente.id, numero_anexo=str(numero), activo=True)
        .first()
    )


def _detalles_anexos(expediente):
    """Devuelve metadatos conocidos de anexos sin almacenar documentos."""
    detalles = []
    vistos = set()

    # Coordinación va primero para conservar la marca de vencido/histórico.
    coordinacion = (
        db.session.query(AnexoCoordinacion)
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id == expediente.id,
            AnexoCoordinacion.numero_anexo.isnot(None),
        )
        .order_by(AnexoCoordinacion.id.asc())
        .all()
    )
    for anexo in coordinacion:
        numero = str(anexo.numero_anexo or "").strip()
        clave = ("numero", numero) if numero else ("coordinacion", anexo.id)
        if clave in vistos:
            continue
        vistos.add(clave)
        detalles.append({
            "numero": numero or None,
            "titulo": anexo.titulo or anexo.tipo_anexo or "Anexo",
            "origen": "Coordinación",
            "vencido": bool(anexo.es_vencido),
        })

    rectificados = (
        AnexoRectificado.query
        .filter_by(expediente_id=expediente.id, activo=True)
        .order_by(AnexoRectificado.id.asc())
        .all()
    )
    for anexo in rectificados:
        numero = str(anexo.numero_anexo or "").strip()
        clave = ("numero", numero) if numero else ("rectificado", anexo.id)
        if clave in vistos:
            continue
        vistos.add(clave)
        detalles.append({
            "numero": numero or None,
            "titulo": anexo.titulo or "Anexo",
            "origen": "Rectificación",
            "vencido": False,
        })

    return detalles


def _estado_anexos(expediente):
    detalles = _detalles_anexos(expediente)
    numeros = [_entero_anexo(item["numero"]) for item in detalles]
    numeros = [numero for numero in numeros if numero is not None]

    total_indice = len([doc for doc in expediente.documentos_activos if doc.es_anexo])
    maximo_detalle = max(numeros, default=0)
    minimo_conocido = max(total_indice, maximo_detalle)

    total_rectificado = expediente.anexos_rectificados
    inconsistente = (
        total_rectificado is not None
        and total_rectificado < minimo_conocido
    )
    requiere_rectificacion = total_rectificado is None or inconsistente
    siguiente = (
        total_rectificado + 1
        if not requiere_rectificacion
        else None
    )

    return {
        "expediente_id": expediente.id,
        "no_sp": expediente.no_sp,
        "total_rectificado": total_rectificado,
        "total_indice": total_indice,
        "minimo_conocido": minimo_conocido,
        "inconsistente": inconsistente,
        "requiere_rectificacion": requiere_rectificacion,
        "siguiente_anexo": siguiente,
        "anexos": detalles,
    }


def _validar_numero(expediente, numero, es_vencido):
    estado = _estado_anexos(expediente)
    if estado["requiere_rectificacion"]:
        return estado, "Primero rectifique el total de anexos y confirme el expediente en File Server."

    if numero is None or numero < 1 or numero > MAX_ANEXOS_MONITOREO:
        return estado, f"Indique un número de anexo entre 1 y {MAX_ANEXOS_MONITOREO}."

    if _anexo_coordinacion_existente(expediente, numero):
        return estado, f"El Anexo {numero} ya está individualizado en Coordinación para este SP."

    if es_vencido:
        total = estado["total_rectificado"] or 0
        if numero > total:
            return estado, (
                f"Un anexo vencido/histórico debe pertenecer a la secuencia ya existente (1 a {total}). "
                f"Para incorporar un anexo nuevo use el Anexo {estado['siguiente_anexo']}."
            )
        return estado, None

    esperado = estado["siguiente_anexo"]
    if numero != esperado:
        return estado, (
            f"El anexo vigente debe registrarse como Anexo {esperado}. "
            "Si está capturando un anexo anterior, marque «ANEXO VENCIDO / HISTÓRICO»."
        )
    return estado, None


def _actualizar_secuencia_vigente(expediente, numero, es_vencido):
    """Solo un anexo nuevo y vigente puede avanzar el contador maestro."""
    anterior = expediente.anexos_rectificados
    if not es_vencido:
        expediente.anexos_rectificados = numero
        expediente.rectificado_en = datetime.utcnow()
        expediente.rectificado_por_id = current_user.id
    return anterior


@monitoreo_anexos_bp.get("/estado-sp")
@login_required
def estado_sp():
    no_sp = (request.args.get("no_sp") or "").strip()
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({
            "ok": False,
            "mensaje": "El SP indicado no existe o no está activo en SICODE.",
        }), 404

    return jsonify({"ok": True, **_estado_anexos(expediente)})


@monitoreo_anexos_bp.post("/rectificar-anexos")
@login_required
def rectificar_anexos():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    expediente_id = datos.get("expediente_id")
    expediente = db.session.get(Expediente, expediente_id)
    if not expediente or not expediente.activo:
        return jsonify({"ok": False, "mensaje": "No fue posible localizar el SP activo."}), 404

    try:
        total = int(datos.get("total_anexos"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "mensaje": "Indique un total de anexos válido."}), 400

    if total < 0 or total > MAX_ANEXOS_MONITOREO:
        return jsonify({
            "ok": False,
            "mensaje": f"El total debe estar entre 0 y {MAX_ANEXOS_MONITOREO}.",
        }), 400

    estado = _estado_anexos(expediente)
    if total < estado["minimo_conocido"]:
        return jsonify({
            "ok": False,
            "mensaje": (
                f"SICODE ya tiene evidencia de al menos {estado['minimo_conocido']} anexo(s). "
                "Confirme el expediente en File Server y escriba un total igual o mayor."
            ),
        }), 400

    anterior = expediente.anexos_rectificados
    expediente.anexos_rectificados = total
    expediente.rectificado_en = datetime.utcnow()
    expediente.rectificado_por_id = current_user.id

    registrar_bitacora(
        accion="RECTIFICAR_ANEXOS_DESDE_MONITOREO",
        modulo="Coordinación",
        descripcion=(
            f"Se rectificó desde el control de anexos el total del SP {expediente.no_sp}: "
            f"{anterior if anterior is not None else 'sin dato'} -> {total}. "
            "La verificación del número físico se confirmó contra File Server."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
        datos_anteriores={"anexos_rectificados": anterior},
        datos_posteriores={"anexos_rectificados": total},
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "mensaje": f"SP {expediente.no_sp} actualizado con {total} anexo(s).",
        **_estado_anexos(expediente),
    })


def _titulo_reporte(form):
    numero = (form.numero_reporte.data or "").strip()
    evento = (form.tipo_evento.data or "").strip()
    partes = ["Reporte de monitoreo"]
    if numero:
        partes.append(f"No. {numero}")
    if evento:
        partes.append(f"— {evento}")
    return " ".join(partes)[:180]


def _render_control(tipo, form):
    return render_template(
        "coordinacion/anexo_control.html",
        tipo=tipo,
        configuracion=TIPOS_REGISTRO[tipo],
        form=form,
        expedientes=_sp_opciones(),
        catalogos=CATALOGOS,
    )


def _registrar_anexo():
    form = AnexoForm()

    if form.validate_on_submit():
        expediente, _ = resolver_expediente(form.no_sp.data)
        if not expediente:
            form.no_sp.errors.append("El SP debe existir y estar activo para registrar el anexo.")
        else:
            numero = _entero_anexo(form.numero_anexo.data)
            es_vencido = bool(form.anexo_vencido.data)
            estado, error = _validar_numero(expediente, numero, es_vencido)
            if error:
                form.numero_anexo.errors.append(error)
            else:
                registro = _crear_base(
                    "ANEXO",
                    form.no_sp.data,
                    form.rc.data,
                    form.providencia.data,
                    form.fecha_recepcion.data,
                    form.observaciones.data,
                    [
                        form.no_sp.data,
                        form.rc.data,
                        form.providencia.data,
                        form.tipo_anexo.data,
                        form.fecha_recepcion.data,
                        numero,
                    ],
                )
                anexo = AnexoCoordinacion(
                    registro_id=registro.id,
                    tipo_anexo=form.tipo_anexo.data,
                    titulo=(form.tipo_anexo.data or "Anexo")[:180],
                    folios=form.folios.data,
                    escaneado=form.escaneado.data,
                    fecha_escaneado=form.fecha_escaneado.data,
                    numero_anexo=str(numero),
                    es_vencido=es_vencido,
                )
                db.session.add(anexo)

                total_anterior = _actualizar_secuencia_vigente(expediente, numero, es_vencido)
                registrar_bitacora(
                    accion="REGISTRAR_ANEXO_VENCIDO" if es_vencido else "REGISTRAR_ANEXO_VIGENTE",
                    modulo="Coordinación",
                    descripcion=(
                        f"Se registró Anexo {numero} del SP {expediente.no_sp}. "
                        + (
                            f"Marcado como ANEXO VENCIDO/HISTÓRICO; el total vigente permanece en {total_anterior}."
                            if es_vencido
                            else f"Anexo vigente; total de anexos {total_anterior} -> {numero}."
                        )
                    ),
                    usuario_id=current_user.id,
                    expediente_id=expediente.id,
                    entidad="RegistroCoordinacion",
                    entidad_id=registro.id,
                    datos_posteriores={
                        "tipo": "ANEXO",
                        "sp": expediente.no_sp,
                        "numero_anexo": numero,
                        "es_vencido": es_vencido,
                        "anexos_rectificados": expediente.anexos_rectificados,
                    },
                    commit=False,
                )
                db.session.commit()

                if es_vencido:
                    flash(
                        f"ANEXO VENCIDO/HISTÓRICO {numero} registrado en el SP {expediente.no_sp}. "
                        f"La secuencia vigente continúa en {total_anterior}.",
                        "warning",
                    )
                else:
                    flash(
                        f"Anexo {numero} registrado correctamente. La secuencia vigente ahora llega a {numero}.",
                        "success",
                    )
                return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    return _render_control("anexo", form)


def _registrar_monitoreo():
    form = MonitoreoForm()

    if form.validate_on_submit():
        expediente, _ = resolver_expediente(form.no_sp.data)
        if not expediente:
            form.no_sp.errors.append(
                "El SP debe existir y estar activo para registrar el reporte como anexo."
            )
        else:
            numero = form.numero_anexo_monitoreo.data
            es_vencido = bool(form.anexo_vencido.data)
            estado, error = _validar_numero(expediente, numero, es_vencido)
            if error:
                form.numero_anexo_monitoreo.errors.append(error)
            else:
                registro = _crear_base(
                    "MONITOREO",
                    form.no_sp.data,
                    form.rc.data,
                    form.providencia.data,
                    form.fecha_recepcion.data,
                    form.observaciones.data,
                    [
                        form.no_sp.data,
                        form.rc.data,
                        form.providencia.data,
                        form.fecha_recepcion.data,
                        form.numero_reporte.data,
                        form.tipo_evento.data,
                        numero,
                    ],
                )

                titulo = _titulo_reporte(form)
                db.session.add(ReporteMonitoreo(
                    registro_id=registro.id,
                    tipo_documento=form.tipo_documento.data or "PROVIDENCIA",
                    numero_reporte=form.numero_reporte.data,
                    tipo_evento=form.tipo_evento.data,
                ))
                db.session.add(AnexoCoordinacion(
                    registro_id=registro.id,
                    tipo_anexo="REPORTE DE MONITOREO",
                    titulo=titulo,
                    folios=form.folios.data,
                    escaneado=False,
                    numero_anexo=str(numero),
                    es_vencido=es_vencido,
                ))

                # Mantiene el detalle rectificado sin crear un duplicado si ese
                # número histórico ya había sido descrito durante rectificación.
                if not _anexo_rectificado_existente(expediente, numero):
                    db.session.add(AnexoRectificado(
                        expediente_id=expediente.id,
                        numero_anexo=str(numero),
                        titulo=titulo,
                        tipo_anexo="OTRO",
                        fecha_recepcion=form.fecha_recepcion.data,
                        persona_entrega=form.persona_entrega.data,
                        rc=form.rc.data,
                        providencia=form.providencia.data,
                        folios=form.folios.data,
                        escaneado=False,
                        observaciones=form.observaciones.data,
                        creado_por_id=current_user.id,
                        activo=True,
                    ))

                total_anterior = _actualizar_secuencia_vigente(expediente, numero, es_vencido)

                registrar_bitacora(
                    accion=(
                        "REGISTRAR_MONITOREO_COMO_ANEXO_VENCIDO"
                        if es_vencido
                        else "REGISTRAR_MONITOREO_COMO_ANEXO"
                    ),
                    modulo="Coordinación",
                    descripcion=(
                        f"Se registró reporte de monitoreo del SP {expediente.no_sp} como Anexo {numero}. "
                        + (
                            f"ANEXO VENCIDO/HISTÓRICO: el total vigente permanece en {total_anterior}. "
                            if es_vencido
                            else f"Total de anexos: {total_anterior} -> {numero}. "
                        )
                        + "Número confirmado contra File Server."
                    ),
                    usuario_id=current_user.id,
                    expediente_id=expediente.id,
                    entidad="RegistroCoordinacion",
                    entidad_id=registro.id,
                    datos_posteriores={
                        "tipo": "MONITOREO",
                        "sp": expediente.no_sp,
                        "numero_anexo": numero,
                        "es_vencido": es_vencido,
                        "numero_reporte": form.numero_reporte.data,
                        "tipo_evento": form.tipo_evento.data,
                        "anexos_rectificados": expediente.anexos_rectificados,
                    },
                    commit=False,
                )
                db.session.commit()

                if es_vencido:
                    flash(
                        f"Reporte registrado como ANEXO VENCIDO/HISTÓRICO {numero} del SP {expediente.no_sp}. "
                        f"La secuencia vigente continúa en {total_anterior}.",
                        "warning",
                    )
                else:
                    flash(
                        f"Reporte de monitoreo registrado como Anexo {numero} del SP {expediente.no_sp}.",
                        "success",
                    )
                return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    return _render_control("monitoreo", form)


def instalar_registro_monitoreo(app):
    """Centraliza ANEXO/MONITOREO para proteger la secuencia maestra del SP."""
    original = app.view_functions.get("coordinacion.registrar")
    if original is None or getattr(original, "_control_anexos_monitoreo", False):
        return

    @wraps(original)
    def registrar_con_control_anexos(tipo):
        if tipo == "monitoreo":
            return _registrar_monitoreo()
        if tipo == "anexo":
            return _registrar_anexo()
        return original(tipo)

    protegido = login_required(registrar_con_control_anexos)
    protegido._control_anexos_monitoreo = True
    app.view_functions["coordinacion.registrar"] = protegido
