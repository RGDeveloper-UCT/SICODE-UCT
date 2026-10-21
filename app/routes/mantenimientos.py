"""Control 09: mantenimientos con checklist persistente y cronómetro de servidor."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from xml.sax.saxutils import escape

from app import db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.soporte_tecnico import ServicioSoporteTecnico
from app.models.mantenimiento_equipo import MantenimientoEquipo
from app.services.checklist_mantenimiento import plantilla, validar_checklist, validar_cierre, actualizar_checklist_pendiente, VERSION
from app.services.bitacora_service import registrar_bitacora
from app.services.resumen_mantenimiento import resumen_trabajo
from app.services.constancia_mantenimiento_service import generar_constancia_mantenimiento

mantenimientos_bp = Blueprint("mantenimientos", __name__, url_prefix="/coordinacion/seguridad/mantenimientos")
TIPOS = {"PREVENTIVO", "CORRECTIVO", "MIXTO"}
FINALES = {"OPERATIVO", "OBSERVACIONES", "REPARACION", "FUERA_SERVICIO"}

def _escritura():
    if not current_user.puede_modificar:
        abort(403)

def _auditar(m, accion):
    registrar_bitacora(
        accion=accion, modulo="Seguridad Informática", usuario_id=current_user.id,
        descripcion=f"{m.numero} · equipo {m.equipo.codigo}",
        entidad="MantenimientoEquipo", entidad_id=m.id,
        datos_posteriores={"equipo_id": m.equipo_id, "estado": m.estado,
                           "tipo": m.tipo, "segundos": m.segundos(),
                           "boleta_id": m.boleta_id},
        commit=False,
    )

def _snapshot(e):
    return {
        "codigo": e.codigo, "nombre": e.nombre, "tipo": e.tipo,
        "marca": e.marca, "modelo": e.modelo, "serie": e.serie,
        "area": e.area, "ubicacion": e.ubicacion, "ip_estatica": e.ip_estatica,
        "custodio": e.nombre_responsable, "usuario_habitual": e.nombre_usuario_habitual,
    }

@mantenimientos_bp.route("/")
@login_required
def listado():
    q = request.args.get("q", "").strip()[:120]
    consulta = MantenimientoEquipo.query.join(EquipoInstitucional)
    if q:
        consulta = consulta.filter(
            or_(EquipoInstitucional.codigo.ilike(f"%{q}%"),
                   EquipoInstitucional.nombre.ilike(f"%{q}%")))
    page = max(1, request.args.get("page", 1, type=int))
    registros = consulta.order_by(MantenimientoEquipo.id.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("mantenimientos/listado.html", registros=registros, q=q)

@mantenimientos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    _escritura()
    equipos = EquipoInstitucional.query.order_by(EquipoInstitucional.codigo).all()
    if request.method == "POST":
        try:
            equipo_id = int(request.form.get("equipo_id", ""))
            equipo = db.session.get(EquipoInstitucional, equipo_id)
            if not equipo:
                raise ValueError("Seleccione un equipo existente del Inventario Tecnológico.")
            tipo = request.form.get("tipo")
            if tipo not in TIPOS:
                raise ValueError("Tipo de mantenimiento inválido.")
            boleta_id = request.form.get("boleta_id", "").strip()
            boleta = None
            if boleta_id:
                boleta = db.session.get(ServicioSoporteTecnico, int(boleta_id))
                if not boleta or boleta.equipo_institucional_id != equipo.id:
                    raise ValueError("La boleta no pertenece al equipo seleccionado.")
            m = MantenimientoEquipo(
                equipo_id=equipo.id, boleta_id=boleta.id if boleta else None,
                tecnico_id=current_user.id, tipo=tipo, estado="BORRADOR",
                checklist_version=VERSION, checklist=plantilla(),
                datos_equipo=_snapshot(equipo), diagnostico="", trabajo_realizado="",
            )
            db.session.add(m)
            db.session.flush()
            _auditar(m, "CREAR_MANTENIMIENTO_EQUIPO")
            db.session.commit()
            return redirect(url_for("mantenimientos.editar", mantenimiento_id=m.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template("mantenimientos/nuevo.html", equipos=equipos)

@mantenimientos_bp.route("/<int:mantenimiento_id>")
@login_required
def detalle(mantenimiento_id):
    m = db.get_or_404(MantenimientoEquipo, mantenimiento_id)
    return render_template("mantenimientos/detalle.html", m=m)

@mantenimientos_bp.route("/<int:mantenimiento_id>/editar", methods=["GET", "POST"])
@login_required
def editar(mantenimiento_id):
    _escritura()
    m = db.get_or_404(MantenimientoEquipo, mantenimiento_id)
    if m.estado == "FINALIZADO":
        flash("Este mantenimiento está cerrado. El historial es de solo lectura.", "warning")
        return redirect(url_for("mantenimientos.detalle", mantenimiento_id=m.id))
    checklist_actual = actualizar_checklist_pendiente(m.checklist)
    if request.method == "POST":
        try:
            datos = [{"codigo": f["codigo"],
                      "resultado": request.form.get("resultado_" + f["codigo"], "PENDIENTE"),
                      "observacion": request.form.get("observacion_" + f["codigo"], "")}
                     for f in checklist_actual]
            validado = validar_checklist(datos, checklist_actual)
            diagnostico = request.form.get("diagnostico", "").strip()
            trabajo = request.form.get("trabajo_realizado", "").strip()
            final = request.form.get("estado_final", "")
            respaldo_texto = request.form.get("respaldo_gb", "").strip()
            try:
                respaldo = Decimal(respaldo_texto) if respaldo_texto else None
            except InvalidOperation:
                raise ValueError("El tamaño del respaldo debe ser un número válido en GB.")
            if respaldo is not None and (not respaldo.is_finite() or respaldo < 0 or respaldo > Decimal("9999999999.99") or respaldo.as_tuple().exponent < -2):
                raise ValueError("Indique un tamaño de respaldo válido, no negativo y con máximo dos decimales.")
            accion = request.form.get("accion", "guardar")
            if len(diagnostico) > 4000 or len(trabajo) > 8000:
                raise ValueError("Texto demasiado largo.")
            if final and final not in FINALES:
                raise ValueError("Estado final inválido.")
            if accion not in {"guardar", "finalizar"}:
                abort(400)
            if accion == "finalizar":
                validar_cierre(validado)
                if not final or not m.iniciado_en:
                    raise ValueError("Para finalizar indique el estado final e inicie el cronómetro.")
                if m.tramo_iniciado_en:
                    m.cambiar_reloj("pausar")
                m.estado = "FINALIZADO"
                m.cerrado_en = datetime.utcnow()
            m.checklist = validado
            m.checklist_version = VERSION
            m.diagnostico = diagnostico
            m.trabajo_realizado = trabajo
            m.respaldo_gb = respaldo
            m.estado_final = final or None
            m.requiere_seguimiento = request.form.get("requiere_seguimiento") == "si"
            _auditar(m, "FINALIZAR_MANTENIMIENTO_EQUIPO" if accion == "finalizar" else "GUARDAR_MANTENIMIENTO_EQUIPO")
            db.session.commit()
            flash("Mantenimiento finalizado." if accion == "finalizar" else "Borrador guardado.", "success")
            return redirect(url_for("mantenimientos.detalle" if accion == "finalizar" else "mantenimientos.editar", mantenimiento_id=m.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template("mantenimientos/editar.html", m=m, checklist=checklist_actual)

@mantenimientos_bp.route("/<int:mantenimiento_id>/reloj", methods=["POST"])
@login_required
def reloj(mantenimiento_id):
    _escritura()
    m = db.get_or_404(MantenimientoEquipo, mantenimiento_id)
    accion = request.form.get("accion")
    try:
        if accion not in {"iniciar", "pausar"}:
            abort(400)
        m.cambiar_reloj(accion)
        _auditar(m, "RELOJ_MANTENIMIENTO_EQUIPO")
        db.session.commit()
        flash("Cronómetro actualizado.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "warning")
    return redirect(url_for("mantenimientos.editar" if m.estado != "FINALIZADO" else "mantenimientos.detalle", mantenimiento_id=m.id))

@mantenimientos_bp.route("/<int:mantenimiento_id>/pdf")
@login_required
def pdf(mantenimiento_id):
    m = db.get_or_404(MantenimientoEquipo, mantenimiento_id)
    if m.estado != "FINALIZADO":
        flash("El PDF definitivo solo se genera al finalizar el mantenimiento.", "warning")
        return redirect(url_for("mantenimientos.detalle", mantenimiento_id=m.id))
    buffer = generar_constancia_mantenimiento(m)
    registrar_bitacora(
        accion="EXPORTAR_MANTENIMIENTO_PDF", modulo="Seguridad Informática",
        usuario_id=current_user.id, entidad="MantenimientoEquipo", entidad_id=m.id,
        descripcion=f"Constancia PDF de {m.numero}")
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"{m.numero}_mantenimiento.pdf")
