import json
from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.forms.coordinacion_form import _normalizar_referencia
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.routes.admin import admin_bp, admin_required
from app.routes.anexos_inteligentes import _titulo_reemplazo
from app.routes.monitoreo_anexos import _actualizar_secuencia_vigente, _entero_anexo, _validar_numero
from app.services.bitacora_service import registrar_bitacora
from app.services.catalogo_anexos_service import COMPONENTES_REEMPLAZO, catalogo_plano
from app.services.coordinacion_service import determinar_estado, resolver_expediente


SCHEMA_ASISTIDO = "sicode.anexos_asistidos.v1"
MAX_REGISTROS_LOTE = 200
ORIGEN_REGISTRO = "GPT_DRIVE"
HOJA_ORIGEN = "ANEXOS_ASISTIDOS"


def _texto(valor, maximo=None):
    texto = str(valor or "").strip()
    if maximo is not None and len(texto) > maximo:
        return None
    return texto or None


def _fecha(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _payload_desde_texto(texto):
    try:
        datos = json.loads(texto or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "El contenido no es JSON válido."

    if not isinstance(datos, dict):
        return None, "El JSON debe contener un objeto principal."
    if datos.get("schema") != SCHEMA_ASISTIDO:
        return None, f"El schema debe ser {SCHEMA_ASISTIDO}."

    lote = _texto(datos.get("lote"), 64)
    if not lote:
        return None, "El lote es obligatorio y debe tener como máximo 64 caracteres."

    registros = datos.get("registros")
    if not isinstance(registros, list) or not registros:
        return None, "El JSON debe incluir al menos un registro."
    if len(registros) > MAX_REGISTROS_LOTE:
        return None, f"El lote supera el máximo de {MAX_REGISTROS_LOTE} registros."

    return datos, None


def _referencia_archivo(registro):
    carpeta = _texto(registro.get("carpeta_fuente")) or "Sin carpeta"
    archivos = registro.get("archivos_fuente") or []
    if not isinstance(archivos, list):
        archivos = []
    nombres = [str(item).strip() for item in archivos if str(item).strip()]
    detalle = carpeta
    if nombres:
        detalle += " | " + ", ".join(nombres)
    return detalle[:255]


def _fila_importada(lote, fila):
    return RegistroCoordinacion.query.filter_by(
        lote_importacion=lote,
        hoja_origen=HOJA_ORIGEN,
        fila_origen=fila,
    ).first()


def _validar_registro(registro, lote, fila, numero_override=None, exigir_numero=False):
    errores = []
    advertencias = []

    if not isinstance(registro, dict):
        return {
            "estado": "BLOQUEADO",
            "errores": ["La fila no contiene un objeto JSON válido."],
            "advertencias": [],
            "fila": fila,
        }

    no_sp = _texto(registro.get("no_sp"), 50)
    expediente = None
    no_sp_norm = no_sp
    if not no_sp:
        errores.append("Falta No. de SP.")
    else:
        expediente, no_sp_norm = resolver_expediente(no_sp)
        if not expediente:
            errores.append("El SP no existe o no está activo en SICODE.")

    codigo = _texto(registro.get("tipo_codigo"), 80)
    codigo = codigo.upper() if codigo else None
    definicion = catalogo_plano().get(codigo) if codigo else None
    if not definicion:
        errores.append("Tipo de anexo no reconocido por el catálogo oficial.")
    elif codigo != "REEMPLAZO_COMPONENTES":
        errores.append("Esta primera versión del módulo admite únicamente REEMPLAZO_COMPONENTES.")

    permitidos = {codigo for codigo, _etiqueta in COMPONENTES_REEMPLAZO}
    componentes_crudos = registro.get("componentes") or []
    componentes = []
    if not isinstance(componentes_crudos, list):
        errores.append("El campo componentes debe ser una lista.")
    else:
        for valor in componentes_crudos:
            codigo_comp = str(valor or "").strip().upper()
            if codigo_comp and codigo_comp not in permitidos:
                errores.append(f"Componente no permitido: {codigo_comp}.")
            elif codigo_comp and codigo_comp not in componentes:
                componentes.append(codigo_comp)
    titulo = _titulo_reemplazo(componentes)
    if not titulo:
        errores.append("Seleccione al menos un componente reemplazado.")

    tipo_referencia = (_texto(registro.get("tipo_referencia"), 2) or "RC").upper()
    if tipo_referencia not in {"RC", "RE"}:
        errores.append("Tipo de referencia inválido; use RC o RE.")

    rc_crudo = _texto(registro.get("rc"), 80)
    rc = _normalizar_referencia(tipo_referencia, rc_crudo)
    if not rc:
        errores.append("Falta el número RC / RE.")

    providencia = _texto(registro.get("providencia"), 120)
    if registro.get("providencia") and providencia is None:
        errores.append("La providencia supera 120 caracteres.")
    if not providencia:
        errores.append("Falta la providencia.")

    fecha_recepcion = _fecha(registro.get("fecha_recepcion"))
    if not fecha_recepcion:
        errores.append("Falta una fecha de recepción válida (AAAA-MM-DD).")

    persona_entrega = _texto(registro.get("persona_entrega"), 180)
    if registro.get("persona_entrega") and persona_entrega is None:
        errores.append("Quién entrega / remite supera 180 caracteres.")

    folios = _texto(registro.get("folios_recepcion"), 80)
    if registro.get("folios_recepcion") and folios is None:
        errores.append("Folios recibidos supera 80 caracteres.")

    observaciones = _texto(registro.get("observaciones"))
    es_vencido = bool(registro.get("es_vencido", False))

    numero_crudo = numero_override if numero_override not in (None, "") else registro.get("numero_anexo")
    numero = _entero_anexo(numero_crudo)
    if numero is None:
        if exigir_numero:
            errores.append("Debe indicar el No. de anexo verificado en File Server.")
        else:
            advertencias.append("Pendiente confirmar No. de anexo en File Server.")
    elif expediente:
        _estado_sp, error_numero = _validar_numero(expediente, numero, es_vencido)
        if error_numero:
            errores.append(error_numero)

    if _fila_importada(lote, fila):
        errores.append("Esta fila del lote ya fue importada anteriormente.")

    estado = "BLOQUEADO" if errores else ("REVISAR" if advertencias else "LISTO")
    return {
        "estado": estado,
        "errores": errores,
        "advertencias": advertencias,
        "fila": fila,
        "no_sp": no_sp_norm,
        "expediente": expediente,
        "codigo": codigo,
        "definicion": definicion,
        "componentes": componentes,
        "titulo": titulo,
        "tipo_referencia": tipo_referencia,
        "rc": rc,
        "providencia": providencia,
        "fecha_recepcion": fecha_recepcion,
        "persona_entrega": persona_entrega,
        "folios": folios,
        "observaciones": observaciones,
        "numero_anexo": numero,
        "es_vencido": es_vencido,
        "carpeta_fuente": _texto(registro.get("carpeta_fuente"), 180),
        "archivo_origen": _referencia_archivo(registro),
        "original": registro,
    }


def _preparar_vista(payload, numeros=None, exigir_numero=False):
    numeros = numeros or {}
    lote = payload["lote"]
    filas = []
    for indice, registro in enumerate(payload["registros"]):
        fila = indice + 1
        override = numeros.get(str(indice))
        filas.append(_validar_registro(
            registro,
            lote,
            fila,
            numero_override=override,
            exigir_numero=exigir_numero,
        ))
    return filas


@admin_bp.get("/anexos-asistidos")
@login_required
@admin_required
def anexos_asistidos():
    return render_template(
        "admin/anexos_asistidos.html",
        payload_texto="",
        filas=[],
        lote=None,
    )


@admin_bp.post("/anexos-asistidos/validar")
@login_required
@admin_required
def validar_anexos_asistidos():
    payload_texto = request.form.get("payload_json") or ""
    payload, error = _payload_desde_texto(payload_texto)
    if error:
        flash(error, "danger")
        return render_template(
            "admin/anexos_asistidos.html",
            payload_texto=payload_texto,
            filas=[],
            lote=None,
        ), 400

    filas = _preparar_vista(payload)
    return render_template(
        "admin/anexos_asistidos.html",
        payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
        filas=filas,
        lote=payload["lote"],
    )


@admin_bp.post("/anexos-asistidos/registrar")
@login_required
@admin_required
def registrar_anexos_asistidos():
    payload_texto = request.form.get("payload_json") or ""
    payload, error = _payload_desde_texto(payload_texto)
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.anexos_asistidos"))

    if request.form.get("confirmacion_file_server") != "1":
        flash("Debe confirmar que verificó los números de anexo en File Server.", "danger")
        filas = _preparar_vista(payload)
        return render_template(
            "admin/anexos_asistidos.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
        ), 400

    seleccionados = []
    for valor in request.form.getlist("seleccionados"):
        try:
            indice = int(valor)
        except (TypeError, ValueError):
            continue
        if 0 <= indice < len(payload["registros"]) and indice not in seleccionados:
            seleccionados.append(indice)

    if not seleccionados:
        flash("Seleccione al menos un registro para importar.", "warning")
        filas = _preparar_vista(payload)
        return render_template(
            "admin/anexos_asistidos.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
        ), 400

    numeros = {str(i): request.form.get(f"numero_anexo_{i}") for i in seleccionados}
    filas_todas = _preparar_vista(payload, numeros=numeros, exigir_numero=False)
    filas_seleccionadas = []
    hay_errores = False
    for indice in seleccionados:
        fila = _validar_registro(
            payload["registros"][indice],
            payload["lote"],
            indice + 1,
            numero_override=numeros.get(str(indice)),
            exigir_numero=True,
        )
        filas_todas[indice] = fila
        filas_seleccionadas.append(fila)
        hay_errores = hay_errores or bool(fila["errores"])

    if hay_errores:
        db.session.rollback()
        flash("No se registró el lote: corrija los registros bloqueados y vuelva a intentar.", "danger")
        return render_template(
            "admin/anexos_asistidos.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas_todas,
            lote=payload["lote"],
            seleccionados_previos=set(seleccionados),
        ), 400

    creados = []
    try:
        for fila in filas_seleccionadas:
            expediente = fila["expediente"]
            numero = fila["numero_anexo"]

            # Revalidación dentro de la misma transacción: protege la secuencia si
            # el lote contiene más de un anexo para el mismo SP.
            _estado_sp, error_numero = _validar_numero(expediente, numero, fila["es_vencido"])
            if error_numero:
                raise ValueError(f"SP {expediente.no_sp}: {error_numero}")

            estado = determinar_estado(
                expediente,
                fila["no_sp"],
                campos_clave=[
                    fila["no_sp"], fila["rc"], fila["providencia"],
                    fila["titulo"], fila["fecha_recepcion"], numero,
                ],
            )
            registro = RegistroCoordinacion(
                tipo="ANEXO",
                expediente_id=expediente.id,
                no_sp_referencia=fila["no_sp"],
                rc=fila["rc"],
                providencia=fila["providencia"],
                fecha_recepcion=fila["fecha_recepcion"],
                persona_entrega=fila["persona_entrega"],
                folios_recepcion=fila["folios"],
                usuario_id=current_user.id,
                usuario_origen=current_user.nombre,
                estado=estado,
                observaciones=fila["observaciones"],
                origen_registro=ORIGEN_REGISTRO,
                archivo_origen=fila["archivo_origen"],
                lote_importacion=payload["lote"],
                hoja_origen=HOJA_ORIGEN,
                fila_origen=fila["fila"],
            )
            db.session.add(registro)
            db.session.flush()

            anexo = AnexoCoordinacion(
                registro_id=registro.id,
                tipo_anexo=fila["definicion"]["titulo"][:120],
                titulo=fila["titulo"][:180],
                folios=fila["folios"],
                escaneado=False,
                numero_anexo=str(numero),
                es_vencido=fila["es_vencido"],
            )
            db.session.add(anexo)

            total_anterior = _actualizar_secuencia_vigente(expediente, numero, fila["es_vencido"])
            registrar_bitacora(
                accion="IMPORTAR_ANEXO_ASISTIDO",
                modulo="Administración / Anexos",
                descripcion=(
                    f"Se importó {fila['titulo']} como Anexo {numero} del SP {expediente.no_sp} "
                    f"desde el lote {payload['lote']}."
                ),
                usuario_id=current_user.id,
                expediente_id=expediente.id,
                entidad="RegistroCoordinacion",
                entidad_id=registro.id,
                datos_posteriores={
                    "origen": ORIGEN_REGISTRO,
                    "lote": payload["lote"],
                    "fila": fila["fila"],
                    "sp": expediente.no_sp,
                    "numero_anexo": numero,
                    "titulo": fila["titulo"],
                    "componentes": fila["componentes"],
                    "es_vencido": fila["es_vencido"],
                    "confirmacion_file_server_declarada": True,
                    "total_anterior": total_anterior,
                    "total_actual": expediente.anexos_rectificados,
                },
                commit=False,
            )
            creados.append(registro)

        registrar_bitacora(
            accion="IMPORTAR_LOTE_ANEXOS_ASISTIDOS",
            modulo="Administración / Anexos",
            descripcion=(
                f"Se importaron {len(creados)} anexo(s) desde el lote {payload['lote']} "
                f"mediante carga asistida GPT/Drive."
            ),
            usuario_id=current_user.id,
            entidad="LoteAnexosAsistidos",
            entidad_id=payload["lote"],
            datos_posteriores={
                "lote": payload["lote"],
                "cantidad": len(creados),
                "origen": ORIGEN_REGISTRO,
            },
            commit=False,
        )
        db.session.commit()
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        flash(f"No se importó el lote. {exc}", "danger")
        filas = _preparar_vista(payload, numeros=numeros)
        return render_template(
            "admin/anexos_asistidos.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
        ), 409

    flash(f"Se registraron correctamente {len(creados)} anexo(s) del lote {payload['lote']}.", "success")
    return redirect(url_for("admin.anexos_asistidos"))
