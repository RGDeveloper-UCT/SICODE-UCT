"""SICODEIAV3: puerta de entrada controlada para archivos fabricados por el asistente.

Flujo esperado:
Google Drive -> Gemini (lectura documental) -> ChatGPT/SICODEIAV3 (traducción y
normalización) -> archivo sicode.iav3.import.v1 -> este módulo -> validación
humana -> persistencia en SICODE.

El archivo se procesa en memoria y nunca se conserva en el servidor.
"""

from __future__ import annotations

import hashlib
import json

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.routes.admin import admin_bp, admin_required
from app.routes import admin_anexos_asistidos as motor
from app.services.bitacora_service import registrar_bitacora


SCHEMA_SICODEIAV3 = "sicode.iav3.import.v1"
GENERADOR_SICODEIAV3 = "SICODEIAV3"
MAX_ARCHIVO_BYTES = 4 * 1024 * 1024
MAX_REGISTROS = motor.MAX_REGISTROS_LOTE
ORIGEN_REGISTRO = "SICODEIAV3"
HOJA_ORIGEN = "SICODEIAV3"

# El motor existente conserva todas las reglas de negocio. Cambiamos solamente
# la procedencia de los registros que se creen a través de esta nueva puerta.
motor.ORIGEN_REGISTRO = ORIGEN_REGISTRO
motor.HOJA_ORIGEN = HOJA_ORIGEN


def _texto(valor, maximo=None):
    if valor is None:
        return None
    dato = str(valor).strip()
    if not dato:
        return None
    if maximo is not None and len(dato) > maximo:
        return None
    return dato


def _json_estricto(texto):
    try:
        return json.loads(texto or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _payload_sicodeiav3_desde_texto(texto):
    """Valida el sobre final. No acepta directamente la respuesta de Gemini."""
    datos = _json_estricto(texto)
    if not isinstance(datos, dict):
        return None, "El archivo no contiene un objeto JSON válido."

    if datos.get("schema") != SCHEMA_SICODEIAV3:
        return None, (
            f"El archivo debe usar el schema {SCHEMA_SICODEIAV3}. "
            "No pegue la respuesta de Gemini directamente: primero debe ser traducida por SICODEIAV3."
        )

    if (_texto(datos.get("generado_por"), 40) or "").upper() != GENERADOR_SICODEIAV3:
        return None, "El archivo debe declarar generado_por = SICODEIAV3."

    lote = _texto(datos.get("lote"), 64)
    if not lote:
        return None, "El lote es obligatorio y debe tener como máximo 64 caracteres."

    registros = datos.get("registros")
    if not isinstance(registros, list) or not registros:
        return None, "El archivo debe contener al menos un registro."
    if len(registros) > MAX_REGISTROS:
        return None, f"El archivo supera el máximo de {MAX_REGISTROS} registros."

    control = datos.get("control") if isinstance(datos.get("control"), dict) else {}
    total_declarado = control.get("total_registros")
    try:
        total_declarado = int(total_declarado)
    except (TypeError, ValueError):
        return None, "control.total_registros es obligatorio y debe ser numérico."
    if total_declarado != len(registros):
        return None, (
            f"El archivo declara {total_declarado} registro(s), pero contiene {len(registros)}. "
            "Esto puede indicar que el archivo fue truncado o modificado."
        )

    # La traducción final debe ser explícita: no aceptamos filas sueltas que el
    # motor tendría que adivinar.
    for indice, registro in enumerate(registros, start=1):
        if not isinstance(registro, dict):
            return None, f"La fila {indice} no es un objeto JSON."
        if not _texto(registro.get("clase_registro"), 40):
            return None, f"La fila {indice} no define clase_registro."
        if not _texto(registro.get("no_sp"), 50):
            return None, f"La fila {indice} no define no_sp."
        if registro.get("clase_registro", "").upper() in motor.CLASES_CON_SECUENCIA_ANEXO:
            anexo = registro.get("anexo")
            if not isinstance(anexo, dict):
                return None, f"La fila {indice} requiere el objeto anexo."

    normalizado = {
        "schema": SCHEMA_SICODEIAV3,
        "generado_por": GENERADOR_SICODEIAV3,
        "lote": lote,
        "creado_en": _texto(datos.get("creado_en"), 40),
        "origen_lectura": datos.get("origen_lectura") if isinstance(datos.get("origen_lectura"), dict) else {},
        "control": {"total_registros": len(registros)},
        "registros": registros,
    }
    return normalizado, None


def _payload_motor(payload):
    """Convierte el contrato estable V3 al contrato interno ya probado."""
    origen = payload.get("origen_lectura") or {}
    puente = {
        "schema": motor.SCHEMA_GEMINIASSIST,
        "lote": payload["lote"],
        "origen": {
            "proveedor": origen.get("proveedor") or "GEMINI",
            "fuente": origen.get("fuente") or "GOOGLE_DRIVE",
            "carpeta": origen.get("carpeta"),
            "traductor": GENERADOR_SICODEIAV3,
        },
        "registros": payload["registros"],
    }
    datos, error = motor._payload_desde_texto(json.dumps(puente, ensure_ascii=False))
    if error:
        return None, error
    return datos, None


def _huella(payload):
    canonico = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:16].upper()


