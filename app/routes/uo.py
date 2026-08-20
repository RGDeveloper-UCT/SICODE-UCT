from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.security import admin_required
from app.services.bitacora_service import registrar_bitacora
from app.services.presencia_service import listar_usuarios_online, registrar_pulso


uo_bp = Blueprint("uo", __name__)


def _serializar_usuario(item):
    return {
        "id": item["id"],
        "nombre": item["nombre"],
        "usuario": item["usuario"],
        "rol": item["rol"],
        "sesiones": item["sesiones"],
        "pagina": item["pagina"],
        "ruta": item["ruta"],
        "iniciado_en": item["iniciado_en"].isoformat() + "Z",
        "ultimo_pulso_en": item["ultimo_pulso_en"].isoformat() + "Z",
        "segundos_desde_pulso": item["segundos_desde_pulso"],
    }


@uo_bp.route("/presencia/pulso", methods=["POST"])
@login_required
def pulso():
    datos = request.get_json(silent=True) or {}
    ruta = str(datos.get("ruta") or "/").strip()
    if not ruta.startswith("/") or ruta.startswith("//"):
        ruta = "/"

    registrar_pulso(
        usuario_id=current_user.id,
        ruta=ruta,
        pagina=datos.get("pagina"),
    )
    return jsonify({"ok": True})


@uo_bp.route("/admin/uo")
@login_required
@admin_required
def panel():
    registrar_bitacora(
        accion="CONSULTAR_USUARIOS_ONLINE",
        modulo="Administración",
        descripcion="Se consultó el panel UO de usuarios conectados.",
        usuario_id=current_user.id,
    )
    return render_template("admin/uo.html")


@uo_bp.route("/admin/uo/datos")
@login_required
@admin_required
def datos():
    usuarios = listar_usuarios_online()
    return jsonify({
        "usuarios": [_serializar_usuario(item) for item in usuarios],
        "total_usuarios": len(usuarios),
        "total_sesiones": sum(item["sesiones"] for item in usuarios),
    })
