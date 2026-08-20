import json
import re
import unicodedata
from datetime import date
from urllib import error as urllib_error
from urllib import request as urllib_request

from flask import current_app
from sqlalchemy import and_, exists, or_

from app.models.alerta import Alerta
from app.models.coordinacion import RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.ubicacion import UbicacionFisica
from app.services.busqueda_service import buscar_global
from app.services.sp_service import normalizar_sp


AMBITOS = {"global", "expedientes", "prestamos", "alertas", "documentos", "ubicacion", "coordinacion"}
DISPONIBILIDADES = {"disponible", "en_prestamo", "sin_expediente_fisico"}
ESTADOS_PRESTAMO = {"activo", "vencido", "devuelto"}
ESTADOS_ALERTA = {"pendiente", "Abierta", "En revisión", "Corregida", "Cerrada"}
GRAVEDADES_ALERTA = {"Alta", "Media", "Baja"}
TIPOS_COORDINACION = {
    "PAGO", "INSTALACION", "DESINSTALACION", "ANEXO", "MONITOREO",
    "DOCUMENTO_EMITIDO", "ACTIVIDAD", "REMISION",
}
LIMITE_IA = 80


class OllamaNoDisponible(RuntimeError):
    pass


def _texto_seguro(valor, limite=180):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:limite] if texto else None


def _sin_acentos(texto):
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def _canon_enum(valor, permitidos):
    texto = _texto_seguro(valor, 80)
    if not texto:
        return None
    normal = _sin_acentos(texto).replace(" ", "_")
    for permitido in permitidos:
        if normal == _sin_acentos(permitido).replace(" ", "_"):
            return permitido
    return None


def normalizar_filtros(datos):
    datos = datos if isinstance(datos, dict) else {}
    return {
        "ambito": _canon_enum(datos.get("ambito"), AMBITOS) or "global",
        "no_sp": normalizar_sp(_texto_seguro(datos.get("no_sp"), 50)) if datos.get("no_sp") else None,
        "texto": _texto_seguro(datos.get("texto")),
        "estado": _texto_seguro(datos.get("estado"), 100),
        "disponibilidad": _canon_enum(datos.get("disponibilidad"), DISPONIBILIDADES),
        "prestamo": _canon_enum(datos.get("prestamo"), ESTADOS_PRESTAMO),
        "persona": _texto_seguro(datos.get("persona")),
        "alerta_estado": _canon_enum(datos.get("alerta_estado"), ESTADOS_ALERTA),
        "alerta_gravedad": _canon_enum(datos.get("alerta_gravedad"), GRAVEDADES_ALERTA),
        "documento": _texto_seguro(datos.get("documento")),
        "solo_anexos": bool(datos.get("solo_anexos")) if datos.get("solo_anexos") is not None else None,
        "ubicacion": _texto_seguro(datos.get("ubicacion")),
        "coordinacion_tipo": _canon_enum(datos.get("coordinacion_tipo"), TIPOS_COORDINACION),
        "rc": _texto_seguro(datos.get("rc"), 80),
        "providencia": _texto_seguro(datos.get("providencia"), 120),
    }


def _prompt_sistema():
    return """Eres el intérprete de búsquedas de SICODE-UCT. Tu única tarea es convertir una consulta en español a filtros JSON seguros. Nunca escribas SQL, código, explicaciones largas ni datos inventados. Responde solamente un objeto JSON.

Esquema permitido:
{
  "ambito": "global|expedientes|prestamos|alertas|documentos|ubicacion|coordinacion",
  "no_sp": "numero o null",
  "texto": "termino literal útil o null",
  "estado": "estado mencionado o null",
  "disponibilidad": "disponible|en_prestamo|sin_expediente_fisico|null",
  "prestamo": "activo|vencido|devuelto|null",
  "persona": "nombre mencionado o null",
  "alerta_estado": "pendiente|Abierta|En revisión|Corregida|Cerrada|null",
  "alerta_gravedad": "Alta|Media|Baja|null",
  "documento": "nombre/tipo documental o null",
  "solo_anexos": true|false|null,
  "ubicacion": "valor de archivador/estante/caja/modulo/posicion o null",
  "coordinacion_tipo": "PAGO|INSTALACION|DESINSTALACION|ANEXO|MONITOREO|DOCUMENTO_EMITIDO|ACTIVIDAD|REMISION|null",
  "rc": "RC mencionado o null",
  "providencia": "providencia mencionada o null"
}

Reglas: 'sin devolver' significa préstamo activo; 'vencido' requiere prestamo=vencido; preguntas de dónde está un SP usan ambito=ubicacion; problemas/alertas usan ambito=alertas; folios/anexos/documentos usan ambito=documentos. Si la consulta solo pide localizar un dato general usa ambito=global."""


