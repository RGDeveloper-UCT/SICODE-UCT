from datetime import datetime
from urllib import request as urlrequest
from urllib.error import URLError

from flask import Blueprint, abort, current_app, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import text

from app import db
from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes
from app.services.cerebro_sicode_schema import inventariar_esquema_sicode
from app.services.cerebro_sicode_service import analizar_sicode, guardar_hallazgos


nexo_ia_bp = Blueprint("nexo_ia", __name__, url_prefix="/nexo")


ESQUEMA_VACIO = {
    "firma": None,
    "tablas_total": 0,
    "columnas_total": 0,
    "cambio_detectado": False,
    "primera_lectura": False,
}


def _exigir_acceso():
    if not current_user.puede_modificar:
        abort(403)


def _resultado_vacio():
    return {
        "aprendizaje": {
            "nivel": 0,
            "muestras": 0,
            "precision": 0,
            "tipos_aprendidos": 0,
        },
        "totales": {
            "expedientes": 0,
            "documentos_indice": 0,
            "registros_coordinacion": 0,
            "muestras_ia": 0,
            "objetos_estudiados": 0,
        },
        "hallazgos": [],
        "hallazgos_total": 0,
        "estado": "degradado",
        "analizado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _registrar_error_etapa(nombre, exc):
    try:
        db.session.rollback()
    except Exception:
        # La sesión puede no haber llegado a abrir una transacción.
        pass
    current_app.logger.exception("SICODE NEXO falló en la etapa %s", nombre)
    return {
        "etapa": nombre,
        "tipo": exc.__class__.__name__,
    }


def _ejecutar_etapa(nombre, funcion, fallback):
    """Ejecuta una etapa de NEXO sin permitir que inutilice todo el panel.

    Cada etapa usa la misma sesión de la aplicación. Si una consulta falla se
    hace rollback antes de continuar para que PostgreSQL no deje la sesión en
    estado abortado y las demás comprobaciones puedan seguir funcionando.
    """
    try:
        return funcion(), None
    except Exception as exc:  # pragma: no cover - el tipo concreto depende del motor/driver
        return fallback, _registrar_error_etapa(nombre, exc)


def _estado_postgresql():
    valor, error = _ejecutar_etapa(
        "postgresql",
        lambda: db.session.execute(text("SELECT 1")).scalar_one(),
        None,
    )
    return {
        "nombre": "PostgreSQL",
        "modo": "núcleo de datos",
        "disponible": error is None and valor == 1,
    }, error


def _estado_ollama():
    base = current_app.config.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    modelo = current_app.config.get(
        "DOCUMENT_ANALYSIS_AI_MODEL",
        current_app.config.get("OLLAMA_MODEL", "qwen3:1.7b"),
    )
    try:
        req = urlrequest.Request(f"{base}/api/tags", headers={"Accept": "application/json"})
        with urlrequest.urlopen(req, timeout=1.5) as response:
            disponible = 200 <= response.status < 300
    except (URLError, TimeoutError, OSError, ValueError):
        disponible = False
    return {
        "nombre": "Ollama",
        "modo": "IA local",
        "disponible": disponible,
        "modelo": modelo,
    }


def _integraciones(postgresql):
    return {
        "ia_local": _estado_ollama(),
        "postgresql": postgresql,
        "github": {
            "nombre": "GitHub",
            "modo": "código y trazabilidad de desarrollo",
            "disponible": None,
            "nota": "La conexión de desarrollo se gestiona fuera del servidor SICODE y no expone credenciales aquí.",
        },
    }


def _identidad():
    return {
        "nombre": "SICODE NEXO",
        "siglas": "NEXO",
        "significado": "Núcleo de Evolución, eXamen y Optimización",
        "mision": "Observar SICODE, aprender de la operación y convertir patrones en mejoras técnicas revisables.",
    }


@nexo_ia_bp.route("/")
@login_required
def inicio():
    _exigir_acceso()
    return render_template("nexo/inicio.html")


@nexo_ia_bp.route("/estado")
@login_required
def estado():
    """Entrega un estado útil aun cuando una subetapa de NEXO falle.

    Antes, cualquier excepción en aprendizaje, inventario, análisis o persistencia
    devolvía HTTP 500 y el panel quedaba completamente en cero. NEXO ahora aísla
    las etapas, recupera la sesión de SQLAlchemy y muestra qué componente requiere
    revisión sin exponer SQL, credenciales ni contenido documental.
    """
    _exigir_acceso()

    errores = []
    omitidas = []
    resultado = _resultado_vacio()
    esquema = dict(ESQUEMA_VACIO)
    aprendidas = 0
    nuevos_hallazgos = 0

    postgresql, error_db = _estado_postgresql()
    if error_db:
        errores.append(error_db)
        omitidas.extend(["aprendizaje", "inventario_esquema", "analisis_sicode", "guardar_hallazgos"])
    else:
        aprendidas, error = _ejecutar_etapa(
            "aprendizaje",
            lambda: absorber_verificaciones_pendientes(usuario_id=current_user.id),
            0,
        )
        if error:
            errores.append(error)

        esquema, error = _ejecutar_etapa(
            "inventario_esquema",
            lambda: inventariar_esquema_sicode(usuario_id=current_user.id),
            dict(ESQUEMA_VACIO),
        )
        if error:
            errores.append(error)

        resultado, error_analisis = _ejecutar_etapa(
            "analisis_sicode",
            analizar_sicode,
            _resultado_vacio(),
        )
        if error_analisis:
            errores.append(error_analisis)
            omitidas.append("guardar_hallazgos")
        else:
            nuevos_hallazgos, error = _ejecutar_etapa(
                "guardar_hallazgos",
                lambda: guardar_hallazgos(resultado, usuario_id=current_user.id),
                0,
            )
            if error:
                errores.append(error)

    resultado["retroalimentaciones_nuevas"] = aprendidas
    resultado["hallazgos_guardados_nuevos"] = nuevos_hallazgos
    resultado["esquema"] = esquema
    resultado["integraciones"] = _integraciones(postgresql)
    resultado["identidad"] = _identidad()

    degradado = bool(errores)
    if degradado:
        resultado["estado"] = "degradado"

    resultado["diagnostico"] = {
        "degradado": degradado,
        "etapas_con_error": [item["etapa"] for item in errores],
        "etapas_omitidas": omitidas,
        "mensaje": (
            "NEXO completó un análisis parcial. Revise las etapas indicadas y la bitácora técnica del servicio."
            if degradado
            else "Todas las etapas principales de NEXO respondieron correctamente."
        ),
    }

    # El detalle técnico se limita al administrador y solo incluye el nombre de
    # la excepción; nunca se envía el mensaje SQL, rutas, credenciales o valores.
    if current_user.rol == "administrador":
        resultado["diagnostico"]["errores"] = errores
    else:
        resultado["hallazgos"] = [
            {
                "categoria": h["categoria"],
                "titulo": h["titulo"],
                "prioridad": h["prioridad"],
                "detalle": "Hallazgo registrado para revisión técnica del sistema.",
                "recomendacion": "Revisión por administración técnica.",
            }
            for h in resultado.get("hallazgos", [])[:5]
        ]
        resultado["esquema"] = {
            "tablas_total": esquema.get("tablas_total", 0),
            "columnas_total": esquema.get("columnas_total", 0),
            "cambio_detectado": esquema.get("cambio_detectado", False),
        }

    return jsonify(resultado)
