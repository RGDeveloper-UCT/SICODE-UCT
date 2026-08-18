from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user


def admin_required(funcion):
    """Restringe una vista a usuarios con rol administrador."""

    @wraps(funcion)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.rol != "administrador":
            flash("No tiene permisos para acceder a esta operación.", "danger")
            return redirect(url_for("dashboard.inicio"))
        return funcion(*args, **kwargs)

    return wrapper


def es_url_interna(destino):
    """Acepta únicamente destinos del mismo host para evitar open redirects."""
    if not destino:
        return False

    host = urlparse(request.host_url)
    objetivo = urlparse(urljoin(request.host_url, destino))
    return objetivo.scheme in ("http", "https") and objetivo.netloc == host.netloc