def _consultar_ollama(consulta):
    if not current_app.config.get("AI_SEARCH_ENABLED", True):
        raise OllamaNoDisponible("La búsqueda IA está deshabilitada por configuración.")

    base_url = current_app.config.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    modelo = current_app.config.get("OLLAMA_MODEL", "qwen3:1.7b")
    timeout = float(current_app.config.get("OLLAMA_TIMEOUT", 15))
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": _prompt_sistema()},
            {"role": "user", "content": consulta},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    req = urllib_request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as respuesta:
            cuerpo = json.loads(respuesta.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise OllamaNoDisponible("Ollama local no respondió.") from exc

    contenido = ((cuerpo.get("message") or {}).get("content") or "").strip()
    if not contenido:
        raise OllamaNoDisponible("Ollama devolvió una respuesta vacía.")
    try:
        return normalizar_filtros(json.loads(contenido))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OllamaNoDisponible("Ollama no devolvió filtros JSON válidos.") from exc


def interpretar_reglas(consulta):
    original = (consulta or "").strip()
    texto = _sin_acentos(original)
    datos = {"ambito": "global"}

    sp = re.search(r"\bsp\s*[-:#]?\s*([a-z0-9.-]+)", texto, re.IGNORECASE)
    if sp:
        datos["no_sp"] = sp.group(1)

    if any(p in texto for p in ("prestam", "devuelt", "devoluc", "sin devolver", "no ha regresado", "no han regresado")):
        datos["ambito"] = "prestamos"
    if any(p in texto for p in ("vencid", "atrasad", "fuera de fecha")):
        datos.update(ambito="prestamos", prestamo="vencido")
    elif any(p in texto for p in ("sin devolver", "no devuelt", "en prestamo", "prestados", "prestado")):
        datos.update(ambito="prestamos", prestamo="activo")
    elif "devuelto" in texto or "devueltos" in texto:
        datos.update(ambito="prestamos", prestamo="devuelto")

    if "disponible" in texto:
        datos["disponibilidad"] = "disponible"
    if "sin expediente fisico" in texto:
        datos["disponibilidad"] = "sin_expediente_fisico"
    if "en prestamo" in texto:
        datos["disponibilidad"] = "en_prestamo"

    if any(p in texto for p in ("alerta", "incidencia", "problema", "pendiente de revisar")):
        datos["ambito"] = "alertas"
        if any(p in texto for p in ("pendiente", "abierta", "sin cerrar")):
            datos["alerta_estado"] = "pendiente"
        if "alta" in texto or "grave" in texto:
            datos["alerta_gravedad"] = "Alta"
        elif "media" in texto:
            datos["alerta_gravedad"] = "Media"
        elif "baja" in texto:
            datos["alerta_gravedad"] = "Baja"

    if any(p in texto for p in ("folio", "documento", "indice documental", "anexo")):
        datos["ambito"] = "documentos"
        if "anexo" in texto:
            datos["solo_anexos"] = True

    if any(p in texto for p in ("donde esta", "ubicacion", "ubicado", "archivador", "estante", "caja", "modulo", "posicion")):
        datos["ambito"] = "ubicacion"
        ubicacion = re.search(r"(?:archivador|estante|caja|modulo|posicion)\s*[-:#]?\s*([a-z0-9.-]+)", texto)
        if ubicacion:
            datos["ubicacion"] = ubicacion.group(1)

    tipos = {
        "pago": "PAGO", "instalacion": "INSTALACION", "desinstalacion": "DESINSTALACION",
        "monitoreo": "MONITOREO", "documento emitido": "DOCUMENTO_EMITIDO",
        "actividad": "ACTIVIDAD", "remision": "REMISION",
    }
    for palabra, tipo in tipos.items():
        if palabra in texto:
            datos.update(ambito="coordinacion", coordinacion_tipo=tipo)
            break

    rc = re.search(r"\brc\s*[-:#]?\s*([a-z0-9./-]+)", texto)
    if rc:
        datos.update(ambito="coordinacion", rc=rc.group(1).upper())
    prov = re.search(r"\bprovidencia\s*[-:#]?\s*([a-z0-9./-]+)", texto)
    if prov:
        datos.update(ambito="coordinacion", providencia=prov.group(1).upper())

    return normalizar_filtros(datos)


def _resultado(categoria, titulo, detalle, endpoint, **params):
    return {"categoria": categoria, "titulo": titulo, "detalle": detalle, "endpoint": endpoint, "params": params}


def _prestamo_activo_exists():
    return exists().where(and_(
        PrestamoExpediente.expediente_id == Expediente.id,
        PrestamoExpediente.activo.is_(True),
        PrestamoExpediente.estado == "En préstamo",
    ))


def _aplicar_expediente_comun(consulta, filtros):
    if filtros["no_sp"]:
        consulta = consulta.filter(Expediente.no_sp == filtros["no_sp"])
    if filtros["estado"]:
        patron = f"%{filtros['estado']}%"
        consulta = consulta.filter(or_(
            Expediente.estado_administrativo.ilike(patron),
            Expediente.estado_fisico_documental.ilike(patron),
            Expediente.estado_portador.ilike(patron),
            Expediente.estado_monitoreo.ilike(patron),
        ))
    if filtros["texto"]:
        patron = f"%{filtros['texto']}%"
        consulta = consulta.filter(or_(
            Expediente.no_sp.ilike(patron), Expediente.codigo_interno.ilike(patron),
            Expediente.nombre_referencia.ilike(patron), Expediente.nombres.ilike(patron),
            Expediente.apellidos.ilike(patron), Expediente.expediente_oj.ilike(patron),
            Expediente.delito.ilike(patron), Expediente.observaciones.ilike(patron),
        ))
    return consulta


def _buscar_expedientes(filtros):
    consulta = _aplicar_expediente_comun(Expediente.query, filtros)

    if filtros["disponibilidad"] == "en_prestamo":
        consulta = consulta.filter(_prestamo_activo_exists())
    elif filtros["disponibilidad"] == "disponible":
        consulta = consulta.filter(
            Expediente.activo.is_(True),
            Expediente.expediente_fisico_registrado.is_(True),
            ~_prestamo_activo_exists(),
        )
    elif filtros["disponibilidad"] == "sin_expediente_fisico":
        consulta = consulta.filter(Expediente.expediente_fisico_registrado.is_(False))

    if filtros["prestamo"]:
        consulta = consulta.join(PrestamoExpediente, PrestamoExpediente.expediente_id == Expediente.id)
        if filtros["prestamo"] == "activo":
            consulta = consulta.filter(PrestamoExpediente.activo.is_(True), PrestamoExpediente.estado == "En préstamo")
        elif filtros["prestamo"] == "vencido":
            consulta = consulta.filter(
                PrestamoExpediente.activo.is_(True), PrestamoExpediente.estado == "En préstamo",
                PrestamoExpediente.fecha_estimada_devolucion.isnot(None),
                PrestamoExpediente.fecha_estimada_devolucion < date.today(),
            )
        elif filtros["prestamo"] == "devuelto":
            consulta = consulta.filter(PrestamoExpediente.estado == "Devuelto")

    if filtros["persona"]:
        patron = f"%{filtros['persona']}%"
        if not filtros["prestamo"]:
            consulta = consulta.join(PrestamoExpediente, PrestamoExpediente.expediente_id == Expediente.id)
        consulta = consulta.filter(or_(
            PrestamoExpediente.solicitante.ilike(patron), PrestamoExpediente.persona_entrega.ilike(patron),
            PrestamoExpediente.persona_recibe.ilike(patron), PrestamoExpediente.persona_devuelve.ilike(patron),
            PrestamoExpediente.persona_recibe_devolucion.ilike(patron),
        ))

    if filtros["alerta_estado"] or filtros["alerta_gravedad"]:
        consulta = consulta.join(Alerta, Alerta.expediente_id == Expediente.id)
        if filtros["alerta_estado"] == "pendiente":
            consulta = consulta.filter(Alerta.estado.in_(["Abierta", "En revisión"]))
        elif filtros["alerta_estado"]:
            consulta = consulta.filter(Alerta.estado == filtros["alerta_estado"])
        if filtros["alerta_gravedad"]:
            consulta = consulta.filter(Alerta.gravedad == filtros["alerta_gravedad"])

    expedientes = consulta.distinct().order_by(Expediente.no_sp.asc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "SP / Expediente", f"SP {item.no_sp} · {item.nombre_referencia or 'Sin nombre'}",
            f"{item.codigo_interno} · {item.disponibilidad} · {item.estado_fisico_documental}",
            "expedientes.detalle", expediente_id=item.id,
        ) for item in expedientes
    ]


