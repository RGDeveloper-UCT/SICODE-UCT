"""Sincronización defensiva y auditable de CISA KEV y NVD 2.0.

Nunca se ejecuta durante una petición HTTP: invocar con el CLI o systemd.
Las fuentes no afirman que un equipo institucional esté afectado.
"""
from datetime import date, datetime, timedelta
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app import db
from app.models.agenda import AgendaNotificacion
from app.models.seguridad_operativa import VulnerabilidadTI, SincronizacionVulnerabilidadesTI
from app.models.usuario import Usuario
from app.services.agenda_service import notificar
from app.services.bitacora_service import registrar_bitacora

CISA_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$", re.ASCII)
LIMITE_BYTES = 12 * 1024 * 1024


def _descargar(url):
    """Solo se llama con URL fija de CISA/NVD construida internamente."""
    req = Request(url, headers={"User-Agent": "SICODE-UCT-Seguridad/1.0 (consulta institucional)",
                                "Accept": "application/json"})
    with urlopen(req, timeout=30) as resp:
        datos = resp.read(LIMITE_BYTES + 1)
    if len(datos) > LIMITE_BYTES:
        raise ValueError("La respuesta supera el tamaño permitido.")
    return json.loads(datos.decode("utf-8"))


def _fecha(texto):
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def _texto(valor, limite):
    return str(valor or "").strip()[:limite]


def _actualizar_cve(datos, fuente):
    cve = _texto(datos.get("cve"), 28).upper()
    if not CVE_PATTERN.fullmatch(cve):
        return None, False, False
    existente = VulnerabilidadTI.query.filter_by(cve=cve).first()
    nueva = existente is None
    v = existente or VulnerabilidadTI(cve=cve, fuente=fuente, fuentes=[fuente],
                                      titulo=cve, severidad="DESCONOCIDA")
    explotada_antes = bool(v.explotada)
    if nueva:
        db.session.add(v)
    v.fuentes = sorted(set((v.fuentes or []) + [fuente]))
    if nueva or not v.descripcion:
        v.descripcion = _texto(datos.get("descripcion"), 4000)
    if nueva or not v.recomendacion:
        v.recomendacion = _texto(datos.get("recomendacion"), 4000)
    if nueva or v.titulo == cve:
        v.titulo = _texto(datos.get("titulo") or cve, 220)
    if nueva or not v.producto:
        v.producto = _texto(datos.get("producto"), 160) or None
    if nueva or not v.fabricante:
        v.fabricante = _texto(datos.get("fabricante"), 140) or None
    if nueva or not v.fecha_publicacion:
        v.fecha_publicacion = datos.get("fecha")
    if nueva or not v.referencia:
        v.referencia = _texto(datos.get("referencia"), 500) or None
    severidad = datos.get("severidad")
    if severidad in ("ALTA", "CRITICA") and v.severidad not in ("CRITICA",):
        v.severidad = severidad
    v.explotada = bool(v.explotada or datos.get("explotada"))
    return v, nueva, bool(v.explotada and not explotada_antes and not nueva)


def _avisar(v, origen):
    usuarios = [u.id for u in Usuario.query.filter_by(activo=True).all() if u.puede_modificar]
    prioridad = "alta" if v.explotada or v.severidad == "CRITICA" else "media"
    notificar(usuarios, None, "Nueva vulnerabilidad: " + (v.cve or v.titulo)[:130],
             (v.titulo + " · Origen " + origen + ". Revisar aplicabilidad en el inventario. ")[:900],
             prioridad=prioridad, obligatoria=False, clave=f"seguridad-ti:{v.id}:{origen}")


def _nvd_registros(ahora):
    desde = ahora - timedelta(days=3)
    params = {
        "pubStartDate": desde.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "pubEndDate": ahora.strftime("%Y-%m-%dT%H:%M:%S.000"),
        "resultsPerPage": 2000, "startIndex": 0,
    }
    recopilados = []
    for _ in range(5):
        datos = _descargar(NVD_URL + "?" + urlencode(params))
        if not isinstance(datos, dict) or not isinstance(datos.get("vulnerabilities"), list):
            raise ValueError("Respuesta inesperada de NVD.")
        recopilados.extend(datos["vulnerabilities"])
        if params["startIndex"] + len(datos["vulnerabilities"]) >= int(datos.get("totalResults", 0)):
            return recopilados
        if not datos["vulnerabilities"]:
            break
        params["startIndex"] += len(datos["vulnerabilities"])
    raise ValueError("La paginación de NVD excedió el máximo: no se registró una sincronización incompleta.")


