"""IMPORTF.IA: reemplaza la antigua carga inicial sin tocar otros importadores."""
from collections import defaultdict
import re
import unicodedata
from datetime import date, datetime

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import db
from app.models.documento_expediente import DocumentoExpediente
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.routes.indice_documental import indice_documental_bp, _exigir_modificacion
from app.services.bitacora_service import registrar_bitacora
from app.services.importfia_service import ImportFIAInvalido, leer_importfia
# Contrato anterior conservado para consumidores y pruebas existentes.
from app.services.indice_importacion_legacy_parser import _leer, ImportacionInvalida


def _firmador():
    return URLSafeTimedSerializer(current_app.secret_key, salt="importfia-folios-v1")


def _ambito(documento):
    if not documento.es_anexo:
        return 0
    if documento.indice_numero_anexo is not None:
        return int(documento.indice_numero_anexo)
    recepcion = documento.anexo_recepcion
    if recepcion and str(recepcion.numero_anexo or "").isdigit():
        return int(recepcion.numero_anexo)
    return None


def _cotejar(expediente, filas):
    """No reemplaza verificaciones ni rectificaciones: solo crea folios nuevos sin conflicto."""
    existentes = DocumentoExpediente.query.filter_by(
        expediente_id=expediente.id, activo=True
    ).all()
    decisiones = []
    nuevos = defaultdict(set)
    for r in filas:
        ambito = r["numero"] or 0
        ocupantes = [d for d in existentes if
                     _ambito(d) == ambito and d.folio_inicio <= r["folio"] <= d.folio_fin]
        ambiguos = [d for d in existentes if d.es_anexo and _ambito(d) is None]
        if ambito and ambiguos:
            estado = "CONFLICTO"
            detalle = "Existe anexo activo sin número y no se puede excluir coincidencia."
        elif not expediente.expediente_fisico_registrado:
            estado = "CONFLICTO"
            detalle = "No consta expediente físico registrado en SICODE."
        elif len(ocupantes) == 1 and ocupantes[0].folio_inicio == ocupantes[0].folio_fin == r["folio"] and ocupantes[0].nombre_documento == r["nombre"]:
            estado = "COINCIDE"
            detalle = "Folio ya registrado. Sin cambios."
        elif ocupantes:
            estado = "CONFLICTO"
            detalle = "Folio ocupado por otro registro o rango existente."
        else:
            estado = "NUEVO"
            detalle = "Nuevo metadato; pendiente de verificación institucional."
            nuevos[ambito].add(r["folio"])
        decisiones.append({**r, "estado": estado, "detalle": detalle})
    # No fabricar supuestos folios de un expediente incompleto. Advertencia,
    # sin rellenar ni impedir que un usuario incorpore evidencia parcial.
    avisos = []
    por_ambito = defaultdict(set)
    for d in existentes:
        ambito = _ambito(d)
        if ambito is not None:
            por_ambito[ambito].update(range(d.folio_inicio, d.folio_fin + 1))
    for numero, folios in nuevos.items():
        total = folios | por_ambito[numero]
        if total and min(total) > 1:
            avisos.append(f"{'Principal' if numero == 0 else 'Anexo '+str(numero)}: inicia en folio {min(total)}.")
        if total and len(total) < max(total):
            avisos.append(f"{'Principal' if numero == 0 else 'Anexo '+str(numero)}: hay saltos de foliación; no se completan artificialmente.")
    return decisiones, avisos


def _normalizar_comparacion(valor, campo):
    """Compara el valor completo sin confundir referencias de distinto número.

    Se omiten solo separadores visuales en RC/RE, conservando todas las
    letras y dígitos (incluido RC frente a RE).
    """
    if valor is None:
        return ""
    if isinstance(valor, (date, datetime)):
        return valor.date().isoformat() if isinstance(valor, datetime) else valor.isoformat()
    texto = str(valor).strip()
    if campo == "fecha de recepción":
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(texto, formato).date().isoformat()
            except ValueError:
                pass
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    if campo == "RC/RE":
        return re.sub(r"[^A-Z0-9]", "", texto)
    return " ".join(texto.split())