def _buscar_prestamos(filtros):
    consulta = PrestamoExpediente.query.join(Expediente, PrestamoExpediente.expediente_id == Expediente.id)
    if filtros["no_sp"]:
        consulta = consulta.filter(Expediente.no_sp == filtros["no_sp"])
    estado = filtros["prestamo"]
    if estado == "activo":
        consulta = consulta.filter(PrestamoExpediente.activo.is_(True), PrestamoExpediente.estado == "En préstamo")
    elif estado == "vencido":
        consulta = consulta.filter(
            PrestamoExpediente.activo.is_(True), PrestamoExpediente.estado == "En préstamo",
            PrestamoExpediente.fecha_estimada_devolucion.isnot(None),
            PrestamoExpediente.fecha_estimada_devolucion < date.today(),
        )
    elif estado == "devuelto":
        consulta = consulta.filter(PrestamoExpediente.estado == "Devuelto")
    if filtros["persona"]:
        patron = f"%{filtros['persona']}%"
        consulta = consulta.filter(or_(
            PrestamoExpediente.solicitante.ilike(patron), PrestamoExpediente.persona_entrega.ilike(patron),
            PrestamoExpediente.persona_recibe.ilike(patron), PrestamoExpediente.persona_devuelve.ilike(patron),
            PrestamoExpediente.persona_recibe_devolucion.ilike(patron),
        ))
    if filtros["texto"]:
        patron = f"%{filtros['texto']}%"
        consulta = consulta.filter(or_(
            PrestamoExpediente.numero_control.ilike(patron), PrestamoExpediente.solicitante.ilike(patron),
            PrestamoExpediente.persona_entrega.ilike(patron), PrestamoExpediente.persona_recibe.ilike(patron),
            PrestamoExpediente.observaciones.ilike(patron), Expediente.no_sp.ilike(patron),
            Expediente.nombre_referencia.ilike(patron),
        ))
    prestamos = consulta.order_by(PrestamoExpediente.fecha_prestamo.desc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "Préstamo", item.numero_control, f"SP {item.expediente.no_sp} · {item.solicitante} · {item.estado}",
            "prestamos.detalle", prestamo_id=item.id,
        ) for item in prestamos
    ]


