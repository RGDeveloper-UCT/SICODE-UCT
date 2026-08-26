from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.coordinacion_form import MonitoreoForm
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


def _detalles_anexos(expediente):
    """Devuelve metadatos conocidos de anexos sin almacenar documentos."""
    detalles = []
    vistos = set()

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
        })

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
            f"Se rectificó desde Reporte de monitoreo el total de anexos del "
            f"SP {expediente.no_sp}: {anterior if anterior is not None else 'sin dato'} -> {total}. "
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


def _registrar_monitoreo():
    form = MonitoreoForm()
    configuracion = TIPOS_REGISTRO["monitoreo"]

    if form.validate_on_submit():
        expediente, _ = resolver_expediente(form.no_sp.data)
        if not expediente:
            form.no_sp.errors.append(
                "El SP debe existir y estar activo para registrar el reporte como anexo."
            )
        else:
            estado = _estado_anexos(expediente)
            if estado["requiere_rectificacion"]:
                form.numero_anexo_monitoreo.errors.append(
                    "Primero rectifique el total de anexos y confirme el expediente en File Server."
                )
            else:
                numero = form.numero_anexo_monitoreo.data
                esperado = estado["siguiente_anexo"]
                if numero != esperado:
                    form.numero_anexo_monitoreo.errors.append(
                        f"El reporte debe registrarse como Anexo {esperado}. "
                        "Si File Server muestra otro número, use «Rectificar anexos» y vuelva a confirmar."
                    )
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
                    ))
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

                    total_anterior = expediente.anexos_rectificados
                    expediente.anexos_rectificados = numero
                    expediente.rectificado_en = datetime.utcnow()
                    expediente.rectificado_por_id = current_user.id

                    registrar_bitacora(
                        accion="REGISTRAR_MONITOREO_COMO_ANEXO",
                        modulo="Coordinación",
                        descripcion=(
                            f"Se registró reporte de monitoreo del SP {expediente.no_sp} "
                            f"como Anexo {numero}. Total de anexos: "
                            f"{total_anterior if total_anterior is not None else 'sin dato'} -> {numero}. "
                            "Número confirmado contra File Server."
                        ),
                        usuario_id=current_user.id,
                        expediente_id=expediente.id,
                        entidad="RegistroCoordinacion",
                        entidad_id=registro.id,
                        datos_posteriores={
                            "tipo": "MONITOREO",
                            "sp": expediente.no_sp,
                            "numero_anexo": numero,
                            "numero_reporte": form.numero_reporte.data,
                            "tipo_evento": form.tipo_evento.data,
                            "anexos_rectificados": numero,
                        },
                        commit=False,
                    )
                    db.session.commit()

                    flash(
                        f"Reporte de monitoreo registrado como Anexo {numero} del SP {expediente.no_sp}.",
                        "success",
                    )
                    return redirect(url_for("coordinacion.detalle", registro_id=registro.id))

    return render_template(
        "coordinacion/formulario.html",
        tipo="monitoreo",
        configuracion=configuracion,
        form=form,
        expedientes=_sp_opciones(),
        catalogos=CATALOGOS,
    )


def instalar_registro_monitoreo(app):
    """Extiende solo el caso MONITOREO sin duplicar el resto del módulo Coordinación."""
    original = app.view_functions.get("coordinacion.registrar")
    if original is None or getattr(original, "_control_anexos_monitoreo", False):
        return

    @wraps(original)
    def registrar_con_control_anexos(tipo):
        if tipo == "monitoreo":
            return _registrar_monitoreo()
        return original(tipo)

    protegido = login_required(registrar_con_control_anexos)
    protegido._control_anexos_monitoreo = True
    app.view_functions["coordinacion.registrar"] = protegido
