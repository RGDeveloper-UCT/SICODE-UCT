from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.forms.importacion_portadores_form import (
    ConfirmarImportacionPortadoresForm,
    ImportarPortadoresForm,
)
from app.models.importacion_portadores import ImportacionPortadores
from app.services.bitacora_service import registrar_bitacora
from app.services.importacion_portadores_service import (
    ErrorMantaPortadores,
    analizar_manta,
    importar_manta,
)


portadores_bp = Blueprint("portadores", __name__, url_prefix="/expedientes/portadores")


def _carpeta_temporal():
    carpeta = Path(current_app.instance_path) / "importaciones_portadores"
    carpeta.mkdir(parents=True, exist_ok=True)

    limite = datetime.now() - timedelta(hours=24)
    for archivo in carpeta.glob("*"):
        try:
            if datetime.fromtimestamp(archivo.stat().st_mtime) < limite:
                archivo.unlink(missing_ok=True)
        except OSError:
            pass
    return carpeta


@portadores_bp.route("/importar", methods=["GET", "POST"])
@login_required
def importar():
    form = ImportarPortadoresForm()
    resumen = None
    confirmar = None

    if form.validate_on_submit():
        archivo = form.archivo.data
        nombre_original = secure_filename(archivo.filename) or "Sujetos_Portadores.xls"
        token = uuid4().hex
        carpeta = _carpeta_temporal()
        ruta = carpeta / f"{token}.xls"
        meta = carpeta / f"{token}.txt"

        archivo.save(ruta)
        meta.write_text(nombre_original, encoding="utf-8")

        try:
            resumen = analizar_manta(ruta)
            confirmar = ConfirmarImportacionPortadoresForm()
            confirmar.token.data = token
        except ErrorMantaPortadores as error:
            ruta.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            flash(str(error), "danger")
        except Exception as error:
            ruta.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            flash(f"No fue posible analizar la manta: {error}", "danger")

    historial = (
        ImportacionPortadores.query
        .order_by(ImportacionPortadores.creado_en.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "expedientes/importar_portadores.html",
        form=form,
        resumen=resumen,
        confirmar=confirmar,
        historial=historial,
    )


@portadores_bp.route("/importar/confirmar", methods=["POST"])
@login_required
def confirmar_importacion():
    form = ConfirmarImportacionPortadoresForm()
    if not form.validate_on_submit():
        flash("No fue posible validar la sincronización.", "danger")
        return redirect(url_for("portadores.importar"))

    token = (form.token.data or "").strip()
    if not token.isalnum() or len(token) != 32:
        abort(400)

    carpeta = _carpeta_temporal()
    ruta = carpeta / f"{token}.xls"
    meta = carpeta / f"{token}.txt"

    if not ruta.exists() or not meta.exists():
        flash("La previsualización venció. Seleccione nuevamente la manta.", "warning")
        return redirect(url_for("portadores.importar"))

    nombre_original = meta.read_text(encoding="utf-8").strip() or "Sujetos_Portadores.xls"

    try:
        resultado = importar_manta(ruta, current_user.id, nombre_original)
        registrar_bitacora(
            accion="IMPORTAR_PORTADORES",
            modulo="Expedientes",
            descripcion=(
                f"Sincronización de manta {nombre_original}. "
                f"Filas: {resultado['total']}; nuevos: {resultado['nuevos']}; "
                f"actualizados: {resultado['actualizados']}; sin cambios: {resultado['sin_cambios']}; "
                f"omitidos: {resultado['omitidos']}; vínculos de Coordinación resueltos: "
                f"{resultado['vinculados_coordinacion']}."
            ),
            usuario_id=current_user.id,
        )
        flash(
            "Manta sincronizada correctamente: "
            f"{resultado['nuevos']} expedientes nuevos, "
            f"{resultado['actualizados']} actualizados y "
            f"{resultado['vinculados_coordinacion']} registros de Coordinación vinculados.",
            "success",
        )
    except ErrorMantaPortadores as error:
        flash(str(error), "warning")
        return redirect(url_for("portadores.importar"))
    except Exception as error:
        flash(f"La sincronización fue cancelada y no se guardaron cambios: {error}", "danger")
        return redirect(url_for("portadores.importar"))
    finally:
        ruta.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)

    return redirect(url_for("expedientes.listado"))