def _buscar_alertas(filtros):
    consulta = Alerta.query.join(Expediente, Alerta.expediente_id == Expediente.id)
    if filtros["no_sp"]:
        consulta = consulta.filter(Expediente.no_sp == filtros["no_sp"])
    if filtros["alerta_estado"] == "pendiente":
        consulta = consulta.filter(Alerta.estado.in_(["Abierta", "En revisión"]))
    elif filtros["alerta_estado"]:
        consulta = consulta.filter(Alerta.estado == filtros["alerta_estado"])
    if filtros["alerta_gravedad"]:
        consulta = consulta.filter(Alerta.gravedad == filtros["alerta_gravedad"])
    texto = filtros["texto"] or filtros["estado"]
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.filter(or_(
            Alerta.titulo.ilike(patron), Alerta.descripcion.ilike(patron), Alerta.tipo_alerta.ilike(patron),
            Expediente.no_sp.ilike(patron), Expediente.nombre_referencia.ilike(patron),
        ))
    alertas = consulta.order_by(Alerta.creado_en.desc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "Alerta", f"SP {item.expediente.no_sp} · {item.titulo}",
            f"{item.gravedad} · {item.estado} · {item.tipo_alerta}",
            "alertas.listado", q=item.expediente.no_sp,
        ) for item in alertas
    ]


