"""Canal SSE de invalidaciones para las sesiones autorizadas de SICODE."""
import json

import redis
from flask import Blueprint, Response, current_app, jsonify, stream_with_context
from flask_login import login_required

from app.services.sincronizacion import CANAL

sincronizacion_bp = Blueprint("sincronizacion", __name__, url_prefix="/sincronizacion")


@sincronizacion_bp.get("/estado")
@login_required
def estado():
    if not current_app.config.get("SICODE_REALTIME_ENABLED", True):
        return jsonify({"conectado": False}), 503
    try:
        conexion = redis.Redis.from_url(
            current_app.config["SICODE_REALTIME_REDIS_URL"],
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        conectado = bool(conexion.ping())
        conexion.close()
    except redis.RedisError:
        conectado = False
    return jsonify({"conectado": conectado}), (200 if conectado else 503)


@sincronizacion_bp.get("/eventos")
@login_required
def eventos():
    if not current_app.config.get("SICODE_REALTIME_ENABLED", True):
        return jsonify({"error": "Sincronización no habilitada"}), 503

    conexion = redis.Redis.from_url(
        current_app.config["SICODE_REALTIME_REDIS_URL"],
        socket_connect_timeout=1,
        socket_timeout=25,
        health_check_interval=20,
    )
    try:
        conexion.ping()
    except redis.RedisError:
        conexion.close()
        return jsonify({"error": "El canal de sincronización no está disponible"}), 503

    def transmision():
        pubsub = conexion.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(CANAL)
            yield "event: listo\\ndata: {}\\n\\n"
            while True:
                mensaje = pubsub.get_message(timeout=15)
                if not mensaje:
                    yield ": pulso\\n\\n"
                    continue
                if mensaje.get("type") != "message":
                    continue
                try:
                    datos = json.loads(mensaje["data"])
                    if not isinstance(datos, dict) or "id" not in datos:
                        continue
                except (TypeError, ValueError):
                    continue
                yield "id: " + str(datos["id"]) + "\\nevent: cambio\\ndata: " + json.dumps(
                    datos, separators=(",", ":")
                ) + "\\n\\n"
        except (GeneratorExit, ConnectionError):
            return
        except redis.RedisError:
            current_app.logger.warning("Se interrumpió el canal SSE de SICODE")
        finally:
            pubsub.close()
            conexion.close()

    respuesta = Response(stream_with_context(transmision()), mimetype="text/event-stream")
    respuesta.headers["Cache-Control"] = "no-cache, no-transform, private"
    respuesta.headers["X-Accel-Buffering"] = "no"
    return respuesta
