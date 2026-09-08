"""GEMINIASSIST: ingreso asistido de metadatos leídos por Gemini/Drive.

El módulo nunca almacena los documentos fuente. Recibe únicamente metadatos,
los normaliza a un contrato estable, los valida contra SICODE y exige revisión
humana antes de persistirlos.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.forms.coordinacion_form import _normalizar_referencia
from app.models.anexo_rectificado import AnexoRectificado
from app.models.coordinacion import (
    AnalisisRiesgo,
    AnexoCoordinacion,
    MovimientoDispositivo,
    PagoCoordinacion,
    RegistroCoordinacion,
    ReporteMonitoreo,
)
from app.routes.admin import admin_bp, admin_required
from app.routes.anexos_inteligentes import _titulo_reemplazo
from app.routes.monitoreo_anexos import _actualizar_secuencia_vigente, _entero_anexo, _validar_numero
from app.services.bitacora_service import registrar_bitacora
from app.services.catalogo_anexos_service import COMPONENTES_REEMPLAZO, catalogo_plano
from app.services.coordinacion_service import determinar_estado, resolver_expediente


SCHEMA_GEMINIASSIST = "sicode.geminiassist.v1"
SCHEMA_LEGACY = "sicode.anexos_asistidos.v1"
# Alias temporal para integraciones antiguas que importaban esta constante.
SCHEMA_ASISTIDO = SCHEMA_GEMINIASSIST
MAX_REGISTROS_LOTE = 500
ORIGEN_REGISTRO = "GEMINIASSIST"
HOJA_ORIGEN = "GEMINIASSIST"
CLASES_SOPORTADAS = {"ANEXO", "PAGO", "MONITOREO", "ANALISIS_RIESGO", "INSTALACION", "DESINSTALACION"}
CLASES_CON_SECUENCIA_ANEXO = {"ANEXO", "MONITOREO", "ANALISIS_RIESGO"}


def _texto(valor, maximo=None):
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if maximo is not None and len(texto) > maximo:
        return None
    return texto


def _fecha(valor):
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _booleano(valor, predeterminado=False):
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return predeterminado
    texto = str(valor).strip().lower()
    if texto in {"1", "true", "si", "sí", "yes", "y"}:
        return True
    if texto in {"0", "false", "no", "n", ""}:
        return False
    return predeterminado


def _decimal(valor):
    if valor in (None, ""):
        return None
    try:
        numero = Decimal(str(valor).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return numero.quantize(Decimal("0.01"))


def _extraer_json(texto):
    """Tolera JSON puro, bloque ```json``` o una breve introducción de Gemini."""
    bruto = (texto or "").strip().lstrip("\ufeff")
    if not bruto:
        return None

    candidatos = [bruto]
    candidatos.extend(
        bloque.strip()
        for bloque in re.findall(r"```(?:json)?\s*(.*?)```", bruto, flags=re.IGNORECASE | re.DOTALL)
        if bloque.strip()
    )

    decoder = json.JSONDecoder()
    for candidato in candidatos:
        try:
            return json.loads(candidato)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        for posicion, caracter in enumerate(candidato):
            if caracter not in "{[":
                continue
            try:
                dato, _fin = decoder.raw_decode(candidato[posicion:])
                return dato
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    return None


def _fuente_normalizada(registro):
    fuente = registro.get("fuente") if isinstance(registro.get("fuente"), dict) else {}
    carpeta = _texto(fuente.get("carpeta"), 180) or _texto(registro.get("carpeta_fuente"), 180)
    archivos = fuente.get("archivos")
    if archivos is None:
        archivos = registro.get("archivos_fuente")
    if not isinstance(archivos, list):
        archivos = []
    archivos = [str(item).strip() for item in archivos if str(item or "").strip()]
    return {
        "carpeta": carpeta,
        "archivos": archivos[:100],
        "id_fuente": _texto(registro.get("id_fuente"), 120) or _texto(fuente.get("id"), 120),
    }


def _anexo_normalizado(registro):
    anexo = registro.get("anexo") if isinstance(registro.get("anexo"), dict) else {}
    return {
        "tipo_codigo": _texto(anexo.get("tipo_codigo"), 80) or _texto(registro.get("tipo_codigo"), 80),
        "numero_anexo": anexo.get("numero_anexo", registro.get("numero_anexo")),
        "es_vencido": _booleano(anexo.get("es_vencido", registro.get("es_vencido", False))),
        "titulo_otro": _texto(anexo.get("titulo_otro"), 180) or _texto(registro.get("titulo_otro"), 180),
        "componentes": anexo.get("componentes", registro.get("componentes", [])),
        "escaneado": _booleano(anexo.get("escaneado", False)),
        "fecha_escaneado": _texto(anexo.get("fecha_escaneado"), 10),
    }


def _normalizar_registro(registro):
    if not isinstance(registro, dict):
        return registro

    clase = (_texto(registro.get("clase_registro"), 40) or "ANEXO").upper().replace(" ", "_")
    anexo = _anexo_normalizado(registro)
    tipo_codigo = (anexo.get("tipo_codigo") or "").upper()
    if clase == "ANEXO" and tipo_codigo == "REPORTE_MONITOREO":
        clase = "MONITOREO"
    elif clase == "ANEXO" and tipo_codigo == "ANALISIS_RIESGO":
        clase = "ANALISIS_RIESGO"

    referencia = _texto(registro.get("referencia"), 80) or _texto(registro.get("rc"), 80)
    tipo_referencia = (_texto(registro.get("tipo_referencia"), 2) or "").upper()
    if not tipo_referencia and referencia:
        prefijo = referencia.strip().upper().split(maxsplit=1)[0].split("/", 1)[0]
        if prefijo in {"RC", "RE"}:
            tipo_referencia = prefijo
    if not tipo_referencia:
        tipo_referencia = "RC"

    normalizado = {
        "id_fuente": _texto(registro.get("id_fuente"), 120),
        "clase_registro": clase,
        "no_sp": _texto(registro.get("no_sp"), 50),
        "tipo_referencia": tipo_referencia,
        "referencia": referencia,
        "providencia": _texto(registro.get("providencia"), 120),
        "fecha_recepcion": _texto(registro.get("fecha_recepcion"), 10),
        "persona_entrega": _texto(registro.get("persona_entrega"), 180),
        "folios_recepcion": _texto(registro.get("folios_recepcion"), 80) or _texto(registro.get("folios"), 80),
        "observaciones": _texto(registro.get("observaciones")),
        "requiere_revision": _booleano(registro.get("requiere_revision", False)),
        "campos_inciertos": registro.get("campos_inciertos") if isinstance(registro.get("campos_inciertos"), list) else [],
        "fuente": _fuente_normalizada(registro),
        "anexo": anexo,
        "pago": registro.get("pago") if isinstance(registro.get("pago"), dict) else {},
        "monitoreo": registro.get("monitoreo") if isinstance(registro.get("monitoreo"), dict) else {},
        "analisis_riesgo": registro.get("analisis_riesgo") if isinstance(registro.get("analisis_riesgo"), dict) else {},
        "movimiento": registro.get("movimiento") if isinstance(registro.get("movimiento"), dict) else {},
    }

    # Compatibilidad con respuestas planas antiguas.
    if clase == "PAGO" and not normalizado["pago"]:
        normalizado["pago"] = {
            clave: registro.get(clave)
            for clave in ("periodo_desde", "periodo_hasta", "periodo_texto", "boleta", "banco", "monto", "total")
            if clave in registro
        }
    return normalizado


def _payload_desde_texto(texto):
    datos = _extraer_json(texto)
    if datos is None:
        return None, "No fue posible encontrar un JSON válido en la respuesta de Gemini."
    if not isinstance(datos, dict):
        return None, "La respuesta debe contener un objeto JSON principal."

    schema = datos.get("schema")
    if schema not in {SCHEMA_GEMINIASSIST, SCHEMA_LEGACY}:
        return None, f"El schema debe ser {SCHEMA_GEMINIASSIST}."

    lote = _texto(datos.get("lote"), 64)
    if not lote:
        return None, "El lote es obligatorio y debe ser un identificador estable de máximo 64 caracteres."

    registros = datos.get("registros")
    if not isinstance(registros, list) or not registros:
        return None, "La respuesta debe incluir al menos un registro."
    if len(registros) > MAX_REGISTROS_LOTE:
        return None, f"El lote supera el máximo de {MAX_REGISTROS_LOTE} registros."

    return {
        "schema": SCHEMA_GEMINIASSIST,
        "lote": lote,
        "origen": datos.get("origen") if isinstance(datos.get("origen"), dict) else {"proveedor": "GEMINI", "fuente": "GOOGLE_DRIVE"},
        "registros": [_normalizar_registro(registro) for registro in registros],
    }, None


def _referencia_archivo(registro):
    fuente = registro.get("fuente") or {}
    partes = []
    if fuente.get("id_fuente"):
        partes.append(f"ID:{fuente['id_fuente']}")
    if fuente.get("carpeta"):
        partes.append(fuente["carpeta"])
    archivos = fuente.get("archivos") or []
    if archivos:
        partes.append(", ".join(str(item) for item in archivos[:12]))
    return (" | ".join(partes) or "Gemini / Google Drive")[:255]


def _fila_importada(lote, fila):
    return RegistroCoordinacion.query.filter_by(
        lote_importacion=lote,
        hoja_origen=HOJA_ORIGEN,
        fila_origen=fila,
    ).first()


def _validar_comunes(registro, errores, advertencias):
    no_sp = _texto(registro.get("no_sp"), 50)
    expediente = None
    no_sp_norm = no_sp
    if not no_sp:
        errores.append("Falta No. de SP.")
    else:
        expediente, no_sp_norm = resolver_expediente(no_sp)
        if not expediente:
            errores.append("El SP no existe o no está activo en SICODE.")

    tipo_referencia = (_texto(registro.get("tipo_referencia"), 2) or "RC").upper()
    if tipo_referencia not in {"RC", "RE"}:
        errores.append("Tipo de referencia inválido; use RC o RE.")
        tipo_referencia = "RC"

    referencia_cruda = _texto(registro.get("referencia"), 80)
    referencia = _normalizar_referencia(tipo_referencia, referencia_cruda) if referencia_cruda else None
    if not referencia:
        advertencias.append("No se identificó RC / RE; revise el documento fuente si corresponde.")

    providencia = _texto(registro.get("providencia"), 120)
    if registro.get("providencia") and providencia is None:
        errores.append("La providencia supera 120 caracteres.")
    if not providencia:
        advertencias.append("No se identificó providencia.")

    fecha_texto = _texto(registro.get("fecha_recepcion"), 10)
    fecha_recepcion = _fecha(fecha_texto)
    if fecha_texto and not fecha_recepcion:
        errores.append("Fecha de recepción inválida; use AAAA-MM-DD.")
    elif not fecha_recepcion:
        advertencias.append("No se identificó fecha de recepción.")

    persona_entrega = _texto(registro.get("persona_entrega"), 180)
    folios = _texto(registro.get("folios_recepcion"), 80)
    observaciones = _texto(registro.get("observaciones"))

    campos_inciertos = [str(x).strip() for x in registro.get("campos_inciertos", []) if str(x).strip()]
    if registro.get("requiere_revision") or campos_inciertos:
        detalle = ", ".join(campos_inciertos[:8]) if campos_inciertos else "Gemini marcó el registro para revisión"
        advertencias.append(f"Revisión humana solicitada: {detalle}.")

    return {
        "no_sp": no_sp_norm,
        "expediente": expediente,
        "tipo_referencia": tipo_referencia,
        "rc": referencia,
        "providencia": providencia,
        "fecha_recepcion": fecha_recepcion,
        "persona_entrega": persona_entrega,
        "folios": folios,
        "observaciones": observaciones,
    }


def _validar_anexo(registro, comunes, errores, advertencias, numero_override=None, exigir_numero=False):
    datos = registro.get("anexo") or {}
    codigo = (_texto(datos.get("tipo_codigo"), 80) or "").upper()
    definicion = catalogo_plano().get(codigo) if codigo else None
    if not definicion:
        errores.append("Tipo de anexo no reconocido por el catálogo oficial de SICODE.")
        definicion = None

    titulo = definicion["titulo"] if definicion else None
    componentes = []
    if definicion and definicion["modo"] == "componentes":
        permitidos = {item[0] for item in COMPONENTES_REEMPLAZO}
        crudos = datos.get("componentes") or []
        if not isinstance(crudos, list):
            errores.append("anexo.componentes debe ser una lista.")
        else:
            for valor in crudos:
                componente = str(valor or "").strip().upper()
                if componente and componente not in permitidos:
                    errores.append(f"Componente no permitido: {componente}.")
                elif componente and componente not in componentes:
                    componentes.append(componente)
        titulo = _titulo_reemplazo(componentes)
        if not titulo:
            errores.append("El reemplazo debe indicar al menos un componente.")
    elif definicion and definicion["modo"] == "libre":
        titulo = _texto(datos.get("titulo_otro"), 180)
        if not titulo:
            errores.append("OTRO_ANEXO requiere anexo.titulo_otro.")
    elif definicion and definicion["modo"] == "especial":
        # El normalizador convierte los dos tipos especiales a sus clases dedicadas.
        errores.append("El tipo especial debe procesarse como MONITOREO o ANALISIS_RIESGO.")

    numero_crudo = numero_override if numero_override not in (None, "") else datos.get("numero_anexo")
    numero = _entero_anexo(numero_crudo)
    if numero is None:
        if exigir_numero:
            errores.append("Debe indicar el No. de anexo verificado en File Server.")
        else:
            advertencias.append("Pendiente confirmar No. de anexo en File Server.")

    fecha_escaneado_texto = _texto(datos.get("fecha_escaneado"), 10)
    fecha_escaneado = _fecha(fecha_escaneado_texto)
    if fecha_escaneado_texto and not fecha_escaneado:
        errores.append("anexo.fecha_escaneado debe usar AAAA-MM-DD.")

    return {
        "codigo": codigo,
        "definicion": definicion,
        "titulo": titulo,
        "componentes": componentes,
        "numero_anexo": numero,
        "es_vencido": _booleano(datos.get("es_vencido", False)),
        "escaneado": _booleano(datos.get("escaneado", False)),
        "fecha_escaneado": fecha_escaneado,
    }


def _validar_pago(registro, errores, advertencias):
    datos = registro.get("pago") or {}
    periodo_desde_texto = _texto(datos.get("periodo_desde"), 10)
    periodo_hasta_texto = _texto(datos.get("periodo_hasta"), 10)
    periodo_desde = _fecha(periodo_desde_texto)
    periodo_hasta = _fecha(periodo_hasta_texto)
    periodo_texto = _texto(datos.get("periodo_texto"), 120)
    if periodo_desde_texto and not periodo_desde:
        errores.append("pago.periodo_desde debe usar AAAA-MM-DD.")
    if periodo_hasta_texto and not periodo_hasta:
        errores.append("pago.periodo_hasta debe usar AAAA-MM-DD.")
    if periodo_desde and periodo_hasta and periodo_desde > periodo_hasta:
        errores.append("El período de pago tiene la fecha inicial después de la final.")
    if not periodo_texto and not periodo_desde and not periodo_hasta:
        errores.append("El pago debe indicar período por fechas o pago.periodo_texto.")

    boleta = _texto(datos.get("boleta"), 120)
    banco = _texto(datos.get("banco"), 120)
    monto = _decimal(datos.get("monto", datos.get("total")))
    if not boleta:
        errores.append("Falta el número de boleta del pago.")
    if not banco:
        errores.append("Falta el banco del pago.")
    if monto is None or monto <= 0:
        errores.append("El monto del pago debe ser numérico y mayor que cero.")

    if banco and boleta:
        duplicado = (
            PagoCoordinacion.query
            .filter(func.lower(PagoCoordinacion.banco) == banco.lower(), PagoCoordinacion.boleta == boleta)
            .first()
        )
        if duplicado:
            errores.append("La boleta ya está registrada para el mismo banco.")

    return {
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "periodo_texto": periodo_texto,
        "boleta": boleta,
        "banco": banco,
        "monto": monto,
    }


def _validar_especial(registro, clase, errores, advertencias, numero_override=None, exigir_numero=False):
    anexo = registro.get("anexo") or {}
    numero_crudo = numero_override if numero_override not in (None, "") else anexo.get("numero_anexo")
    numero = _entero_anexo(numero_crudo)
    if numero is None:
        if exigir_numero:
            errores.append("Debe indicar el No. de anexo verificado en File Server.")
        else:
            advertencias.append("Pendiente confirmar No. de anexo en File Server.")

    if clase == "MONITOREO":
        detalle = registro.get("monitoreo") or {}
        numero_reporte = _texto(detalle.get("numero_reporte"), 120)
        tipo_evento = _texto(detalle.get("tipo_evento"), 180)
        tipo_documento = _texto(detalle.get("tipo_documento"), 80) or "PROVIDENCIA"
        if not numero_reporte:
            advertencias.append("No se identificó número de reporte de monitoreo.")
        titulo_partes = ["Reporte de monitoreo"]
        if numero_reporte:
            titulo_partes.append(f"No. {numero_reporte}")
        if tipo_evento:
            titulo_partes.append(f"— {tipo_evento}")
        return {
            "numero_anexo": numero,
            "es_vencido": _booleano(anexo.get("es_vencido", False)),
            "titulo": " ".join(titulo_partes)[:180],
            "tipo_documento": tipo_documento,
            "numero_reporte": numero_reporte,
            "tipo_evento": tipo_evento,
        }

    detalle = registro.get("analisis_riesgo") or {}
    correlativo = _texto(detalle.get("correlativo"), 120) or _texto(detalle.get("correlativo_analisis"), 120)
    tipo_evento = _texto(detalle.get("tipo_evento"), 180)
    tipo_documento = _texto(detalle.get("tipo_documento"), 80) or "PROVIDENCIA"
    if not correlativo:
        advertencias.append("No se identificó correlativo del análisis de riesgo.")
    titulo_partes = ["Análisis de riesgo"]
    if correlativo:
        titulo_partes.append(f"Correlativo {correlativo}")
    if tipo_evento:
        titulo_partes.append(f"— {tipo_evento}")
    return {
        "numero_anexo": numero,
        "es_vencido": _booleano(anexo.get("es_vencido", False)),
        "titulo": " ".join(titulo_partes)[:180],
        "tipo_documento": tipo_documento,
        "correlativo": correlativo,
        "tipo_evento": tipo_evento,
    }


def _validar_movimiento(registro, clase, errores, advertencias):
    detalle = registro.get("movimiento") or {}
    descripcion = _texto(detalle.get("descripcion"), 180)
    if not descripcion:
        advertencias.append(f"{clase.title()} sin descripción específica del movimiento.")
    return {"descripcion": descripcion}


def _validar_registro(registro, lote, fila, numero_override=None, exigir_numero=False):
    errores = []
    advertencias = []
    if not isinstance(registro, dict):
        return {"estado": "BLOQUEADO", "errores": ["La fila no contiene un objeto JSON válido."], "advertencias": [], "fila": fila}

    clase = (_texto(registro.get("clase_registro"), 40) or "").upper()
    if clase not in CLASES_SOPORTADAS:
        errores.append(
            f"Clase {clase or 'sin definir'} no soportada. GEMINIASSIST no guardará datos en una tabla incorrecta."
        )

    comunes = _validar_comunes(registro, errores, advertencias)
    detalle = {}
    if clase == "ANEXO":
        detalle = _validar_anexo(registro, comunes, errores, advertencias, numero_override, exigir_numero)
    elif clase == "PAGO":
        detalle = _validar_pago(registro, errores, advertencias)
    elif clase in {"MONITOREO", "ANALISIS_RIESGO"}:
        detalle = _validar_especial(registro, clase, errores, advertencias, numero_override, exigir_numero)
    elif clase in {"INSTALACION", "DESINSTALACION"}:
        detalle = _validar_movimiento(registro, clase, errores, advertencias)

    if _fila_importada(lote, fila):
        errores.append("Esta fila del lote ya fue importada anteriormente.")

    estado = "BLOQUEADO" if errores else ("REVISAR" if advertencias else "LISTO")
    fuente = registro.get("fuente") or {}
    return {
        "estado": estado,
        "errores": errores,
        "advertencias": advertencias,
        "fila": fila,
        "clase": clase,
        "clase_etiqueta": clase.replace("_", " ").title() if clase else "Sin clase",
        **comunes,
        "detalle": detalle,
        "numero_anexo": detalle.get("numero_anexo"),
        "es_vencido": detalle.get("es_vencido", False),
        "titulo": detalle.get("titulo") or (detalle.get("definicion") or {}).get("titulo") or clase.replace("_", " ").title(),
        "carpeta_fuente": fuente.get("carpeta"),
        "archivo_origen": _referencia_archivo(registro),
        "original": registro,
    }


def _preparar_vista(payload, numeros=None, exigir_numero=False):
    numeros = numeros or {}
    return [
        _validar_registro(
            registro,
            payload["lote"],
            indice + 1,
            numero_override=numeros.get(str(indice)),
            exigir_numero=exigir_numero,
        )
        for indice, registro in enumerate(payload["registros"])
    ]


def _crear_base_desde_fila(fila, lote):
    expediente = fila["expediente"]
    numero = fila.get("numero_anexo")
    estado = determinar_estado(
        expediente,
        fila["no_sp"],
        campos_clave=[
            fila["no_sp"], fila["rc"], fila["providencia"], fila["fecha_recepcion"],
            fila["clase"], fila.get("titulo"), numero,
        ],
    )
    registro = RegistroCoordinacion(
        tipo=fila["clase"],
        expediente_id=expediente.id if expediente else None,
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
        lote_importacion=lote,
        hoja_origen=HOJA_ORIGEN,
        fila_origen=fila["fila"],
    )
    db.session.add(registro)
    db.session.flush()
    return registro


def _crear_rectificado_si_falta(fila, titulo):
    expediente = fila["expediente"]
    numero = fila["numero_anexo"]
    existente = AnexoRectificado.query.filter_by(
        expediente_id=expediente.id,
        numero_anexo=str(numero),
        activo=True,
    ).first()
    if existente:
        return
    db.session.add(AnexoRectificado(
        expediente_id=expediente.id,
        numero_anexo=str(numero),
        titulo=titulo,
        tipo_anexo="OTRO",
        fecha_recepcion=fila["fecha_recepcion"],
        persona_entrega=fila["persona_entrega"],
        rc=fila["rc"],
        providencia=fila["providencia"],
        folios=fila["folios"],
        escaneado=False,
        observaciones=fila["observaciones"],
        creado_por_id=current_user.id,
        activo=True,
    ))


def _guardar_anexo(fila, registro):
    detalle = fila["detalle"]
    numero = fila["numero_anexo"]
    expediente = fila["expediente"]
    _estado, error_numero = _validar_numero(expediente, numero, fila["es_vencido"])
    if error_numero:
        raise ValueError(f"SP {expediente.no_sp}: {error_numero}")

    definicion = detalle["definicion"]
    db.session.add(AnexoCoordinacion(
        registro_id=registro.id,
        tipo_anexo=definicion["titulo"][:120],
        titulo=fila["titulo"][:180],
        folios=fila["folios"],
        escaneado=detalle.get("escaneado", False),
        fecha_escaneado=detalle.get("fecha_escaneado"),
        numero_anexo=str(numero),
        es_vencido=fila["es_vencido"],
    ))
    return _actualizar_secuencia_vigente(expediente, numero, fila["es_vencido"])


def _guardar_monitoreo(fila, registro):
    detalle = fila["detalle"]
    expediente = fila["expediente"]
    numero = fila["numero_anexo"]
    _estado, error_numero = _validar_numero(expediente, numero, fila["es_vencido"])
    if error_numero:
        raise ValueError(f"SP {expediente.no_sp}: {error_numero}")
    db.session.add(ReporteMonitoreo(
        registro_id=registro.id,
        tipo_documento=detalle["tipo_documento"],
        numero_reporte=detalle["numero_reporte"],
        tipo_evento=detalle["tipo_evento"],
    ))
    db.session.add(AnexoCoordinacion(
        registro_id=registro.id,
        tipo_anexo="REPORTE DE MONITOREO",
        titulo=fila["titulo"][:180],
        folios=fila["folios"],
        escaneado=False,
        numero_anexo=str(numero),
        es_vencido=fila["es_vencido"],
    ))
    _crear_rectificado_si_falta(fila, fila["titulo"])
    return _actualizar_secuencia_vigente(expediente, numero, fila["es_vencido"])


def _guardar_analisis(fila, registro):
    detalle = fila["detalle"]
    expediente = fila["expediente"]
    numero = fila["numero_anexo"]
    _estado, error_numero = _validar_numero(expediente, numero, fila["es_vencido"])
    if error_numero:
        raise ValueError(f"SP {expediente.no_sp}: {error_numero}")
    db.session.add(AnalisisRiesgo(
        registro_id=registro.id,
        tipo_documento=detalle["tipo_documento"],
        correlativo=detalle["correlativo"],
        tipo_evento=detalle["tipo_evento"],
    ))
    db.session.add(AnexoCoordinacion(
        registro_id=registro.id,
        tipo_anexo="ANÁLISIS DE RIESGO",
        titulo=fila["titulo"][:180],
        folios=fila["folios"],
        escaneado=False,
        numero_anexo=str(numero),
        es_vencido=fila["es_vencido"],
    ))
    _crear_rectificado_si_falta(fila, fila["titulo"])
    return _actualizar_secuencia_vigente(expediente, numero, fila["es_vencido"])


def _guardar_pago(fila, registro):
    detalle = fila["detalle"]
    duplicado = (
        PagoCoordinacion.query
        .filter(
            func.lower(PagoCoordinacion.banco) == detalle["banco"].lower(),
            PagoCoordinacion.boleta == detalle["boleta"],
        )
        .first()
    )
    if duplicado:
        raise ValueError(f"Pago duplicado: boleta {detalle['boleta']} / {detalle['banco']}.")
    db.session.add(PagoCoordinacion(
        registro_id=registro.id,
        folios=fila["folios"],
        periodo_desde=detalle["periodo_desde"],
        periodo_hasta=detalle["periodo_hasta"],
        periodo_texto=detalle["periodo_texto"],
        boleta=detalle["boleta"],
        banco=detalle["banco"],
        total=detalle["monto"],
    ))
    return None


def _guardar_movimiento(fila, registro):
    db.session.add(MovimientoDispositivo(
        registro_id=registro.id,
        movimiento=fila["clase"],
        descripcion=fila["detalle"].get("descripcion"),
        folios=fila["folios"],
    ))
    return None


def _clave_orden_importacion(fila):
    if fila["clase"] not in CLASES_CON_SECUENCIA_ANEXO:
        return (0, fila["fila"], "", 0, 0)
    numero = fila.get("numero_anexo") or 0
    return (1, 0, fila.get("no_sp") or "", 0 if fila.get("es_vencido") else 1, numero)


def _resumen_detalle(fila):
    detalle = fila.get("detalle") or {}
    if fila["clase"] == "PAGO":
        monto = detalle.get("monto")
        return f"Boleta {detalle.get('boleta') or '—'} · {detalle.get('banco') or '—'} · Q {monto if monto is not None else '—'}"
    if fila["clase"] == "MONITOREO":
        return f"Reporte {detalle.get('numero_reporte') or '—'} · {detalle.get('tipo_evento') or 'Sin evento'}"
    if fila["clase"] == "ANALISIS_RIESGO":
        return f"Correlativo {detalle.get('correlativo') or '—'} · {detalle.get('tipo_evento') or 'Sin evento'}"
    if fila["clase"] in {"INSTALACION", "DESINSTALACION"}:
        return detalle.get("descripcion") or fila["clase"].replace("_", " ").title()
    if fila["clase"] == "ANEXO":
        if detalle.get("componentes"):
            return f"{fila.get('titulo') or 'Anexo'} · {', '.join(detalle['componentes'])}"
        return fila.get("titulo") or "Anexo"
    return fila.get("titulo") or fila["clase"]


def _agregar_resumenes(filas):
    for fila in filas:
        fila["resumen_detalle"] = _resumen_detalle(fila)
    return filas


@admin_bp.get("/geminiassist")
@login_required
@admin_required
def geminiassist():
    return render_template("admin/geminiassist.html", payload_texto="", filas=[], lote=None)


@admin_bp.post("/geminiassist/validar")
@login_required
@admin_required
def validar_geminiassist():
    payload_texto = request.form.get("payload_json") or ""
    payload, error = _payload_desde_texto(payload_texto)
    if error:
        flash(error, "danger")
        return render_template("admin/geminiassist.html", payload_texto=payload_texto, filas=[], lote=None), 400

    filas = _agregar_resumenes(_preparar_vista(payload))
    return render_template(
        "admin/geminiassist.html",
        payload_texto=json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        filas=filas,
        lote=payload["lote"],
    )


@admin_bp.post("/geminiassist/registrar")
@login_required
@admin_required
def registrar_geminiassist():
    payload_texto = request.form.get("payload_json") or ""
    payload, error = _payload_desde_texto(payload_texto)
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.geminiassist"))

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
        filas = _agregar_resumenes(_preparar_vista(payload))
        return render_template(
            "admin/geminiassist.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
        ), 400

    numeros = {str(i): request.form.get(f"numero_anexo_{i}") for i in seleccionados}
    filas_todas = _preparar_vista(payload, numeros=numeros, exigir_numero=False)
    filas_seleccionadas = []
    hay_errores = False
    requiere_file_server = False
    for indice in seleccionados:
        clase = payload["registros"][indice].get("clase_registro")
        fila = _validar_registro(
            payload["registros"][indice],
            payload["lote"],
            indice + 1,
            numero_override=numeros.get(str(indice)),
            exigir_numero=clase in CLASES_CON_SECUENCIA_ANEXO,
        )
        filas_todas[indice] = fila
        filas_seleccionadas.append(fila)
        hay_errores = hay_errores or bool(fila["errores"])
        requiere_file_server = requiere_file_server or fila["clase"] in CLASES_CON_SECUENCIA_ANEXO

    if requiere_file_server and request.form.get("confirmacion_file_server") != "1":
        flash("Los anexos seleccionados requieren confirmar sus números contra File Server.", "danger")
        filas_todas = _agregar_resumenes(filas_todas)
        return render_template(
            "admin/geminiassist.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas_todas,
            lote=payload["lote"],
            seleccionados_previos=set(seleccionados),
        ), 400

    if hay_errores:
        db.session.rollback()
        flash("No se registró el lote: corrija los registros bloqueados y vuelva a validar.", "danger")
        filas_todas = _agregar_resumenes(filas_todas)
        return render_template(
            "admin/geminiassist.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas_todas,
            lote=payload["lote"],
            seleccionados_previos=set(seleccionados),
        ), 400

    creados = []
    try:
        for fila in sorted(filas_seleccionadas, key=_clave_orden_importacion):
            registro = _crear_base_desde_fila(fila, payload["lote"])
            total_anterior = None
            if fila["clase"] == "ANEXO":
                total_anterior = _guardar_anexo(fila, registro)
            elif fila["clase"] == "MONITOREO":
                total_anterior = _guardar_monitoreo(fila, registro)
            elif fila["clase"] == "ANALISIS_RIESGO":
                total_anterior = _guardar_analisis(fila, registro)
            elif fila["clase"] == "PAGO":
                _guardar_pago(fila, registro)
            elif fila["clase"] in {"INSTALACION", "DESINSTALACION"}:
                _guardar_movimiento(fila, registro)
            else:
                raise ValueError(f"Clase no implementada: {fila['clase']}")

            registrar_bitacora(
                accion=f"IMPORTAR_GEMINIASSIST_{fila['clase']}",
                modulo="Administración / GEMINIASSIST",
                descripcion=(
                    f"GEMINIASSIST importó {fila['clase']} del SP {fila['no_sp']} "
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
                },
                commit=False,
            )
            creados.append(registro)

        registrar_bitacora(
            accion="IMPORTAR_LOTE_GEMINIASSIST",
            modulo="Administración / GEMINIASSIST",
            descripcion=f"Se importaron {len(creados)} registro(s) desde el lote {payload['lote']} preparado por Gemini/Drive.",
            usuario_id=current_user.id,
            entidad="LoteGeminiAssist",
            entidad_id=payload["lote"],
            datos_posteriores={
                "lote": payload["lote"],
                "cantidad": len(creados),
                "origen": ORIGEN_REGISTRO,
                "clases": sorted({fila["clase"] for fila in filas_seleccionadas}),
            },
            commit=False,
        )
        db.session.commit()
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        flash(f"No se importó el lote. {exc}", "danger")
        filas = _agregar_resumenes(_preparar_vista(payload, numeros=numeros))
        return render_template(
            "admin/geminiassist.html",
            payload_texto=json.dumps(payload, ensure_ascii=False, indent=2),
            filas=filas,
            lote=payload["lote"],
        ), 409

    flash(f"GEMINIASSIST registró correctamente {len(creados)} registro(s) del lote {payload['lote']}.", "success")
    return redirect(url_for("admin.geminiassist"))


# Compatibilidad de URL con el panel anterior. Los POST conservan cuerpo con 307.
@admin_bp.get("/anexos-asistidos")
@login_required
@admin_required
def anexos_asistidos():
    return redirect(url_for("admin.geminiassist"), code=302)


@admin_bp.post("/anexos-asistidos/validar")
@login_required
@admin_required
def validar_anexos_asistidos():
    return redirect(url_for("admin.validar_geminiassist"), code=307)


@admin_bp.post("/anexos-asistidos/registrar")
@login_required
@admin_required
def registrar_anexos_asistidos():
    return redirect(url_for("admin.registrar_geminiassist"), code=307)