def _buscar_documentos(filtros):
    consulta = DocumentoExpediente.query.join(Expediente, DocumentoExpediente.expediente_id == Expediente.id)
    if filtros["no_sp"]:
        consulta = consulta.filter(Expediente.no_sp == filtros["no_sp"])
    if filtros["solo_anexos"] is True:
        consulta = consulta.filter(DocumentoExpediente.es_anexo.is_(True))
    texto = filtros["documento"] or filtros["texto"] or filtros["estado"]
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.filter(or_(
            DocumentoExpediente.nombre_documento.ilike(patron), DocumentoExpediente.tipo_documento.ilike(patron),
            DocumentoExpediente.estado_revision.ilike(patron), DocumentoExpediente.observaciones.ilike(patron),
            Expediente.no_sp.ilike(patron),
        ))
    documentos = consulta.order_by(Expediente.no_sp.asc(), DocumentoExpediente.folio_inicio.asc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "Índice documental", item.nombre_documento,
            f"SP {item.expediente.no_sp} · folios {item.folio_inicio}-{item.folio_fin} · {item.estado_revision}",
            "indice_documental.listado", expediente_id=item.expediente_id,
        ) for item in documentos
    ]


def _buscar_ubicaciones(filtros):
    consulta = UbicacionFisica.query.join(Expediente, UbicacionFisica.expediente_id == Expediente.id)
    if filtros["no_sp"]:
        consulta = consulta.filter(Expediente.no_sp == filtros["no_sp"])
    if filtros["ubicacion"]:
        patron = f"%{filtros['ubicacion']}%"
        consulta = consulta.filter(or_(
            UbicacionFisica.archivador.ilike(patron), UbicacionFisica.sicoin.ilike(patron),
            UbicacionFisica.estante.ilike(patron), UbicacionFisica.caja.ilike(patron),
            UbicacionFisica.modulo.ilike(patron), UbicacionFisica.posicion.ilike(patron),
            UbicacionFisica.observaciones.ilike(patron),
        ))
    ubicaciones = consulta.order_by(Expediente.no_sp.asc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "Ubicación", f"SP {item.expediente.no_sp} · {item.expediente.nombre_referencia or 'Sin nombre'}",
            " · ".join(filter(None, [item.archivador, item.sicoin, item.estante, item.caja, item.modulo, item.posicion])) or "Ubicación sin detalle",
            "expedientes.detalle", expediente_id=item.expediente_id,
        ) for item in ubicaciones
    ]


def _buscar_coordinacion(filtros):
    consulta = RegistroCoordinacion.query
    if filtros["no_sp"]:
        consulta = consulta.filter(RegistroCoordinacion.no_sp_referencia == filtros["no_sp"])
    if filtros["coordinacion_tipo"]:
        consulta = consulta.filter(RegistroCoordinacion.tipo == filtros["coordinacion_tipo"])
    if filtros["rc"]:
        consulta = consulta.filter(RegistroCoordinacion.rc.ilike(f"%{filtros['rc']}%"))
    if filtros["providencia"]:
        consulta = consulta.filter(RegistroCoordinacion.providencia.ilike(f"%{filtros['providencia']}%"))
    if filtros["estado"]:
        consulta = consulta.filter(RegistroCoordinacion.estado.ilike(f"%{filtros['estado']}%"))
    if filtros["texto"]:
        patron = f"%{filtros['texto']}%"
        consulta = consulta.filter(or_(
            RegistroCoordinacion.no_sp_referencia.ilike(patron), RegistroCoordinacion.rc.ilike(patron),
            RegistroCoordinacion.providencia.ilike(patron), RegistroCoordinacion.persona_entrega.ilike(patron),
            RegistroCoordinacion.folios_recepcion.ilike(patron), RegistroCoordinacion.observaciones.ilike(patron),
        ))
    registros = consulta.order_by(RegistroCoordinacion.creado_en.desc()).limit(LIMITE_IA).all()
    return [
        _resultado(
            "Coordinación", f"{item.tipo} · SP {item.no_sp_referencia or '—'}",
            f"RC {item.rc or '—'} · Providencia {item.providencia or '—'} · {item.estado}",
            "coordinacion.detalle", registro_id=item.id,
        ) for item in registros
    ]


def _deduplicar(resultados):
    vistos = set()
    salida = []
    for item in resultados:
        clave = (item["categoria"], item["titulo"], item["endpoint"], tuple(sorted(item["params"].items())))
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(item)
        if len(salida) >= LIMITE_IA:
            break
    return salida


