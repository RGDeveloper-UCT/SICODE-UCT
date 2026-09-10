import re

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.routes.indice_documental import _exigir_modificacion, indice_documental_bp
from app.services.bitacora_service import registrar_bitacora


MIN_NUMERO_ANEXO = 1
MAX_NUMERO_ANEXO = 200


def _numero_anexo_entero(valor):
    texto = str(valor or "").strip()
    if not texto or not re.fullmatch(r"\d+", texto):
        return None
    numero = int(texto)
    if numero < MIN_NUMERO_ANEXO or numero > MAX_NUMERO_ANEXO:
        return None
    return numero


def _renumerar_titulo_anexo(nombre_documento, numero_anexo):
    """Sincroniza el prefijo visible sin alterar el título documental."""
    nombre = (nombre_documento or "").strip()
    coincidencia = re.match(
        r"^\s*Anexo\s+[^\-–—]+?\s*[\-–—]\s*(.+)$",
        nombre,
        flags=re.IGNORECASE,
    )
    if not coincidencia:
        return nombre
    titulo = coincidencia.group(1).strip()
    return f"Anexo {numero_anexo} - {titulo}" if titulo else f"Anexo {numero_anexo}"


def _buscar_anexo_duplicado(expediente_id, anexo_actual_id, numero_nuevo):
    """Compara numéricamente para detectar también variantes como 03 vs 3."""
    candidatos = (
        AnexoCoordinacion.query
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id == expediente_id,
            AnexoCoordinacion.id != anexo_actual_id,
            AnexoCoordinacion.numero_anexo.isnot(None),
        )
        .order_by(AnexoCoordinacion.id.asc())
        .all()
    )
    for candidato in candidatos:
        if _numero_anexo_entero(candidato.numero_anexo) == numero_nuevo:
            return candidato
    return None


@indice_documental_bp.route(
    "/expedientes/<int:expediente_id>/indice-documental/<int:documento_id>/editar-numero-anexo",
    methods=["POST"],
)
@login_required
def editar_numero_anexo(expediente_id, documento_id):
    """Corrige el número físico de un anexo ya incorporado, con trazabilidad."""
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)
    documento = DocumentoExpediente.query.filter_by(
        id=documento_id,
        expediente_id=expediente.id,
        activo=True,
        es_anexo=True,
    ).first_or_404()

    anexo = documento.anexo_recepcion
    if not anexo:
        flash(
            "Este anexo fue creado manualmente y no tiene un número de recepción de Coordinación para modificar.",
            "warning",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    numero_nuevo = _numero_anexo_entero(request.form.get("numero_anexo"))
    if numero_nuevo is None:
        flash(
            f"El número de anexo debe ser un entero entre {MIN_NUMERO_ANEXO} y {MAX_NUMERO_ANEXO}.",
            "danger",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    numero_nuevo_texto = str(numero_nuevo)
    numero_anterior = (anexo.numero_anexo or "").strip() or None
    nombre_anterior = documento.nombre_documento

    duplicado = _buscar_anexo_duplicado(expediente.id, anexo.id, numero_nuevo)
    if duplicado:
        flash(
            f"No se puede asignar Anexo {numero_nuevo}: ese número ya está registrado para este SP. Revise el anexo existente antes de continuar.",
            "danger",
        )
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    nombre_nuevo = _renumerar_titulo_anexo(documento.nombre_documento, numero_nuevo_texto)
    if numero_anterior == numero_nuevo_texto and nombre_nuevo == nombre_anterior:
        flash(f"El registro ya corresponde al Anexo {numero_nuevo}.", "info")
        return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))

    anexo.numero_anexo = numero_nuevo_texto
    documento.nombre_documento = nombre_nuevo

    registrar_bitacora(
        accion="EDITAR_NUMERO_ANEXO_INDICE",
        modulo="Índice documental",
        descripcion=(
            f"Se corrigió el número del anexo vinculado al SP {expediente.no_sp}: "
            f"{numero_anterior or 's/n'} → {numero_nuevo_texto}."
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="AnexoCoordinacion",
        entidad_id=anexo.id,
        datos_anteriores={
            "numero_anexo": numero_anterior,
            "nombre_documento": nombre_anterior,
            "documento_expediente_id": documento.id,
        },
        datos_posteriores={
            "numero_anexo": numero_nuevo_texto,
            "nombre_documento": documento.nombre_documento,
            "documento_expediente_id": documento.id,
        },
        commit=False,
    )
    db.session.commit()

    flash(f"Número actualizado correctamente: Anexo {numero_nuevo}.", "success")
    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