def _leer_entrada():
    archivo = request.files.get("archivo_json")
    if archivo and archivo.filename:
        nombre = archivo.filename.strip()
        if not nombre.lower().endswith(".json"):
            return None, None, "El archivo debe tener extensión .json."
        bruto = archivo.stream.read(MAX_ARCHIVO_BYTES + 1)
        if len(bruto) > MAX_ARCHIVO_BYTES:
            return None, None, "El archivo JSON supera el máximo permitido de 4 MB."
        try:
            return bruto.decode("utf-8-sig"), nombre, None
        except UnicodeDecodeError:
            return None, None, "El archivo debe estar codificado en UTF-8."

    texto = request.form.get("payload_json") or ""
    if texto.strip():
        if len(texto.encode("utf-8")) > MAX_ARCHIVO_BYTES:
            return None, None, "El JSON pegado supera el máximo permitido de 4 MB."
        return texto, "pegado-manual.json", None

    return None, None, "Seleccione el archivo .json fabricado por SICODEIAV3 o pegue su contenido."


def _render(payload_texto="", filas=None, lote=None, archivo_nombre=None, huella=None, status=200, seleccionados_previos=None):
    return render_template(
        "admin/sicodeiav3.html",
        payload_texto=payload_texto,
        filas=filas or [],
        lote=lote,
        archivo_nombre=archivo_nombre,
        huella=huella,
        schema_sicodeiav3=SCHEMA_SICODEIAV3,
        seleccionados_previos=seleccionados_previos,
    ), status


@admin_bp.get("/sicodeiav3")
@login_required
@admin_required
def sicodeiav3():
    return _render()[0]


@admin_bp.post("/sicodeiav3/validar")
@login_required
@admin_required
def validar_sicodeiav3():
    texto, nombre, error = _leer_entrada()
    if error:
        flash(error, "danger")
        return _render(status=400)

    payload, error = _payload_sicodeiav3_desde_texto(texto)
    if error:
        flash(error, "danger")
        return _render(payload_texto=texto or "", archivo_nombre=nombre, status=400)

    interno, error = _payload_motor(payload)
    if error:
        flash(error, "danger")
        return _render(payload_texto=json.dumps(payload, ensure_ascii=False, indent=2), archivo_nombre=nombre, status=400)

    filas = motor._agregar_resumenes(motor._preparar_vista(interno))
    return _render(
        payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
        filas=filas,
        lote=payload["lote"],
        archivo_nombre=nombre,
        huella=_huella(payload),
    )[0]


