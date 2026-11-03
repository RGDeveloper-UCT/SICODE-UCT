"""Segunda modalidad del correlativo BSI: solo medidas CERT 4.1 y 4.2."""
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.seguridad_operativa import BoletaSeguridadTI
from app.routes.seguridad_operativa import (
    seguridad_operativa_bp, TIPOS_EQUIPO, RESULTADOS, _escritura, _texto,
    _snapshot, _auditoria,
)
from app.services.checklist_medidas_seguridad import (
    VERSION_MEDIDAS, plantilla_medidas, validar_medidas,
)


@seguridad_operativa_bp.route("/boletas/medidas/nueva", methods=["GET", "POST"])
@login_required
def nueva_boleta_medidas():
    _escritura()
    equipos = EquipoInstitucional.query.filter(
        EquipoInstitucional.tipo.in_(TIPOS_EQUIPO)
    ).order_by(EquipoInstitucional.codigo).all()
    preseleccionado = request.args.get("equipo_id", type=int)
    if request.method == "POST":
        try:
            equipo = db.session.get(EquipoInstitucional, int(request.form.get("equipo_id", "")))
            if equipo is None or equipo.tipo not in TIPOS_EQUIPO:
                raise ValueError("Seleccione una computadora existente del Inventario Tecnológico.")
            b = BoletaSeguridadTI(
                equipo_id=equipo.id,
                tecnico_id=current_user.id,
                tipo_boleta="MEDIDAS",
                estado="BORRADOR",
                checklist_version=VERSION_MEDIDAS,
                checklist=plantilla_medidas(),
                datos_equipo=_snapshot(equipo),
            )
            db.session.add(b)
            db.session.flush()
            _auditoria("CREAR_BOLETA_MEDIDAS", "BoletaSeguridadTI", b.id,
                       f"{b.numero}: Medidas prioritarias y temporales")
            db.session.commit()
            return redirect(url_for("seguridad_operativa.editar_boleta_medidas", id_=b.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template(
        "seguridad_operativa/nueva_medidas.html",
        equipos=equipos, preseleccionado=preseleccionado,
        total_medidas=len(plantilla_medidas()),
    )


@seguridad_operativa_bp.route("/boletas/<int:id_>/medidas/editar", methods=["GET", "POST"])
@login_required
def editar_boleta_medidas(id_):
    _escritura()
    b = db.get_or_404(BoletaSeguridadTI, id_)
    if b.tipo_boleta != "MEDIDAS":
        abort(404)
    if b.estado in ("FINALIZADO", "ANULADA"):
        flash("Esta boleta ya está cerrada o anulada y es de solo lectura.", "warning")
        return redirect(url_for("seguridad_operativa.detalle_boleta", id_=id_))
    if request.method == "POST":
        try:
            accion = request.form.get("accion")
            if accion not in {"guardar", "finalizar"}:
                abort(400)
            datos = [
                {"codigo": f["codigo"],
                 "resultado": request.form.get("resultado_" + f["codigo"], "PENDIENTE"),
                 "observacion": request.form.get("observacion_" + f["codigo"], "")}
                for f in b.checklist
            ]
            versiones = {}
            for campo in ("chrome", "java", "python", "php"):
                versiones[campo] = _texto("version_" + campo, 100)
                instalado = _texto("instalado_" + campo, 16) or "NO_VERIFICADO"
                if instalado not in {"SI", "NO", "NO_VERIFICADO"}:
                    raise ValueError("Instalación inválida de " + campo)
                versiones["instalado_" + campo] = instalado
            checklist = validar_medidas(datos, b.checklist, versiones,
                                        finalizar=accion == "finalizar")
            diagnostico = _texto("diagnostico", 4000)
            acciones = _texto("acciones", 8000)
            resultado = _texto("resultado_final", 30) or None
            if resultado and resultado not in RESULTADOS:
                raise ValueError("Resultado final inválido.")
            if accion == "finalizar":
                if not b.iniciado_en or not resultado:
                    raise ValueError("Inicie el cronómetro y seleccione el resultado final antes de cerrar.")
                if b.tramo_iniciado_en:
                    b.cambiar_reloj("pausar")
                b.estado = "FINALIZADO"
                b.cerrado_en = datetime.utcnow()
            b.checklist = checklist
            b.versiones = versiones
            b.diagnostico = diagnostico
            b.acciones = acciones
            b.resultado_final = resultado
            b.requiere_seguimiento = request.form.get("requiere_seguimiento") == "si"
            _auditoria("FINALIZAR_BOLETA_MEDIDAS" if accion == "finalizar" else "GUARDAR_BOLETA_MEDIDAS",
                       "BoletaSeguridadTI", b.id, b.numero, {
                           "tipo_boleta": b.tipo_boleta, "estado": b.estado,
                           "segundos": b.segundos(),
                       })
            db.session.commit()
            flash("Boleta de medidas finalizada." if accion == "finalizar" else "Avance guardado.", "success")
            return redirect(url_for(
                "seguridad_operativa.detalle_boleta" if accion == "finalizar"
                else "seguridad_operativa.editar_boleta_medidas", id_=id_,
            ))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template("seguridad_operativa/editar_medidas.html", b=b,
                           checklist=b.checklist)
