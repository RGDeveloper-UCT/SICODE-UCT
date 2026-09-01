from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models.favorito_usuario import FavoritoUsuario


favoritos_bp = Blueprint("favoritos", __name__, url_prefix="/favoritos")
MAX_FAVORITOS = 6


_ICONOS_POR_PREFIJO = (
    ("/dashboard", "grid", "modulo"),
    ("/buscar", "search", "modulo"),
    ("/busqueda", "search", "modulo"),
    ("/expedientes", "folder", "registro"),
    ("/pagos", "payment", "registro"),
    ("/coordinacion/analisis-documental/ia", "ai", "modulo"),
    ("/coordinacion", "coordination", "registro"),
    ("/ca-cct", "shield", "registro"),
    ("/prestamos", "loan", "registro"),
    ("/alertas", "alert", "registro"),
    ("/bitacora", "log", "registro"),
    ("/nexo", "nexo", "modulo"),
    ("/admin/uo", "online", "modulo"),
    ("/admin/usuarios", "users", "modulo"),
    ("/admin/sistema", "system", "modulo"),
    ("/cuenta", "account", "pagina"),
)

_RUTAS_NO_FAVORITAS = ("/favoritos", "/static", "/health", "/login", "/logout")


def _normalizar_url(valor):
    texto = str(valor or "").strip()
    if not texto or len(texto) > 500:
        return None
    partes = urlsplit(texto)
    if partes.scheme or partes.netloc or not partes.path.startswith("/") or partes.path.startswith("//"):
        return None
    if any(partes.path.startswith(prefijo) for prefijo in _RUTAS_NO_FAVORITAS):
        return None
    return urlunsplit(("", "", partes.path, partes.query, partes.fragment))[:500]


def _clasificar(url):
    ruta = urlsplit(url).path
    for prefijo, icono, tipo in _ICONOS_POR_PREFIJO:
        if ruta.startswith(prefijo):
            return icono, tipo
    return "star", "pagina"


def _favoritos_usuario():
    return (
        FavoritoUsuario.query
        .filter_by(usuario_id=current_user.id)
        .order_by(FavoritoUsuario.orden.asc(), FavoritoUsuario.id.asc())
    )


@favoritos_bp.get("/")
@login_required
def listar():
    favoritos = _favoritos_usuario().all()
    return jsonify({
        "favoritos": [favorito.a_dict() for favorito in favoritos],
        "total": len(favoritos),
        "maximo": MAX_FAVORITOS,
    })


@favoritos_bp.post("/")
@login_required
def agregar():
    datos = request.get_json(silent=True) or request.form
    titulo = " ".join(str(datos.get("titulo") or "").split())[:160]
    url = _normalizar_url(datos.get("url"))
    if not titulo:
        titulo = "Acceso SICODE"
    if not url:
        return jsonify({"error": "La página indicada no es un destino interno válido de SICODE."}), 400

    existente = _favoritos_usuario().filter_by(url=url).first()
    if existente:
        return jsonify({
            "favorito": existente.a_dict(),
            "total": _favoritos_usuario().count(),
            "maximo": MAX_FAVORITOS,
            "ya_existia": True,
        })

    total = _favoritos_usuario().count()
    if total >= MAX_FAVORITOS:
        return jsonify({"error": f"Puede guardar un máximo de {MAX_FAVORITOS} favoritos."}), 409

    ultimo_orden = (
        db.session.query(func.max(FavoritoUsuario.orden))
        .filter(FavoritoUsuario.usuario_id == current_user.id)
        .scalar()
        or 0
    )
    icono, tipo = _clasificar(url)
    favorito = FavoritoUsuario(
        usuario_id=current_user.id,
        titulo=titulo,
        url=url,
        icono=icono,
        tipo=tipo,
        orden=min(int(ultimo_orden) + 1, MAX_FAVORITOS),
    )
    db.session.add(favorito)
    db.session.commit()
    return jsonify({
        "favorito": favorito.a_dict(),
        "total": total + 1,
        "maximo": MAX_FAVORITOS,
        "ya_existia": False,
    }), 201


@favoritos_bp.delete("/<int:favorito_id>")
@login_required
def eliminar(favorito_id):
    favorito = FavoritoUsuario.query.filter_by(id=favorito_id, usuario_id=current_user.id).first_or_404()
    db.session.delete(favorito)
    db.session.flush()

    restantes = _favoritos_usuario().all()
    for indice, item in enumerate(restantes, start=1):
        item.orden = indice
    db.session.commit()

    return jsonify({
        "eliminado": favorito_id,
        "total": len(restantes),
        "maximo": MAX_FAVORITOS,
    })
