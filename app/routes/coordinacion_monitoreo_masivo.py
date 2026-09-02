from datetime import date, datetime
from uuid import uuid4

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.coordinacion_form import _normalizar_referencia
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, ReporteMonitoreo
from app.routes.coordinacion import CATALOGOS, TIPOS_REGISTRO, _crear_base, _sp_opciones, coordinacion_bp
from app.routes.monitoreo_anexos import (
    MAX_ANEXOS_MONITOREO,
    _actualizar_secuencia_vigente,
    _anexo_rectificado_existente,
    _estado_anexos,
    _validar_numero,
)
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente


MAX_REPORTES_MASIVOS = 30
SESION_LOTE = "monitoreo_masivo_lote"

# La tarjeta se integra al mismo catálogo que ya utiliza Coordinación → REGISTROS.
# Los registros creados siguen siendo MONITOREO para no fragmentar reportes,
# consultas, exportaciones ni estadísticas existentes.
TIPOS_REGISTRO.setdefault(
    "monitoreo-masivo",
    {
        "codigo": "MONITOREO",
        "titulo": "Registro masivo de monitoreo",
        "descripcion": (
            "Registre varios reportes con una sola RC/RE, providencia y fecha, "
            "rectificando cada SP antes de confirmar el lote."
        ),
    },
)


class ValidacionLote(ValueError):
    pass


def _lote_sesion():
    valor = session.get(SESION_LOTE)
    return valor if isinstance(valor, dict) else {}


def _nuevo_lote():
    lote = {"id": uuid4().hex, "rectificados": {}}
    session[SESION_LOTE] = lote
    session.modified = True
    return lote


def _validar_lote_id(lote_id):
    lote = _lote_sesion()
    if not lote or lote.get("id") != str(lote_id or ""):
        return None
    return lote


