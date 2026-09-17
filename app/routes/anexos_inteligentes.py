from datetime import datetime
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.forms.coordinacion_form import _normalizar_referencia
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import AnalisisRiesgo, AnexoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.routes.coordinacion import _crear_base, _sp_opciones
from app.routes.monitoreo_anexos import (
    MAX_ANEXOS_MONITOREO,
    _actualizar_secuencia_vigente,
    _anexo_coordinacion_existente,
    _anexo_rectificado_existente,
    _entero_anexo,
    _estado_anexos,
    _validar_numero,
)
from app.services.bitacora_service import registrar_bitacora
from app.services.catalogo_anexos_service import (
    CATEGORIAS_ANEXOS,
    COMPONENTES_REEMPLAZO,
    catalogo_plano,
    descubrir_tipos_nexo,
)
from app.services.coordinacion_service import resolver_expediente


anexos_inteligentes_bp = Blueprint(
    "anexos_inteligentes",
    __name__,
    url_prefix="/coordinacion/anexos",
)

MAX_FILAS_ANALISIS_RIESGO_MASIVO = 100


def _fecha(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _texto_limitado(nombre, maximo, *, requerido=False):
    valor = (request.form.get(nombre) or "").strip()
    if requerido and not valor:
        return None, f"El campo {nombre} es obligatorio."
    if len(valor) > maximo:
        return None, f"El campo {nombre} supera el máximo permitido de {maximo} caracteres."
    return valor or None, None


def _sugerencias_nexo_seguras():
    try:
        return descubrir_tipos_nexo()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("NEXO no pudo revisar tipos de anexo no catalogados")
        return []


def _titulo_reemplazo(componentes):
    etiquetas = dict(COMPONENTES_REEMPLAZO)
    nombres = [etiquetas[codigo] for codigo in componentes if codigo in etiquetas]
    if not nombres:
        return None
    if len(nombres) == 1:
        detalle = nombres[0]
    elif len(nombres) == 2:
        detalle = " y ".join(nombres)
    else:
        detalle = ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return f"Reemplazo de {detalle}"


def _datos_catalogo_para_vista():
    catalogo = []
    for categoria in CATEGORIAS_ANEXOS:
        item = dict(categoria)
        item["tipos"] = [
            {"codigo": codigo, "titulo": titulo, "modo": modo}
            for codigo, titulo, modo in categoria["tipos"]
        ]
        catalogo.append(item)
    return catalogo


def _analisis_riesgo_existente(correlativo):
    """Busca el correlativo globalmente para impedir duplicar el mismo documento."""
    return (
        db.session.query(AnalisisRiesgo, RegistroCoordinacion.no_sp_referencia)
        .join(RegistroCoordinacion, AnalisisRiesgo.registro_id == RegistroCoordinacion.id)
        .filter(
            func.lower(func.trim(AnalisisRiesgo.correlativo))
            == correlativo.strip().lower()
        )
        .first()
    )


def _resultado_lote(indice, fila):
    return {
        "id": str(fila.get("id") or indice + 1)[:80],
        "indice": indice,
        "fecha_recepcion": (fila.get("fecha_recepcion") or "").strip(),
        "correlativo": (fila.get("correlativo") or "").strip(),
        "no_sp": (fila.get("no_sp") or "").strip(),
        "es_vencido": fila.get("es_vencido") is True,
        "numero_anexo": _entero_anexo(fila.get("numero_anexo")),
        "valido": False,
        "estado": "error",
        "condicion": None,
        "mensaje": None,
        "expediente_id": None,
        "total_rectificado": None,
        "minimo_conocido": None,
    }


def _validar_lote_analisis_riesgo(filas):
    """Valida hasta 100 análisis sin escribir en base de datos.

    Los tres datos de captura son fecha, correlativo y SP. En modo normal el
    número de anexo se propone automáticamente usando la misma secuencia maestra
    del registro individual. Si el usuario identifica un documento histórico,
    debe confirmar su número físico original contra File Server.
    """
    if not isinstance(filas, list):
        return []

    resultados = []
    correlativos_lote = set()
    estados = {}
    totales_simulados = {}
    numeros_reservados = {}

    for indice, fila in enumerate(filas[:MAX_FILAS_ANALISIS_RIESGO_MASIVO]):
        if not isinstance(fila, dict):
            fila = {}
        resultado = _resultado_lote(indice, fila)
        resultados.append(resultado)

        fecha_texto = resultado["fecha_recepcion"]
        correlativo = resultado["correlativo"]
        no_sp = resultado["no_sp"]

        if not fecha_texto or not correlativo or not no_sp:
            resultado["mensaje"] = "Complete fecha de recibido, número de análisis y No. de SP."
            continue
        if len(correlativo) > 120:
            resultado["mensaje"] = "El número de análisis supera 120 caracteres."
            continue
        if len(no_sp) > 50:
            resultado["mensaje"] = "El No. de SP supera 50 caracteres."
            continue

        fecha_recepcion = _fecha(fecha_texto)
        if fecha_recepcion is None:
            resultado["mensaje"] = "La fecha de recibido no tiene un formato válido."
            continue

        expediente, _ = resolver_expediente(no_sp)
        if not expediente:
            resultado["mensaje"] = "El SP indicado no existe o no está activo en SICODE."
            continue

        resultado["expediente_id"] = expediente.id
        resultado["no_sp"] = expediente.no_sp
        clave_correlativo = correlativo.casefold()
        if clave_correlativo in correlativos_lote:
            resultado["mensaje"] = f"El análisis {correlativo} está repetido dentro de este lote."
            continue
        correlativos_lote.add(clave_correlativo)

        existente = _analisis_riesgo_existente(correlativo)
        if existente:
            sp_existente = existente[1] or "sin SP"
            resultado["mensaje"] = (
                f"El análisis {correlativo} ya está registrado en SICODE para el SP {sp_existente}."
            )
            continue

        if expediente.id not in estados:
            estados[expediente.id] = _estado_anexos(expediente)
        estado = estados[expediente.id]
        resultado["total_rectificado"] = estado["total_rectificado"]
        resultado["minimo_conocido"] = estado["minimo_conocido"]

        if estado["requiere_rectificacion"]:
            resultado["estado"] = "rectificacion"
            resultado["mensaje"] = (
                "Rectifique primero el total de anexos del SP contra File Server."
            )
            continue

        if expediente.id not in totales_simulados:
            totales_simulados[expediente.id] = estado["total_rectificado"] or 0
            numeros_reservados[expediente.id] = set()

        reservados = numeros_reservados[expediente.id]
        es_vencido = resultado["es_vencido"]

        if es_vencido:
            numero = resultado["numero_anexo"]
            _estado, error = _validar_numero(expediente, numero, True)
            if error:
                resultado["mensaje"] = error
                continue
            if numero in reservados:
                resultado["mensaje"] = (
                    f"El Anexo {numero} ya fue reservado por otra fila de este lote para el SP {expediente.no_sp}."
                )
                continue
            resultado["condicion"] = "Vencido / histórico"
            resultado["numero_anexo"] = numero
        else:
            numero = totales_simulados[expediente.id] + 1
            if numero < 1 or numero > MAX_ANEXOS_MONITOREO:
                resultado["mensaje"] = (
                    f"No es posible proponer otro anexo: el máximo configurado es {MAX_ANEXOS_MONITOREO}."
                )
                continue
            if numero in reservados or _anexo_coordinacion_existente(expediente, numero):
                resultado["mensaje"] = (
                    f"El Anexo {numero} ya está individualizado o reservado para este SP. "
                    "Rectifique la secuencia antes de continuar."
                )
                continue

            # La primera fila vigente de cada SP pasa además por el validador
            # utilizado por el formulario individual. Las siguientes simulan el
            # avance consecutivo dentro del mismo lote.
            if totales_simulados[expediente.id] == (estado["total_rectificado"] or 0):
                _estado, error = _validar_numero(expediente, numero, False)
                if error:
                    resultado["mensaje"] = error
                    continue

            resultado["condicion"] = "Nuevo / vigente"
            resultado["numero_anexo"] = numero
            totales_simulados[expediente.id] = numero

        reservados.add(numero)
        resultado["valido"] = True
        resultado["estado"] = "valido"
        resultado["mensaje"] = f"Se registrará como Anexo {numero} · {resultado['condicion']}."

    return resultados


def _crear_detalle_rectificado_masivo(expediente, numero, titulo, fecha_recepcion):
    if _anexo_rectificado_existente(expediente, numero):
        return
    db.session.add(
        AnexoRectificado(
            expediente_id=expediente.id,
            numero_anexo=str(numero),
            titulo=titulo,
            tipo_anexo="OTRO",
            fecha_recepcion=fecha_recepcion,
            escaneado=False,
            creado_por_id=current_user.id,
            activo=True,
        )
    )


@anexos_inteligentes_bp.get("/nuevo")
@login_required
def nuevo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    return render_template(
        "coordinacion/anexos_inteligentes.html",
        categorias=_datos_catalogo_para_vista(),
        componentes=COMPONENTES_REEMPLAZO,
        expedientes=_sp_opciones(),
        sugerencias_nexo=_sugerencias_nexo_seguras(),
        url_monitoreo=url_for("coordinacion.registrar", tipo="monitoreo"),
        url_analisis=url_for("coordinacion.registrar", tipo="analisis-riesgo"),
        url_analisis_masivo=url_for("anexos_inteligentes.analisis_riesgo_masivo"),
        url_estado_sp=url_for("monitoreo_anexos.estado_sp"),
    )


@anexos_inteligentes_bp.get("/analisis-riesgo/masivo")
@login_required
def analisis_riesgo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    return render_template(
        "coordinacion/analisis_riesgo_masivo.html",
        expedientes=_sp_opciones(),
        max_filas=MAX_FILAS_ANALISIS_RIESGO_MASIVO,
        url_validar=url_for("anexos_inteligentes.validar_analisis_riesgo_masivo"),
        url_guardar=url_for("anexos_inteligentes.guardar_analisis_riesgo_masivo"),
        url_rectificar=url_for("monitoreo_anexos.rectificar_anexos"),
    )


@anexos_inteligentes_bp.post("/analisis-riesgo/masivo/validar")
@login_required
def validar_analisis_riesgo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    filas = datos.get("filas")
    if not isinstance(filas, list):
        return jsonify({"ok": False, "mensaje": "El lote enviado no es válido.", "resultados": []}), 400
    if len(filas) > MAX_FILAS_ANALISIS_RIESGO_MASIVO:
        return jsonify({
            "ok": False,
            "mensaje": f"El lote admite como máximo {MAX_FILAS_ANALISIS_RIESGO_MASIVO} filas.",
            "resultados": [],
        }), 400

    resultados = _validar_lote_analisis_riesgo(filas)
    validos = sum(1 for fila in resultados if fila["valido"])
    rectificaciones = sum(1 for fila in resultados if fila["estado"] == "rectificacion")
    return jsonify({
        "ok": True,
        "resultados": resultados,
        "total": len(resultados),
        "validos": validos,
        "errores": len(resultados) - validos,
        "rectificaciones": rectificaciones,
    })


@anexos_inteligentes_bp.post("/analisis-riesgo/masivo/guardar")
@login_required
def guardar_analisis_riesgo_masivo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    datos = request.get_json(silent=True) or {}
    filas = datos.get("filas")
    if not isinstance(filas, list) or not filas:
        return jsonify({"ok": False, "mensaje": "No hay filas para guardar.", "resultados": []}), 400
    if len(filas) > MAX_FILAS_ANALISIS_RIESGO_MASIVO:
        return jsonify({
            "ok": False,
            "mensaje": f"El lote admite como máximo {MAX_FILAS_ANALISIS_RIESGO_MASIVO} filas.",
            "resultados": [],
        }), 400
    if datos.get("confirmacion_file_server") is not True:
        return jsonify({
            "ok": False,
            "mensaje": "Confirme que revisó la secuencia propuesta contra File Server antes de guardar.",
            "resultados": [],
        }), 400

    resultados = _validar_lote_analisis_riesgo(filas)
    validos = [fila for fila in resultados if fila["valido"]]
    rechazados = [fila for fila in resultados if not fila["valido"]]
    if not validos:
        return jsonify({
            "ok": False,
            "mensaje": "Ninguna fila está lista para guardar. Corrija o rectifique los registros indicados.",
            "resultados": resultados,
        }), 400

    lote = uuid4().hex
    guardados = []

    try:
        for fila in validos:
            expediente = db.session.get(Expediente, fila["expediente_id"])
            if not expediente or not expediente.activo:
                raise RuntimeError(f"El SP {fila['no_sp']} dejó de estar disponible durante el guardado.")

            numero = fila["numero_anexo"]
            es_vencido = fila["es_vencido"]
            fecha_recepcion = _fecha(fila["fecha_recepcion"])
            correlativo = fila["correlativo"]
            titulo = f"Análisis de riesgo Correlativo {correlativo}"[:180]

            registro = _crear_base(
                "ANALISIS_RIESGO",
                expediente.no_sp,
                None,
                None,
                fecha_recepcion,
                None,
                [expediente.no_sp, fecha_recepcion, correlativo, numero],
            )
            registro.origen_registro = "MASIVO"
            registro.lote_importacion = lote
            registro.hoja_origen = "ANALISIS_RIESGO_MASIVO"
            registro.fila_origen = fila["indice"] + 1

            db.session.add(
                AnalisisRiesgo(
                    registro_id=registro.id,
                    correlativo=correlativo,
                    tipo_evento=None,
                )
            )
            db.session.add(
                AnexoCoordinacion(
                    registro_id=registro.id,
                    tipo_anexo="ANÁLISIS DE RIESGO",
                    titulo=titulo,
                    escaneado=False,
                    numero_anexo=str(numero),
                    es_vencido=es_vencido,
                )
            )
            _crear_detalle_rectificado_masivo(
                expediente,
                numero,
                titulo,
                fecha_recepcion,
            )

            total_anterior = _actualizar_secuencia_vigente(
                expediente,
                numero,
                es_vencido,
            )
            registrar_bitacora(
                accion=(
                    "REGISTRAR_ANALISIS_RIESGO_COMO_ANEXO_VENCIDO"
                    if es_vencido
                    else "REGISTRAR_ANALISIS_RIESGO_COMO_ANEXO"
                ),
                modulo="Coordinación",
                descripcion=(
                    f"Registro masivo: análisis de riesgo {correlativo} del SP {expediente.no_sp} "
                    f"como Anexo {numero}. "
                    + (
                        f"ANEXO VENCIDO/HISTÓRICO; el total vigente permanece en {total_anterior}."
                        if es_vencido
                        else f"Total de anexos: {total_anterior} -> {numero}."
                    )
                ),
                usuario_id=current_user.id,
                expediente_id=expediente.id,
                entidad="RegistroCoordinacion",
                entidad_id=registro.id,
                datos_posteriores={
                    "tipo": "ANALISIS_RIESGO",
                    "sp": expediente.no_sp,
                    "numero_anexo": numero,
                    "es_vencido": es_vencido,
                    "correlativo_analisis": correlativo,
                    "origen_registro": "MASIVO",
                    "lote_importacion": lote,
                    "anexos_rectificados": expediente.anexos_rectificados,
                },
                commit=False,
            )
            guardados.append(fila["id"])

        registrar_bitacora(
            accion="REGISTRAR_ANALISIS_RIESGO_MASIVO",
            modulo="Coordinación",
            descripcion=(
                f"Lote masivo de análisis de riesgo {lote}: "
                f"{len(filas)} fila(s) recibida(s), {len(guardados)} registrada(s) y "
                f"{len(rechazados)} rechazada(s)."
            ),
            usuario_id=current_user.id,
            entidad="LoteAnalisisRiesgo",
            entidad_id=lote,
            datos_posteriores={
                "lote_importacion": lote,
                "total_recibido": len(filas),
                "total_registrado": len(guardados),
                "total_rechazado": len(rechazados),
            },
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("No fue posible guardar el lote masivo de análisis de riesgo")
        return jsonify({
            "ok": False,
            "mensaje": "No fue posible guardar el lote. No se aplicó ningún cambio.",
            "resultados": resultados,
        }), 500

    return jsonify({
        "ok": True,
        "mensaje": (
            f"Registro masivo procesado: {len(guardados)} análisis registrado(s); "
            f"{len(rechazados)} fila(s) requieren corrección."
        ),
        "lote": lote,
        "registrados": len(guardados),
        "rechazados": len(rechazados),
        "guardados": guardados,
        "resultados": rechazados,
    })


@anexos_inteligentes_bp.post("/guardar")
@login_required
def guardar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    codigo = (request.form.get("tipo_codigo") or "").strip().upper()
    definicion = catalogo_plano().get(codigo)
    if not definicion:
        flash("Seleccione un tipo de anexo válido.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    if codigo == "ANALISIS_RIESGO_MASIVO":
        return redirect(url_for("anexos_inteligentes.analisis_riesgo_masivo"))

    if definicion["modo"] == "especial":
        destino = "monitoreo" if codigo == "REPORTE_MONITOREO" else "analisis-riesgo"
        return redirect(url_for("coordinacion.registrar", tipo=destino))

    no_sp, error = _texto_limitado("no_sp", 50, requerido=True)
    if error:
        flash(error, "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        flash("El SP debe existir y estar activo para registrar el anexo.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    numero = _entero_anexo(request.form.get("numero_anexo"))
    es_vencido = request.form.get("anexo_vencido") == "1"
    if request.form.get("confirmacion_file_server") != "1":
        flash("Debe confirmar el número de anexo contra File Server.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    _estado, error = _validar_numero(expediente, numero, es_vencido)
    if error:
        flash(error, "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    titulo = definicion["titulo"]
    componentes = []
    if definicion["modo"] == "componentes":
        permitidos = {codigo for codigo, _etiqueta in COMPONENTES_REEMPLAZO}
        componentes = [
            valor for valor in request.form.getlist("componentes")
            if valor in permitidos
        ]
        titulo = _titulo_reemplazo(componentes)
        if not titulo:
            flash("Seleccione al menos un componente reemplazado.", "warning")
            return redirect(url_for("anexos_inteligentes.nuevo"))
    elif definicion["modo"] == "libre":
        titulo, error = _texto_limitado("titulo_otro", 180, requerido=True)
        if error:
            flash("Escriba un nombre válido para el tipo de anexo (máximo 180 caracteres).", "warning")
            return redirect(url_for("anexos_inteligentes.nuevo"))

    tipo_referencia = (request.form.get("tipo_referencia") or "RC").strip().upper()
    rc_crudo, error_rc = _texto_limitado("rc", 80)
    providencia, error_prov = _texto_limitado("providencia", 120)
    persona_entrega, error_entrega = _texto_limitado("persona_entrega", 180)
    folios, error_folios = _texto_limitado("folios", 80)
    for mensaje in (error_rc, error_prov, error_entrega, error_folios):
        if mensaje:
            flash(mensaje, "warning")
            return redirect(url_for("anexos_inteligentes.nuevo"))

    rc = _normalizar_referencia(tipo_referencia, rc_crudo)
    fecha_texto = (request.form.get("fecha_recepcion") or "").strip()
    fecha_recepcion = _fecha(fecha_texto)
    if fecha_texto and fecha_recepcion is None:
        flash("La fecha de recepción no tiene un formato válido.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    observaciones = (request.form.get("observaciones") or "").strip() or None

    registro = _crear_base(
        "ANEXO",
        no_sp,
        rc,
        providencia,
        fecha_recepcion,
        observaciones,
        [no_sp, rc, providencia, titulo, fecha_recepcion, numero],
    )
    # _crear_base obtiene persona_entrega/folios desde request.form; las variables
    # anteriores se validan aquí para que un POST manipulado no salte los límites.
    _ = persona_entrega

    anexo = AnexoCoordinacion(
        registro_id=registro.id,
        tipo_anexo=definicion["titulo"][:120],
        titulo=titulo[:180],
        folios=folios,
        escaneado=False,
        numero_anexo=str(numero),
        es_vencido=es_vencido,
    )
    db.session.add(anexo)

    total_anterior = _actualizar_secuencia_vigente(expediente, numero, es_vencido)
    registrar_bitacora(
        accion="REGISTRAR_ANEXO_CATALOGO_VENCIDO" if es_vencido else "REGISTRAR_ANEXO_CATALOGO",
        modulo="Coordinación",
        descripcion=(
            f"Se registró {titulo} como Anexo {numero} del SP {expediente.no_sp}. "
            + (
                f"Marcado como histórico; la secuencia vigente permanece en {total_anterior}."
                if es_vencido
                else f"Total de anexos {total_anterior} -> {numero}."
            )
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="RegistroCoordinacion",
        entidad_id=registro.id,
        datos_posteriores={
            "tipo": "ANEXO",
            "tipo_catalogo": codigo,
            "categoria": definicion["categoria"],
            "titulo": titulo,
            "componentes": componentes,
            "sp": expediente.no_sp,
            "numero_anexo": numero,
            "es_vencido": es_vencido,
            "confirmacion_file_server_declarada": True,
            "anexos_rectificados": expediente.anexos_rectificados,
        },
        commit=False,
    )
    db.session.commit()

    if es_vencido:
        flash(
            f"{titulo} registrado como ANEXO VENCIDO/HISTÓRICO {numero} del SP {expediente.no_sp}.",
            "warning",
        )
    else:
        flash(f"{titulo} registrado correctamente como Anexo {numero}.", "success")
    return redirect(url_for("coordinacion.detalle", registro_id=registro.id))
