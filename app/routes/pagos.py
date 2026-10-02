from collections import defaultdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from app import db
from app.forms.pagos_form import PagoSPForm
from app.models.boleta_pago import BoletaPagoSP
from app.models.coordinacion import PagoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.services.bitacora_service import registrar_bitacora
from app.services.pagos_boleta_pdf_service import (
    BANCO_DEFAULT,
    BASE_LEGAL_DEFAULT,
    CUENTA_DEFAULT,
    CUENTA_NOMBRE_DEFAULT,
    TARIFA_DIA,
    TARIFA_MES,
    DatosBoletaPago,
    generar_boleta_pago_pdf,
)
from app.services.pagos_service import ahora_guatemala, resumen_solvencia_actual
from app.services.sp_service import resolver_expediente


pagos_bp = Blueprint("pagos", __name__, url_prefix="/pagos")

MAX_COMPROBANTE_BYTES = 12 * 1024 * 1024
BANCOS_SUGERIDOS = (
    "BANTRAB",
    BANCO_DEFAULT,
    "BANRURAL",
    "BANCO INDUSTRIAL",
    "G&T CONTINENTAL",
    "BAM",
    "BAC",
    "BANTRAB",
    "CHN",
    "PROMERICA",
    "FICOHSA",
)


def _fecha_arg(nombre):
    valor = (request.args.get(nombre) or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _filtros_actuales():
    return {
        "q": (request.args.get("q") or "").strip(),
        "no_sp": (request.args.get("no_sp") or "").strip(),
        "banco": (request.args.get("banco") or "").strip(),
        "tipo_referencia": (request.args.get("tipo_referencia") or "").strip().upper(),
        "fecha_desde": (request.args.get("fecha_desde") or "").strip(),
        "fecha_hasta": (request.args.get("fecha_hasta") or "").strip(),
    }


def _consulta_filtrada(expediente_id=None):
    filtros = _filtros_actuales()
    consulta = (
        PagoCoordinacion.query
        .join(RegistroCoordinacion, PagoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(RegistroCoordinacion.tipo == "PAGO")
    )

    if expediente_id is not None:
        consulta = consulta.filter(RegistroCoordinacion.expediente_id == expediente_id)
    elif filtros["no_sp"]:
        consulta = consulta.filter(RegistroCoordinacion.no_sp_referencia == filtros["no_sp"])

    if filtros["q"]:
        patron = f"%{filtros['q']}%"
        consulta = consulta.filter(or_(
            RegistroCoordinacion.no_sp_referencia.ilike(patron),
            RegistroCoordinacion.providencia.ilike(patron),
            RegistroCoordinacion.rc.ilike(patron),
            PagoCoordinacion.boleta.ilike(patron),
            PagoCoordinacion.banco.ilike(patron),
        ))

    if filtros["banco"]:
        consulta = consulta.filter(PagoCoordinacion.banco == filtros["banco"])

    if filtros["tipo_referencia"] in {"RC", "RE"}:
        consulta = consulta.filter(
            or_(
                RegistroCoordinacion.rc == filtros["tipo_referencia"],
                RegistroCoordinacion.rc.ilike(f"{filtros['tipo_referencia']} %"),
            )
        )

    fecha_desde = _fecha_arg("fecha_desde")
    fecha_hasta = _fecha_arg("fecha_hasta")
    if fecha_desde:
        consulta = consulta.filter(RegistroCoordinacion.fecha_recepcion >= fecha_desde)
    if fecha_hasta:
        consulta = consulta.filter(RegistroCoordinacion.fecha_recepcion <= fecha_hasta)

    return consulta, filtros


def _bancos_disponibles():
    existentes = [
        banco for (banco,) in (
            db.session.query(PagoCoordinacion.banco)
            .filter(PagoCoordinacion.banco.isnot(None), PagoCoordinacion.banco != "")
            .distinct()
            .order_by(PagoCoordinacion.banco.asc())
            .all()
        )
        if banco
    ]
    vistos = set()
    resultado = []
    for banco in (*BANCOS_SUGERIDOS, *existentes):
        clave = banco.strip().casefold()
        if clave and clave not in vistos:
            vistos.add(clave)
            resultado.append(banco.strip())
    return resultado


def _sp_disponibles():
    return Expediente.query.filter(Expediente.activo.is_(True)).order_by(Expediente.no_sp.asc()).all()


def _numero_referencia(tipo, numero):
    tipo = (tipo or "RC").strip().upper()
    if tipo not in {"RC", "RE"}:
        tipo = "RC"
    numero = (numero or "").strip()
    partes = numero.split(maxsplit=1)
    if partes and partes[0].upper() in {"RC", "RE"}:
        numero = partes[1].strip() if len(partes) > 1 else ""
    return f"{tipo} {numero}".strip()


def _nombre_sp(expediente):
    return (
        (expediente.nombre_referencia or "").strip()
        or " ".join(
            parte.strip()
            for parte in (expediente.nombres or "", expediente.apellidos or "")
            if parte and parte.strip()
        )
        or f"SP {expediente.no_sp}"
    )


def _datos_sp(expediente):
    return {
        "no_sp": expediente.no_sp,
        "nombre_sujeto": _nombre_sp(expediente),
        "expediente_oj": expediente.expediente_oj or "",
        "organo_jurisdiccional": expediente.juzgado_tribunal or "",
    }


def _precargar_formulario(form, expediente):
    datos = _datos_sp(expediente)
    if not form.nombre_sujeto.data:
        form.nombre_sujeto.data = datos["nombre_sujeto"]
    if not form.expediente_oj.data:
        form.expediente_oj.data = datos["expediente_oj"]
    if not form.organo_jurisdiccional.data:
        form.organo_jurisdiccional.data = datos["organo_jurisdiccional"]


@pagos_bp.route("")
@pagos_bp.route("/")
@login_required
def inicio():
    consulta, filtros = _consulta_filtrada()
    pagos = consulta.order_by(RegistroCoordinacion.creado_en.desc()).all()

    total_monto = sum((pago.total or Decimal("0.00") for pago in pagos), Decimal("0.00"))
    sp_unicos = {pago.registro.expediente_id for pago in pagos if pago.registro.expediente_id is not None}
    promedio = total_monto / len(pagos) if pagos else Decimal("0.00")

    por_banco = defaultdict(lambda: {"cantidad": 0, "monto": Decimal("0.00")})
    por_mes = defaultdict(lambda: {"cantidad": 0, "monto": Decimal("0.00")})
    for pago in pagos:
        banco = (pago.banco or "Sin dato").strip() or "Sin dato"
        por_banco[banco]["cantidad"] += 1
        por_banco[banco]["monto"] += pago.total or Decimal("0.00")

        fecha_registro = pago.registro.fecha_recepcion
        clave_mes = fecha_registro.strftime("%Y-%m") if fecha_registro else "Sin fecha"
        por_mes[clave_mes]["cantidad"] += 1
        por_mes[banco]["cantidad"] += 0
        por_mes[clave_mes]["monto"] += pago.total or Decimal("0.00")

    bancos_grafica = [
        {"nombre": nombre, **datos}
        for nombre, datos in sorted(por_banco.items(), key=lambda item: item[1]["monto"], reverse=True)
    ]
    meses_grafica = [
        {"nombre": nombre, **datos}
        for nombre, datos in sorted(por_mes.items(), reverse=True)[:12]
        if datos["cantidad"] > 0
    ]
    meses_grafica.reverse()

    max_banco = max((item["monto"] for item in bancos_grafica), default=Decimal("0.00"))
    max_mes = max((item["monto"] for item in meses_grafica), default=Decimal("0.00"))
    for item in bancos_grafica:
        item["porcentaje"] = float((item["monto"] / max_banco * 100) if max_banco else 0)
    for item in meses_grafica:
        item["porcentaje"] = float((item["monto"] / max_mes * 100) if max_mes else 0)

    return render_template(
        "pagos/dashboard.html",
        filtros=filtros,
        pagos=pagos,
        recientes=pagos[:12],
        total_monto=total_monto,
        total_pagos=len(pagos),
        sp_unicos=len(sp_unicos),
        promedio=promedio,
        bancos_grafica=bancos_grafica,
        meses_grafica=meses_grafica,
        bancos=_bancos_disponibles(),
        sps=_sp_disponibles(),
        solvencia=resumen_solvencia_actual(),
    )


@pagos_bp.route("/api/sp")
@login_required
def api_sp():
    no_sp = (request.args.get("sp") or "").strip()
    expediente, normalizado = resolver_expediente(no_sp)
    if not expediente:
        return jsonify({"ok": False, "error": f"El SP {normalizado or no_sp} no existe."}), 404
    return jsonify({"ok": True, **_datos_sp(expediente)})


@pagos_bp.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    form = PagoSPForm()
    if request.method == "GET":
        form.fecha_comprobante.data = ahora_guatemala().date()
        if not form.banco.data:
            form.banco.data = BANCO_DEFAULT
        if form.dias_aplicados.data is None:
            form.dias_aplicados.data = 0
        if form.meses_aplicados.data is None:
            form.meses_aplicados.data = 1

        no_sp_get = (request.args.get("sp") or "").strip()
        if no_sp_get:
            form.no_sp.data = no_sp_get
            expediente_get, _ = resolver_expediente(no_sp_get)
            if expediente_get:
                _precargar_formulario(form, expediente_get)

    if form.validate_on_submit():
        expediente, no_sp = resolver_expediente(form.no_sp.data)
        if not expediente:
            form.no_sp.errors.append(f"El SP {no_sp or form.no_sp.data} no existe en el registro maestro de SICODE.")
        else:
            _precargar_formulario(form, expediente)
            banco = (form.banco.data or BANCO_DEFAULT).strip()
            boleta = (form.boleta.data or "").strip()
            duplicado = (
                PagoCoordinacion.query
                .filter(
                    func.lower(PagoCoordinacion.banco) == banco.lower(),
                    PagoCoordinacion.boleta == boleta,
                )
                .first()
            )
            if duplicado:
                form.boleta.errors.append("Esta boleta ya está registrada para el mismo banco.")
            else:
                comprobante_archivo = form.comprobante.data
                comprobante_bytes = comprobante_archivo.read() if comprobante_archivo else b""
                if not comprobante_bytes:
                    form.comprobante.errors.append("El comprobante bancario está vacío.")
                elif len(comprobante_bytes) > MAX_COMPROBANTE_BYTES:
                    form.comprobante.errors.append("El comprobante bancario no puede superar 12 MB.")
                else:
                    referencia = _numero_referencia(form.tipo_referencia.data, form.numero_referencia.data)
                    datos_boleta = DatosBoletaPago(
                        fecha_comprobante=form.fecha_comprobante.data,
                        no_sp=expediente.no_sp,
                        numero_expediente=(form.expediente_oj.data or expediente.expediente_oj or "").strip(),
                        organo_jurisdiccional=(
                            form.organo_jurisdiccional.data or expediente.juzgado_tribunal or ""
                        ).strip(),
                        nombre_sujeto=(form.nombre_sujeto.data or _nombre_sp(expediente)).strip(),
                        periodo_desde=form.periodo_desde.data,
                        periodo_hasta=form.periodo_hasta.data,
                        dias_aplicados=form.dias_aplicados.data or 0,
                        meses_aplicados=form.meses_aplicados.data or 0,
                        numero_boleta=boleta,
                        elaborado_por=current_user.nombre,
                        contacto=(form.contacto.data or "").strip(),
                        banco=banco,
                    )

                    if datos_boleta.total <= 0:
                        form.monto.errors.append("La cantidad calculada debe ser mayor que cero.")
                    else:
                        ahora = ahora_guatemala()
                        momento_local = ahora.replace(tzinfo=None)
                        nombre_comprobante = secure_filename(comprobante_archivo.filename or "comprobante")
                        comprobante_mime = (comprobante_archivo.mimetype or "application/octet-stream").lower()

                        try:
                            documento = generar_boleta_pago_pdf(
                                datos_boleta,
                                comprobante=comprobante_bytes,
                                comprobante_mime=comprobante_mime,
                            )
                        except Exception as exc:
                            current_app.logger.warning(
                                "No se pudo generar la boleta PDF de pago para SP %s",
                                expediente.no_sp,
                                exc_info=exc,
                            )
                            form.comprobante.errors.append(
                                "No se pudo procesar el comprobante. Verifique que el archivo sea una imagen o PDF válido."
                            )
                        else:
                            registro = RegistroCoordinacion(
                                tipo="PAGO",
                                expediente_id=expediente.id,
                                no_sp_referencia=expediente.no_sp,
                                rc=referencia,
                                providencia=(form.providencia.data or "").strip(),
                                fecha_recepcion=ahora.date(),
                                usuario_id=current_user.id,
                                usuario_origen=current_user.nombre,
                                estado="Completo",
                                observaciones=(form.observaciones.data or "").strip() or None,
                                origen_registro="MANUAL",
                                creado_en=momento_local,
                                actualizado_en=momento_local,
                            )
                            db.session.add(registro)
                            db.session.flush()

                            pago = PagoCoordinacion(
                                registro_id=registro.id,
                                periodo_desde=form.periodo_desde.data,
                                periodo_hasta=form.periodo_hasta.data,
                                periodo_texto=None,
                                boleta=boleta,
                                banco=banco,
                                total=documento["total"],
                            )
                            db.session.add(pago)
                            db.session.flush()

                            boleta_pdf = BoletaPagoSP(
                                pago_id=pago.id,
                                plantilla_version=documento["plantilla_version"],
                                fecha_comprobante=datos_boleta.fecha_comprobante,
                                expediente_numero=datos_boleta.numero_expediente or None,
                                organo_jurisdiccional=datos_boleta.organo_jurisdiccional or None,
                                nombre_sujeto=datos_boleta.nombre_sujeto,
                                dias_aplicados=datos_boleta.dias_aplicados,
                                meses_aplicados=datos_boleta.meses_aplicados,
                                tarifa_dia=TARIFA_DIA,
                                tarifa_mes=TARIFA_MES,
                                banco_snapshot=datos_boleta.banco,
                                cuenta_snapshot=CUENTA_DEFAULT,
                                cuenta_nombre_snapshot=CUENTA_NOMBRE_DEFAULT,
                                elaborado_por_snapshot=datos_boleta.elaborado_por or None,
                                contacto_snapshot=datos_boleta.contacto or None,
                                base_legal_snapshot=BASE_LEGAL_DEFAULT,
                                comprobante_nombre=nombre_comprobante,
                                comprobante_mime=comprobante_mime,
                                comprobante_sha256=sha256(comprobante_bytes).hexdigest(),
                                pdf_nombre=documento["nombre"],
                                pdf_mime=documento["mime"],
                                pdf_sha256=documento["sha256"],
                                pdf_bytes=documento["bytes"],
                                generado_en=momento_local,
                            )
                            db.session.add(boleta_pdf)
                            db.session.flush()

                            registrar_bitacora(
                                accion="REGISTRAR_PAGO_SP",
                                modulo="Pagos",
                                descripcion=(
                                    f"Se registró pago y boleta PDF del SP {expediente.no_sp}, "
                                    f"boleta {boleta}, período "
                                    f"{form.periodo_desde.data.strftime('%d/%m/%Y')} al "
                                    f"{form.periodo_hasta.data.strftime('%d/%m/%Y')}."
                                ),
                                usuario_id=current_user.id,
                                expediente_id=expediente.id,
                                entidad="PagoCoordinacion",
                                entidad_id=pago.id,
                                datos_posteriores={
                                    "sp": expediente.no_sp,
                                    "referencia": referencia,
                                    "providencia": registro.providencia,
                                    "banco": banco,
                                    "boleta": boleta,
                                    "monto": str(pago.total),
                                    "periodo_desde": str(pago.periodo_desde),
                                    "periodo_hasta": str(pago.periodo_hasta),
                                    "dias_aplicados": datos_boleta.dias_aplicados,
                                    "meses_aplicados": datos_boleta.meses_aplicados,
                                    "plantilla_pdf": boleta_pdf.plantilla_version,
                                    "pdf_sha256": boleta_pdf.pdf_sha256,
                                    "comprobante_sha256": boleta_pdf.comprobante_sha256,
                                    "registrado_en": momento_local.isoformat(sep=" ", timespec="seconds"),
                                },
                                commit=False,
                            )
                            db.session.commit()
                            flash(
                                f"Pago del SP {expediente.no_sp} registrado y boleta PDF generada correctamente.",
                                "success",
                            )
                            return redirect(url_for("pagos.boleta_pdf", pago_id=pago.id))

    monto_calculado = (
        Decimal(form.dias_aplicados.data or 0) * TARIFA_DIA
        + Decimal(form.meses_aplicados.data or 0) * TARIFA_MES
    )
    return render_template(
        "pagos/registrar.html",
        form=form,
        ahora_gt=ahora_guatemala(),
        bancos=_bancos_disponibles(),
        sps=_sp_disponibles(),
        tarifa_dia=TARIFA_DIA,
        tarifa_mes=TARIFA_MES,
        monto_calculado=monto_calculado,
        cuenta_bantrab=CUENTA_DEFAULT,
        cuenta_nombre=CUENTA_NOMBRE_DEFAULT,
    )


@pagos_bp.route("/<int:pago_id>/boleta.pdf")
@login_required
def boleta_pdf(pago_id):
    pago = PagoCoordinacion.query.get_or_404(pago_id)
    boleta = pago.boleta_pdf
    if boleta is None:
        abort(404)

    registrar_bitacora(
        accion="CONSULTAR_BOLETA_PAGO_PDF",
        modulo="Pagos",
        descripcion=(
            f"Se consultó la boleta PDF del SP {pago.registro.no_sp_referencia or 'sin SP'}, "
            f"boleta {pago.boleta or pago.id}."
        ),
        usuario_id=current_user.id,
        expediente_id=pago.registro.expediente_id,
        entidad="BoletaPagoSP",
        entidad_id=boleta.id,
        datos_posteriores={
            "pago_id": pago.id,
            "pdf_sha256": boleta.pdf_sha256,
            "plantilla_version": boleta.plantilla_version,
        },
    )

    descargar = (request.args.get("descargar") or "").lower() in {"1", "true", "si", "sí"}
    return send_file(
        BytesIO(boleta.pdf_bytes),
        mimetype=boleta.pdf_mime or "application/pdf",
        as_attachment=descargar,
        download_name=boleta.pdf_nombre,
        max_age=0,
    )


@pagos_bp.route("/historico")
@login_required
def historico():
    consulta, filtros = _consulta_filtrada()
    pagina = max(request.args.get("page", 1, type=int), 1)
    paginacion = consulta.order_by(RegistroCoordinacion.creado_en.desc()).paginate(
        page=pagina,
        per_page=60,
        error_out=False,
    )
    return render_template(
        "pagos/historico.html",
        expediente=None,
        estado_solvencia=None,
        pagos=paginacion.items,
        paginacion=paginacion,
        filtros=filtros,
        bancos=_bancos_disponibles(),
        sps=_sp_disponibles(),
    )


@pagos_bp.route("/sp/<int:expediente_id>")
@login_required
def sp(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)
    consulta, filtros = _consulta_filtrada(expediente_id=expediente.id)
    pagina = max(request.args.get("page", 1, type=int), 1)
    paginacion = consulta.order_by(RegistroCoordinacion.creado_en.desc()).paginate(
        page=pagina,
        per_page=60,
        error_out=False,
    )
    return render_template(
        "pagos/historico.html",
        expediente=expediente,
        estado_solvencia=expediente.solvencia_pago,
        pagos=paginacion.items,
        paginacion=paginacion,
        filtros=filtros,
        bancos=_bancos_disponibles(),
        sps=_sp_disponibles(),
    )