def _entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _fecha(valor):
    try:
        return datetime.strptime(str(valor or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _texto(valor, limite):
    return str(valor or "").strip()[:limite]


def _titulo_reporte(numero_reporte, tipo_evento):
    partes = ["Reporte de monitoreo"]
    if numero_reporte:
        partes.append(f"No. {numero_reporte}")
    if tipo_evento:
        partes.append(f"— {tipo_evento}")
    return " ".join(partes)[:180]


def _marca_rectificacion(expediente, lote):
    return (lote.get("rectificados") or {}).get(str(expediente.id))


def _estado_masivo(expediente, lote):
    estado_anexos = _estado_anexos(expediente)
    marca = _marca_rectificacion(expediente, lote)
    rectificado_lote = bool(
        marca
        and marca.get("folios") == expediente.folios_rectificados
        and marca.get("anexos") == expediente.anexos_rectificados
        and expediente.rectificado_por_id == current_user.id
    )
    return {
        "expediente_id": expediente.id,
        "no_sp": expediente.no_sp,
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "minimo_anexos_conocido": estado_anexos["minimo_conocido"],
        "siguiente_anexo": (
            expediente.anexos_rectificados + 1
            if expediente.anexos_rectificados is not None
            else None
        ),
        "rectificado_lote": rectificado_lote,
        "rectificado_en": expediente.rectificado_en.isoformat() if expediente.rectificado_en else None,
    }


@coordinacion_bp.before_request
def _redirigir_tarjeta_monitoreo_masivo():
    if request.endpoint != "coordinacion.registrar":
        return None
    if (request.view_args or {}).get("tipo") != "monitoreo-masivo":
        return None
    return redirect(url_for("coordinacion.monitoreo_masivo"))


@coordinacion_bp.route("/monitoreo/masivo", methods=["GET", "POST"])
@login_required
def monitoreo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    if request.method == "GET":
        lote = _nuevo_lote()
        return render_template(
            "coordinacion/monitoreo_masivo.html",
            lote_id=lote["id"],
            expedientes=_sp_opciones(),
            catalogos=CATALOGOS,
            fecha_hoy=date.today().isoformat(),
            max_reportes=MAX_REPORTES_MASIVOS,
        )

    datos = request.get_json(silent=True) or {}
    lote = _validar_lote_id(datos.get("lote_id"))
    if lote is None:
        return jsonify({
            "ok": False,
            "mensaje": "El lote expiró o la página fue recargada. Abra de nuevo el registro masivo.",
        }), 409

    if datos.get("confirmacion_final") is not True:
        return jsonify({
            "ok": False,
            "mensaje": "Debe realizar la verificación final del lote antes de registrarlo.",
        }), 400

    tipo_referencia = _texto(datos.get("tipo_referencia") or "RC", 2).upper()
    numero_referencia = _texto(datos.get("rc"), 80)
    rc = _normalizar_referencia(tipo_referencia, numero_referencia)
    providencia = _texto(datos.get("providencia"), 120)
    persona_entrega = _texto(datos.get("persona_entrega"), 180) or None
    fecha_recepcion = _fecha(datos.get("fecha_recepcion"))

    if tipo_referencia not in {"RC", "RE"}:
        return jsonify({"ok": False, "mensaje": "Seleccione RC o RE como tipo de referencia."}), 400
    if not rc:
        return jsonify({"ok": False, "mensaje": "Ingrese la RC/RE compartida por el lote."}), 400
    if not providencia:
        return jsonify({"ok": False, "mensaje": "Ingrese la providencia compartida por el lote."}), 400
    if fecha_recepcion is None:
        return jsonify({"ok": False, "mensaje": "Ingrese una fecha de recepción válida."}), 400

    reportes = datos.get("reportes")
    if not isinstance(reportes, list) or not reportes:
        return jsonify({"ok": False, "mensaje": "Agregue al menos un reporte de monitoreo."}), 400
    if len(reportes) > MAX_REPORTES_MASIVOS:
        return jsonify({
            "ok": False,
            "mensaje": f"Un lote puede contener como máximo {MAX_REPORTES_MASIVOS} reportes.",
        }), 400

    filas = []
    vistos = set()
    expedientes_lote = {}

    for indice, item in enumerate(reportes, start=1):
        if not isinstance(item, dict):
            return jsonify({"ok": False, "mensaje": f"Fila {indice}: datos inválidos."}), 400

        no_sp = _texto(item.get("no_sp"), 60)
        numero_reporte = _texto(item.get("numero_reporte"), 120)
        tipo_evento = _texto(item.get("tipo_evento"), 180)
        folios = _texto(item.get("folios"), 80)
        numero_anexo = _entero(item.get("numero_anexo"))
        es_vencido = item.get("es_vencido") is True

        if not no_sp:
            return jsonify({"ok": False, "mensaje": f"Fila {indice}: indique el No. de SP."}), 400
        expediente, _ = resolver_expediente(no_sp)
        if not expediente:
            return jsonify({
                "ok": False,
                "mensaje": f"Fila {indice}: el SP {no_sp} no existe o no está activo.",
            }), 400
        if not numero_reporte:
            return jsonify({"ok": False, "mensaje": f"Fila {indice}: indique el número de reporte."}), 400
        if not tipo_evento:
            return jsonify({"ok": False, "mensaje": f"Fila {indice}: indique el tipo de evento."}), 400
        if not folios:
            return jsonify({"ok": False, "mensaje": f"Fila {indice}: indique los folios del reporte."}), 400
        if numero_anexo is None or numero_anexo < 1 or numero_anexo > MAX_ANEXOS_MONITOREO:
            return jsonify({
                "ok": False,
                "mensaje": f"Fila {indice}: indique un número de anexo entre 1 y {MAX_ANEXOS_MONITOREO}.",
            }), 400

        clave = (expediente.id, numero_reporte.upper())
        if clave in vistos:
            return jsonify({
                "ok": False,
                "mensaje": f"Fila {indice}: el reporte {numero_reporte} está repetido para el SP {expediente.no_sp}.",
            }), 400
        vistos.add(clave)

        existente = (
            db.session.query(ReporteMonitoreo.id)
            .join(RegistroCoordinacion, ReporteMonitoreo.registro_id == RegistroCoordinacion.id)
            .filter(
                RegistroCoordinacion.expediente_id == expediente.id,
                ReporteMonitoreo.numero_reporte == numero_reporte,
            )
            .first()
        )
        if existente:
            return jsonify({
                "ok": False,
                "mensaje": (
                    f"Fila {indice}: el reporte {numero_reporte} ya está registrado "
                    f"para el SP {expediente.no_sp}."
                ),
            }), 409

        filas.append({
            "indice": indice,
            "expediente": expediente,
            "no_sp": expediente.no_sp,
            "numero_reporte": numero_reporte,
            "tipo_evento": tipo_evento,
            "folios": folios,
            "numero_anexo": numero_anexo,
            "es_vencido": es_vencido,
        })
        expedientes_lote[expediente.id] = expediente

    # Cada SP debe haber sido rectificado dentro de ESTE lote. Además se
    # comprueba que nadie haya cambiado sus totales después de esa rectificación.
    for expediente in expedientes_lote.values():
        marca = _marca_rectificacion(expediente, lote)
        if not marca:
            return jsonify({
                "ok": False,
                "mensaje": f"El SP {expediente.no_sp} debe rectificarse antes de la verificación final.",
            }), 400
        if (
            expediente.rectificado_por_id != current_user.id
            or expediente.folios_rectificados != marca.get("folios")
            or expediente.anexos_rectificados != marca.get("anexos")
        ):
            return jsonify({
                "ok": False,
                "mensaje": (
                    f"Los totales del SP {expediente.no_sp} cambiaron después de rectificarlo. "
                    "Rectifique nuevamente antes de registrar el lote."
                ),
            }), 409

    lote_codigo = f"MON-{lote['id'][:20]}"
    creados = []

    try:
        for fila in filas:
            expediente = fila["expediente"]
            _estado, error = _validar_numero(
                expediente,
                fila["numero_anexo"],
                fila["es_vencido"],
            )
            if error:
                raise ValidacionLote(f"Fila {fila['indice']} · SP {expediente.no_sp}: {error}")

            registro = _crear_base(
                "MONITOREO",
                expediente.no_sp,
                rc,
                providencia,
                fecha_recepcion,
                None,
                [
                    expediente.no_sp,
                    rc,
                    providencia,
                    fecha_recepcion,
                    fila["numero_reporte"],
                    fila["tipo_evento"],
                    fila["numero_anexo"],
                    lote_codigo,
                ],
            )
            registro.persona_entrega = persona_entrega
            registro.folios_recepcion = fila["folios"]
            registro.origen_registro = "MASIVO"
            registro.lote_importacion = lote_codigo
            registro.hoja_origen = "MONITOREO_MASIVO"
            registro.fila_origen = fila["indice"]

            titulo = _titulo_reporte(fila["numero_reporte"], fila["tipo_evento"])
            db.session.add(ReporteMonitoreo(
                registro_id=registro.id,
                tipo_documento="PROVIDENCIA",
                numero_reporte=fila["numero_reporte"],
                tipo_evento=fila["tipo_evento"],
            ))
            db.session.add(AnexoCoordinacion(
                registro_id=registro.id,
                tipo_anexo="REPORTE DE MONITOREO",
                titulo=titulo,
                folios=fila["folios"],
                escaneado=False,
                numero_anexo=str(fila["numero_anexo"]),
                es_vencido=fila["es_vencido"],
            ))

            if not _anexo_rectificado_existente(expediente, fila["numero_anexo"]):
                db.session.add(AnexoRectificado(
                    expediente_id=expediente.id,
                    numero_anexo=str(fila["numero_anexo"]),
                    titulo=titulo,
                    tipo_anexo="OTRO",
                    fecha_recepcion=fecha_recepcion,
                    persona_entrega=persona_entrega,
                    rc=rc,
                    providencia=providencia,
                    folios=fila["folios"],
                    escaneado=False,
                    observaciones=None,
                    creado_por_id=current_user.id,
                    activo=True,
                ))

            total_anterior = _actualizar_secuencia_vigente(
                expediente,
                fila["numero_anexo"],
                fila["es_vencido"],
            )

            registrar_bitacora(
                accion=(
                    "REGISTRAR_MONITOREO_MASIVO_COMO_ANEXO_VENCIDO"
                    if fila["es_vencido"]
                    else "REGISTRAR_MONITOREO_MASIVO_COMO_ANEXO"
                ),
                modulo="Coordinación",
                descripcion=(
                    f"Lote {lote_codigo}: reporte {fila['numero_reporte']} del SP "
                    f"{expediente.no_sp} registrado como Anexo {fila['numero_anexo']}. "
                    + (
                        f"ANEXO VENCIDO/HISTÓRICO; la secuencia vigente permanece en {total_anterior}."
                        if fila["es_vencido"]
                        else f"Secuencia vigente: {total_anterior} -> {fila['numero_anexo']}."
                    )
                ),
                usuario_id=current_user.id,
                expediente_id=expediente.id,
                entidad="RegistroCoordinacion",
                entidad_id=registro.id,
                datos_posteriores={
                    "tipo": "MONITOREO",
                    "origen_registro": "MASIVO",
                    "lote": lote_codigo,
                    "sp": expediente.no_sp,
                    "numero_reporte": fila["numero_reporte"],
                    "tipo_evento": fila["tipo_evento"],
                    "folios": fila["folios"],
                    "numero_anexo": fila["numero_anexo"],
                    "es_vencido": fila["es_vencido"],
                },
                commit=False,
            )

            # Hace visibles los cambios de esta fila a las validaciones de una
            # fila posterior del mismo SP, sin cerrar la transacción.
            db.session.flush()
            creados.append(registro.id)

        registrar_bitacora(
            accion="REGISTRAR_LOTE_MONITOREO_MASIVO",
            modulo="Coordinación",
            descripcion=(
                f"Se registró el lote {lote_codigo} con {len(creados)} reporte(s) "
                f"de monitoreo bajo {rc} y providencia {providencia}."
            ),
            usuario_id=current_user.id,
            entidad="RegistroCoordinacion",
            entidad_id=creados[0],
            datos_posteriores={
                "lote": lote_codigo,
                "cantidad": len(creados),
                "rc": rc,
                "providencia": providencia,
                "fecha_recepcion": fecha_recepcion.isoformat(),
                "registros": creados,
            },
            commit=False,
        )
        db.session.commit()
    except ValidacionLote as exc:
        db.session.rollback()
        return jsonify({"ok": False, "mensaje": str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al registrar lote masivo de monitoreo")
        return jsonify({
            "ok": False,
            "mensaje": "No fue posible registrar el lote. No se guardó ningún reporte del lote.",
        }), 500

    session.pop(SESION_LOTE, None)
    session.modified = True
    return jsonify({
        "ok": True,
        "mensaje": f"Se registraron {len(creados)} reportes de monitoreo correctamente.",
        "cantidad": len(creados),
        "redirect_url": url_for("coordinacion.listado", tipo="MONITOREO"),
    })


@coordinacion_bp.get("/monitoreo/masivo/estado-sp")
@login_required
def estado_sp_monitoreo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    lote = _validar_lote_id(request.args.get("lote_id"))
    if lote is None:
        return jsonify({"ok": False, "mensaje": "El lote ya no está activo."}), 409

    no_sp = _texto(request.args.get("no_sp"), 60)
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({"ok": False, "mensaje": "El SP indicado no existe o no está activo."}), 404

    return jsonify({"ok": True, **_estado_masivo(expediente, lote)})


@coordinacion_bp.post("/monitoreo/masivo/rectificar")
@login_required
def rectificar_monitoreo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    lote = _validar_lote_id(datos.get("lote_id"))
    if lote is None:
        return jsonify({"ok": False, "mensaje": "El lote ya no está activo."}), 409
    if datos.get("confirmado") is not True:
        return jsonify({
            "ok": False,
            "mensaje": "Debe confirmar la verificación física/File Server antes de guardar.",
        }), 400

    no_sp = _texto(datos.get("no_sp"), 60)
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({"ok": False, "mensaje": "El SP indicado no existe o no está activo."}), 404

    total_folios = _entero(datos.get("total_folios"))
    total_anexos = _entero(datos.get("total_anexos"))
    if total_folios is None or total_folios < 1:
        return jsonify({"ok": False, "mensaje": "El total de folios debe ser mayor que cero."}), 400
    if total_anexos is None or total_anexos < 0 or total_anexos > MAX_ANEXOS_MONITOREO:
        return jsonify({
            "ok": False,
            "mensaje": f"El total de anexos debe estar entre 0 y {MAX_ANEXOS_MONITOREO}.",
        }), 400

    estado_anexos = _estado_anexos(expediente)
    if total_anexos < estado_anexos["minimo_conocido"]:
        return jsonify({
            "ok": False,
            "mensaje": (
                f"SICODE ya tiene evidencia de al menos {estado_anexos['minimo_conocido']} anexo(s) "
                "para este SP. Verifique el expediente y corrija el total."
            ),
        }), 400

    anteriores = {
        "folios_rectificados": expediente.folios_rectificados,
        "anexos_rectificados": expediente.anexos_rectificados,
        "rectificado_por_id": expediente.rectificado_por_id,
    }
    expediente.folios_rectificados = total_folios
    expediente.anexos_rectificados = total_anexos
    expediente.rectificado_en = datetime.utcnow()
    expediente.rectificado_por_id = current_user.id

    registrar_bitacora(
        accion="RECTIFICAR_EXPEDIENTE_MONITOREO_MASIVO",
        modulo="Coordinación",
        descripcion=(
            f"Rectificación para lote masivo de monitoreo. SP {expediente.no_sp}: "
            f"{total_folios} folios y {total_anexos} anexos antes de incorporar los reportes del lote."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="Expediente",
        entidad_id=expediente.id,
        datos_anteriores=anteriores,
        datos_posteriores={
            "folios_rectificados": total_folios,
            "anexos_rectificados": total_anexos,
            "rectificado_por_id": current_user.id,
            "origen": "Registro masivo de reportes de monitoreo",
        },
        motivo="Rectificación obligatoria previa a registro masivo de monitoreo",
        commit=False,
    )
    db.session.commit()

    rectificados = dict(lote.get("rectificados") or {})
    rectificados[str(expediente.id)] = {
        "folios": total_folios,
        "anexos": total_anexos,
        "rectificado_en": expediente.rectificado_en.isoformat(),
    }
    lote = {"id": lote["id"], "rectificados": rectificados}
    session[SESION_LOTE] = lote
    session.modified = True

    return jsonify({
        "ok": True,
        "mensaje": (
            f"SP {expediente.no_sp} rectificado: {total_folios} folios y "
            f"{total_anexos} anexos."
        ),
        **_estado_masivo(expediente, lote),
    })