def _nvd_datos(entrada):
    cve = entrada.get("cve") or {}
    if cve.get("vulnStatus", "").lower() in {"rejected", "reject"}:
        return None
    metricas = cve.get("metrics") or {}
    puntuacion = None
    for clave in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
        for m in metricas.get(clave, []):
            try:
                valor = float((m.get("cvssData") or {}).get("baseScore"))
            except (ValueError, TypeError):
                continue
            if puntuacion is None or valor > puntuacion:
                puntuacion = valor
    if puntuacion is None or puntuacion < 7.0:
        return None  # Panel mundial: solo severidad ALTA/CRITICA y KEV completo.
    ingles = next((d.get("value") for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
    identificador = cve.get("id", "")
    return {
        "cve": identificador, "titulo": identificador + " · " + _texto(ingles, 180),
        "descripcion": ingles, "recomendacion": "Validar fabricante, producto y versión; consultar el aviso oficial antes de aplicar cambios.",
        "severidad": "CRITICA" if puntuacion >= 9 else "ALTA",
        "referencia": "https://nvd.nist.gov/vuln/detail/" + identificador,
        "fecha": _fecha(cve.get("published")), "explotada": False,
    }


def _cisa_datos(entrada):
    cve = entrada.get("cveID")
    return {
        "cve": cve,
        "titulo": _texto(entrada.get("vulnerabilityName") or cve, 220),
        "fabricante": entrada.get("vendorProject"),
        "producto": entrada.get("product"),
        "descripcion": entrada.get("shortDescription"),
        "recomendacion": entrada.get("requiredAction"),
        "referencia": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        "fecha": _fecha(entrada.get("dateAdded")),
        "explotada": True,
    }


def sincronizar_fuente(fuente, ahora=None):
    """Transacción por fuente: los fallos conservan el catálogo anterior."""
    if fuente not in {"CISA_KEV", "NVD"}:
        raise ValueError("Fuente no autorizada.")
    ahora = ahora or datetime.utcnow()
    estado = SincronizacionVulnerabilidadesTI.query.filter_by(fuente=fuente).first()
    if estado is None:
        estado = SincronizacionVulnerabilidadesTI(fuente=fuente)
        db.session.add(estado)
    primera = estado.ultimo_exito is None
    estado.ultimo_intento = ahora
    try:
        if fuente == "CISA_KEV":
            json_cisa = _descargar(CISA_URL)
            if not isinstance(json_cisa, dict) or not isinstance(json_cisa.get("vulnerabilities"), list):
                raise ValueError("El catálogo CISA no presenta el formato esperado.")
            entradas = [_cisa_datos(x) for x in json_cisa["vulnerabilities"] if isinstance(x, dict)]
        else:
            entradas = [_nvd_datos(x) for x in _nvd_registros(ahora) if isinstance(x, dict)]
        nuevos, avisados = 0, set()
        for entrada in entradas:
            if entrada is None:
                continue
            v, nuevo, se_volvio_explotada = _actualizar_cve(entrada, fuente)
            if v is None:
                continue
            if nuevo:
                nuevos += 1
            if not primera and (nuevo or se_volvio_explotada):
                db.session.flush()
                if v.id not in avisados:
                    _avisar(v, fuente)
                    avisados.add(v.id)
        estado.ultimo_exito = ahora
        estado.ultimo_error = None
        estado.registros_nuevos = nuevos
        registrar_bitacora("SINCRONIZAR_VULNERABILIDADES", "Seguridad Informática",
                           f"{fuente}: {nuevos} CVE nuevos", usuario_id=None, commit=False)
        db.session.commit()
        return {"fuente": fuente, "nuevos": nuevos, "avisos": len(avisados)}
    except Exception as error:
        db.session.rollback()
        estado = SincronizacionVulnerabilidadesTI.query.filter_by(fuente=fuente).first()
        if estado is None:
            estado = SincronizacionVulnerabilidadesTI(fuente=fuente)
            db.session.add(estado)
        estado.ultimo_intento = ahora
        estado.ultimo_error = _texto(error, 400)
        db.session.commit()
        raise


def sincronizar_todo():
    resultados = []
    for fuente in ("CISA_KEV", "NVD"):
        try:
            resultados.append(sincronizar_fuente(fuente))
        except Exception as error:
            resultados.append({"fuente": fuente, "error": str(error)[:250]})
    return resultados
