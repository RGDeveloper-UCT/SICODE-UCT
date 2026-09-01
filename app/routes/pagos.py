from collections import defaultdict
from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.forms.pagos_form import PagoSPForm
from app.models.coordinacion import PagoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.services.bitacora_service import registrar_bitacora
from app.services.pagos_service import ahora_guatemala, resumen_solvencia_actual
from app.services.sp_service import resolver_expediente


pagos_bp = Blueprint("pagos", __name__, url_prefix="/pagos")

BANCOS_SUGERIDOS = (
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
        por_mes[clave_mes]["monto"] += pago.total or Decimal("0.00")

    bancos_grafica = [
        {"nombre": nombre, **datos}
        for nombre, datos in sorted(por_banco.items(), key=lambda item: item[1]["monto"], reverse=True)
    ]
    meses_grafica = [
        {"nombre": nombre, **datos}
        for nombre, datos in sorted(por_mes.items(), reverse=True)[:12]
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


@pagos_bp.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    form = PagoSPForm()
    if request.method == "GET" and request.args.get("sp"):
        form.no_sp.data = request.args.get("sp", "").strip()

    if form.validate_on_submit():
        expediente, no_sp = resolver_expediente(form.no_sp.data)
        if not expediente:
            form.no_sp.errors.append(f"El SP {no_sp or form.no_sp.data} no existe en el registro maestro de SICODE.")
        else:
            banco = (form.banco.data or "").strip()
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
                ahora = ahora_guatemala()
                momento_local = ahora.replace(tzinfo=None)
                referencia = _numero_referencia(form.tipo_referencia.data, form.numero_referencia.data)

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
                    total=form.monto.data,
                )
                db.session.add(pago)
                db.session.flush()

                registrar_bitacora(
                    accion="REGISTRAR_PAGO_SP",
                    modulo="Pagos",
                    descripcion=(
                        f"Se registró pago del SP {expediente.no_sp}, boleta {boleta}, "
                        f"período {form.periodo_desde.data.strftime('%d/%m/%Y')} al "
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
                        "registrado_en": momento_local.isoformat(sep=" ", timespec="seconds"),
                    },
                    commit=False,
                )
                db.session.commit()
                flash(
                    f"Pago del SP {expediente.no_sp} registrado correctamente a las {ahora.strftime('%H:%M:%S')}.",
                    "success",
                )
                return redirect(url_for("pagos.sp", expediente_id=expediente.id))

    return render_template(
        "pagos/registrar.html",
        form=form,
        ahora_gt=ahora_guatemala(),
        bancos=_bancos_disponibles(),
        sps=_sp_disponibles(),
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
