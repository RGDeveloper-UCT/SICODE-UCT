from urllib import request as urlrequest
from urllib.error import URLError

from flask import Blueprint, abort, current_app, jsonify, render_template
from flask_login import current_user, login_required

from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes
from app.services.cerebro_sicode_schema import inventariar_esquema_sicode
from app.services.cerebro_sicode_service import analizar_sicode, guardar_hallazgos


nexo_ia_bp = Blueprint("nexo_ia", __name__, url_prefix="/nexo")


def _exigir_acceso():
    if not current_user.puede_modificar:
        abort(403)


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
    except (URLError, TimeoutError, OSError):
        disponible = False
    return {
        "nombre": "Ollama",
        "modo": "IA local",
        "disponible": disponible,
        "modelo": modelo,
    }


@nexo_ia_bp.route("/")
@login_required
def inicio():
    _exigir_acceso()
    return render_template("nexo/inicio.html")


@nexo_ia_bp.route("/estado")
@login_required
def estado():
    _exigir_acceso()

    aprendidas = absorber_verificaciones_pendientes(usuario_id=current_user.id)
    esquema = inventariar_esquema_sicode(usuario_id=current_user.id)
    resultado = analizar_sicode()
    nuevos_hallazgos = guardar_hallazgos(resultado, usuario_id=current_user.id)

    resultado["retroalimentaciones_nuevas"] = aprendidas
    resultado["hallazgos_guardados_nuevos"] = nuevos_hallazgos
    resultado["esquema"] = esquema
    resultado["integraciones"] = {
        "ia_local": _estado_ollama(),
        "postgresql": {"nombre": "PostgreSQL", "modo": "núcleo de datos", "disponible": True},
        "github": {
            "nombre": "GitHub",
            "modo": "código y trazabilidad de desarrollo",
            "disponible": None,
            "nota": "La conexión de desarrollo se gestiona fuera del servidor SICODE y no expone credenciales aquí.",
        },
    }
    resultado["identidad"] = {
        "nombre": "SICODE NEXO",
        "siglas": "NEXO",
        "significado": "Núcleo de Evolución, eXamen y Optimización",
        "mision": "Observar SICODE, aprender de la operación y convertir patrones en mejoras técnicas revisables.",
    }

    if current_user.rol != "administrador":
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
            "tablas_total": esquema["tablas_total"],
            "columnas_total": esquema["columnas_total"],
            "cambio_detectado": esquema["cambio_detectado"],
        }

    return jsonify(resultado)