def _validar_anexos_coordinacion(expediente, anexos):
    """Rechaza contradicciones con recepciones existentes; no crea recepciones."""
    existentes = (AnexoCoordinacion.query.join(RegistroCoordinacion)
                  .filter(RegistroCoordinacion.expediente_id == expediente.id).all())
    for numero, datos in anexos.items():
        coincidencias = [a for a in existentes if str(a.numero_anexo or "").strip() == str(numero)]
        if len(coincidencias) > 1:
            raise ImportFIAInvalido(f"Anexo {numero}: hay varias recepciones con ese número; revise manualmente.")
        if not coincidencias:
            continue
        anexo = coincidencias[0]
        recepcion = anexo.registro
        comparaciones = [
            ("título", datos.get("titulo"), anexo.titulo),
            ("RC/RE", datos.get("numero_referencia"), recepcion.rc),
            ("providencia", datos.get("providencia"), recepcion.providencia),
            ("fecha de recepción", datos.get("fecha_recepcion"),
             recepcion.fecha_recepcion.isoformat() if recepcion.fecha_recepcion else None),
        ]
        for nombre, entrante, vigente in comparaciones:
            if entrante and vigente and _normalizar_comparacion(entrante, nombre) != _normalizar_comparacion(vigente, nombre):
                raise ImportFIAInvalido(
                    f"Anexo {numero}: {nombre} difiere de Coordinación. No se sobrescribirá.")
        if datos.get("es_vencido") in ("SI", "NO") and bool(anexo.es_vencido) != (datos["es_vencido"] == "SI"):
            raise ImportFIAInvalido(f"Anexo {numero}: vigencia contradice el registro de Coordinación.")

@indice_documental_bp.route("/expedientes/<int:expediente_id>/indice-documental/importar", methods=["GET", "POST"])
@login_required
def importar_indice(expediente_id):
    _exigir_modificacion()
    expediente = Expediente.query.get_or_404(expediente_id)
    if not expediente.expediente_fisico_registrado:
        abort(403)
    decisiones, avisos, token = [], [], None
    if request.method == "POST":
        try:
            if request.form.get("accion") == "confirmar":
                try:
                    paquete = _firmador().loads(request.form.get("token", ""), max_age=1800)
                except (BadSignature, SignatureExpired) as exc:
                    raise ImportFIAInvalido("La previsualización caducó o fue alterada.") from exc
                if paquete.get("expediente_id") != expediente.id or paquete.get("usuario_id") != current_user.id:
                    abort(403)
                # Reconsultar la base antes de escribir. Si cambió el cotejo, abortar.
                _validar_anexos_coordinacion(expediente, paquete["anexos"])
                decisiones, avisos = _cotejar(expediente, paquete["folios"])
                resumen = [(r["numero"], r["folio"], r["estado"]) for r in decisiones]
                if resumen != [tuple(x) for x in paquete["resumen"]]:
                    raise ImportFIAInvalido("El índice cambió desde la previsualización. Vuelva a cargar el Excel.")
                if any(r["estado"] == "CONFLICTO" for r in decisiones):
                    raise ImportFIAInvalido("Hay folios en conflicto; no se importará parcialmente.")
                nuevos = [r for r in decisiones if r["estado"] == "NUEVO"]
                if not nuevos:
                    flash("Todos los folios ya coincidían; no hubo cambios.", "info")
                    return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
                for r in nuevos:
                    db.session.add(DocumentoExpediente(
                        expediente_id=expediente.id,
                        nombre_documento=r["nombre"], tipo_documento=r["tipo"],
                        folio_inicio=r["folio"], folio_fin=r["folio"], total_folios=1,
                        estado_revision="Pendiente de revisión",
                        es_anexo=bool(r["numero"]),
                        indice_numero_anexo=r["numero"],
                        indice_titulo_anexo=r["titulo"] or None,
                        indice_orden=r["orden"],
                        observaciones=r["observaciones"], activo=True,
                    ))
                registrar_bitacora(
                    accion="IMPORTFIA_FOLIOS", modulo="Índice documental",
                    descripcion=f"IMPORTF.IA añadió {len(nuevos)} folios al SP {expediente.no_sp}; sin modificar existentes.",
                    usuario_id=current_user.id, expediente_id=expediente.id,
                    entidad="Expediente", entidad_id=expediente.id,
                    datos_posteriores={
                        "filas_nuevas": len(nuevos),
                        "coincidentes": sum(x["estado"] == "COINCIDE" for x in decisiones),
                        "verificacion": "PENDIENTE_INSTITUCIONAL",
                        "anexos": sorted({x["numero"] for x in nuevos if x["numero"]}),
                    }, commit=False)
                db.session.commit()
                flash(f"IMPORTF.IA incorporó {len(nuevos)} folios nuevos; permanecen pendientes de verificación institucional.", "success")
                return redirect(url_for("indice_documental.listado", expediente_id=expediente.id))
            archivo = request.files.get("archivo")
            if not archivo:
                raise ImportFIAInvalido("Seleccione el Excel IMPORTF.IA.")
            folios, _anexos, _ambitos = leer_importfia(archivo, expediente)
            _validar_anexos_coordinacion(expediente, _anexos)
            decisiones, avisos = _cotejar(expediente, folios)
            token = _firmador().dumps({
                "expediente_id": expediente.id,
                "usuario_id": current_user.id,
                "folios": folios,
                "anexos": _anexos,
                "resumen": [(r["numero"], r["folio"], r["estado"]) for r in decisiones],
            })
        except ImportFIAInvalido as exc:
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            raise
    return render_template("indice_documental/importar.html", expediente=expediente,
                           decisiones=decisiones, avisos=avisos, token=token)