@admin_bp.post("/sicodeiav3/registrar")
@login_required
@admin_required
def registrar_sicodeiav3():
    payload, error = _payload_sicodeiav3_desde_texto(request.form.get("payload_json") or "")
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.sicodeiav3"))

    interno, error = _payload_motor(payload)
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.sicodeiav3"))

    seleccionados = []
    for valor in request.form.getlist("seleccionados"):
        try:
            indice = int(valor)
        except (TypeError, ValueError):
            continue
        if 0 <= indice < len(interno["registros"]) and indice not in seleccionados:
            seleccionados.append(indice)

    if not seleccionados:
        flash("Seleccione al menos un registro para importar.", "warning")
        filas = motor._agregar_resumenes(motor._preparar_vista(interno))
        return _render(
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
            huella=_huella(payload),
            status=400,
        )[0], 400

    numeros = {str(i): request.form.get(f"numero_anexo_{i}") for i in seleccionados}
    filas_todas = motor._preparar_vista(interno, numeros=numeros, exigir_numero=False)
    filas_seleccionadas = []
    hay_errores = False
    requiere_file_server = False

    for indice in seleccionados:
        clase = interno["registros"][indice].get("clase_registro")
        fila = motor._validar_registro(
            interno["registros"][indice],
            interno["lote"],
            indice + 1,
            numero_override=numeros.get(str(indice)),
            exigir_numero=clase in motor.CLASES_CON_SECUENCIA_ANEXO,
        )
        filas_todas[indice] = fila
        filas_seleccionadas.append(fila)
        hay_errores = hay_errores or bool(fila["errores"])
        requiere_file_server = requiere_file_server or fila["clase"] in motor.CLASES_CON_SECUENCIA_ANEXO

    if requiere_file_server and request.form.get("confirmacion_file_server") != "1":
        flash("Confirme que verificó en File Server los números de los anexos seleccionados.", "danger")
        filas_todas = motor._agregar_resumenes(filas_todas)
        return _render(
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas_todas,
            lote=payload["lote"],
            huella=_huella(payload),
            status=400,
            seleccionados_previos=set(seleccionados),
        )[0], 400

    if hay_errores:
        db.session.rollback()
        flash("No se registró el lote: corrija los registros bloqueados y vuelva a validar.", "danger")
        filas_todas = motor._agregar_resumenes(filas_todas)
        return _render(
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas_todas,
            lote=payload["lote"],
            huella=_huella(payload),
            status=400,
            seleccionados_previos=set(seleccionados),
        )[0], 400

    creados = []
    try:
        for fila in sorted(filas_seleccionadas, key=motor._clave_orden_importacion):
            registro = motor._crear_base_desde_fila(fila, payload["lote"])
            total_anterior = None
            if fila["clase"] == "ANEXO":
                total_anterior = motor._guardar_anexo(fila, registro)
            elif fila["clase"] == "MONITOREO":
                total_anterior = motor._guardar_monitoreo(fila, registro)
            elif fila["clase"] == "ANALISIS_RIESGO":
                total_anterior = motor._guardar_analisis(fila, registro)
            elif fila["clase"] == "PAGO":
                motor._guardar_pago(fila, registro)
            elif fila["clase"] in {"INSTALACION", "DESINSTALACION"}:
                motor._guardar_movimiento(fila, registro)
            else:
                raise ValueError(f"Clase no implementada: {fila['clase']}")

            registrar_bitacora(
                accion=f"IMPORTAR_SICODEIAV3_{fila['clase']}",
                modulo="Administración / SICODEIAV3",
                descripcion=(
                    f"SICODEIAV3 importó {fila['clase']} del SP {fila['no_sp']} "
                    f"desde el lote {payload['lote']} (fila {fila['fila']})."
                ),
                usuario_id=current_user.id,
                expediente_id=fila["expediente"].id if fila["expediente"] else None,
                entidad="RegistroCoordinacion",
                entidad_id=registro.id,
                datos_posteriores={
                    "origen": ORIGEN_REGISTRO,
                    "lote": payload["lote"],
                    "fila": fila["fila"],
                    "clase": fila["clase"],
                    "sp": fila["no_sp"],
                    "numero_anexo": fila.get("numero_anexo"),
                    "es_vencido": fila.get("es_vencido", False),
                    "confirmacion_file_server_declarada": bool(requiere_file_server),
                    "total_anterior": total_anterior,
                    "total_actual": fila["expediente"].anexos_rectificados if fila.get("expediente") else None,
                    "fuente": fila["archivo_origen"],
                    "huella_archivo": _huella(payload),
                },
                commit=False,
            )
            creados.append(registro)

        registrar_bitacora(
            accion="IMPORTAR_LOTE_SICODEIAV3",
            modulo="Administración / SICODEIAV3",
            descripcion=(
                f"Se importaron {len(creados)} registro(s) desde el lote {payload['lote']} "
                f"mediante archivo fabricado por SICODEIAV3."
            ),
            usuario_id=current_user.id,
            entidad="LoteSICODEIAV3",
            entidad_id=payload["lote"],
            datos_posteriores={
                "lote": payload["lote"],
                "cantidad": len(creados),
                "origen": ORIGEN_REGISTRO,
                "clases": sorted({fila["clase"] for fila in filas_seleccionadas}),
                "huella_archivo": _huella(payload),
            },
            commit=False,
        )
        db.session.commit()
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        flash(f"No se importó el lote. {exc}", "danger")
        filas = motor._agregar_resumenes(motor._preparar_vista(interno, numeros=numeros))
        return _render(
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
            huella=_huella(payload),
            status=409,
        )[0], 409

    flash(
        f"SICODEIAV3 registró correctamente {len(creados)} registro(s) del lote {payload['lote']}.",
        "success",
    )
    return redirect(url_for("admin.sicodeiav3"))