def buscar_por_filtros(filtros, consulta_original=""):
    ambito = filtros.get("ambito") or "global"
    buscadores = {
        "expedientes": _buscar_expedientes,
        "prestamos": _buscar_prestamos,
        "alertas": _buscar_alertas,
        "documentos": _buscar_documentos,
        "ubicacion": _buscar_ubicaciones,
        "coordinacion": _buscar_coordinacion,
    }
    if ambito in buscadores:
        return buscadores[ambito](filtros)

    resultados = []
    hay_filtros = any(
        filtros.get(clave) not in (None, "", False)
        for clave in ("no_sp", "estado", "disponibilidad", "prestamo", "persona", "alerta_estado",
                      "alerta_gravedad", "documento", "solo_anexos", "ubicacion", "coordinacion_tipo", "rc", "providencia")
    )
    if hay_filtros:
        resultados.extend(_buscar_expedientes(filtros))
        if filtros.get("prestamo") or filtros.get("persona"):
            resultados.extend(_buscar_prestamos(filtros))
        if filtros.get("alerta_estado") or filtros.get("alerta_gravedad"):
            resultados.extend(_buscar_alertas(filtros))
        if filtros.get("documento") or filtros.get("solo_anexos"):
            resultados.extend(_buscar_documentos(filtros))
        if filtros.get("ubicacion"):
            resultados.extend(_buscar_ubicaciones(filtros))
        if filtros.get("coordinacion_tipo") or filtros.get("rc") or filtros.get("providencia"):
            resultados.extend(_buscar_coordinacion(filtros))

    if not resultados:
        termino = filtros.get("texto") or consulta_original
        if termino:
            resultados.extend(buscar_global(termino))
    return _deduplicar(resultados)


def describir_filtros(filtros):
    partes = []
    etiquetas = {
        "global": "búsqueda general", "expedientes": "expedientes", "prestamos": "préstamos",
        "alertas": "alertas", "documentos": "índice documental", "ubicacion": "ubicación física",
        "coordinacion": "registros de coordinación",
    }
    partes.append(etiquetas.get(filtros.get("ambito"), "búsqueda general"))
    if filtros.get("no_sp"):
        partes.append(f"SP {filtros['no_sp']}")
    if filtros.get("prestamo"):
        partes.append(f"préstamo {filtros['prestamo']}")
    if filtros.get("disponibilidad"):
        partes.append(f"disponibilidad {filtros['disponibilidad'].replace('_', ' ')}")
    if filtros.get("persona"):
        partes.append(f"persona: {filtros['persona']}")
    if filtros.get("alerta_estado"):
        partes.append(f"alerta {filtros['alerta_estado']}")
    if filtros.get("alerta_gravedad"):
        partes.append(f"gravedad {filtros['alerta_gravedad']}")
    if filtros.get("documento"):
        partes.append(f"documento: {filtros['documento']}")
    if filtros.get("solo_anexos"):
        partes.append("solo anexos")
    if filtros.get("ubicacion"):
        partes.append(f"ubicación: {filtros['ubicacion']}")
    if filtros.get("coordinacion_tipo"):
        partes.append(f"tipo {filtros['coordinacion_tipo']}")
    if filtros.get("rc"):
        partes.append(f"RC {filtros['rc']}")
    if filtros.get("providencia"):
        partes.append(f"providencia {filtros['providencia']}")
    if filtros.get("estado"):
        partes.append(f"estado: {filtros['estado']}")
    return " · ".join(partes)


def buscar_con_ia(consulta):
    consulta = (consulta or "").strip()
    if len(consulta) < 3:
        return {
            "resultados": [], "filtros": normalizar_filtros({}), "interpretacion": "Consulta demasiado corta",
            "motor": "reglas", "aviso": "Escriba una consulta de al menos 3 caracteres.",
        }

    aviso = None
    try:
        filtros = _consultar_ollama(consulta)
        motor = "ollama"
    except OllamaNoDisponible:
        filtros = interpretar_reglas(consulta)
        motor = "reglas"
        aviso = "La IA local todavía no está disponible; SICODE aplicó interpretación básica segura."

    resultados = buscar_por_filtros(filtros, consulta_original=consulta)
    return {
        "resultados": resultados,
        "filtros": filtros,
        "interpretacion": describir_filtros(filtros),
        "motor": motor,
        "aviso": aviso,
    }
