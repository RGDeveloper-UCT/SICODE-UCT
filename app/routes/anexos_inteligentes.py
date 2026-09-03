from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.coordinacion_form import _normalizar_referencia
from app.models.coordinacion import AnexoCoordinacion
from app.routes.coordinacion import _crear_base, _sp_opciones
from app.routes.monitoreo_anexos import (
    _actualizar_secuencia_vigente,
    _entero_anexo,
    _estado_anexos,
    _validar_numero,
)
from app.services.bitacora_service import registrar_bitacora
from app.services.catalogo_anexos_service import (
    CATEGORIAS_ANEXOS,
    COMPONENTES_REEMPLAZO,
    catalogo_plano,
    descubrir_tipos_nexo,
)
from app.services.coordinacion_service import resolver_expediente


anexos_inteligentes_bp = Blueprint(
    "anexos_inteligentes",
    __name__,
    url_prefix="/coordinacion/anexos",
)


def _fecha(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def _sugerencias_nexo_seguras():
    try:
        return descubrir_tipos_nexo()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("NEXO no pudo revisar tipos de anexo no catalogados")
        return []


def _titulo_reemplazo(componentes):
    etiquetas = dict(COMPONENTES_REEMPLAZO)
    nombres = [etiquetas[codigo] for codigo in componentes if codigo in etiquetas]
    if not nombres:
        return None
    if len(nombres) == 1:
        detalle = nombres[0]
    elif len(nombres) == 2:
        detalle = " y ".join(nombres)
    else:
        detalle = ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return f"Reemplazo de {detalle}"


def _datos_catalogo_para_vista():
    catalogo = []
    for categoria in CATEGORIAS_ANEXOS:
        item = dict(categoria)
        item["tipos"] = [
            {"codigo": codigo, "titulo": titulo, "modo": modo}
            for codigo, titulo, modo in categoria["tipos"]
        ]
        catalogo.append(item)
    return catalogo


@anexos_inteligentes_bp.get("/nuevo")
@login_required
def nuevo():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    return render_template(
        "coordinacion/anexos_inteligentes.html",
        categorias=_datos_catalogo_para_vista(),
        componentes=COMPONENTES_REEMPLAZO,
        expedientes=_sp_opciones(),
        sugerencias_nexo=_sugerencias_nexo_seguras(),
        url_monitoreo=url_for("coordinacion.registrar", tipo="monitoreo"),
        url_analisis=url_for("coordinacion.registrar", tipo="analisis-riesgo"),
        url_estado_sp=url_for("monitoreo_anexos.estado_sp"),
    )


@anexos_inteligentes_bp.post("/guardar")
@login_required
def guardar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)

    codigo = (request.form.get("tipo_codigo") or "").strip().upper()
    definicion = catalogo_plano().get(codigo)
    if not definicion:
        flash("Seleccione un tipo de anexo válido.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    if definicion["modo"] == "especial":
        destino = "monitoreo" if codigo == "REPORTE_MONITOREO" else "analisis-riesgo"
        return redirect(url_for("coordinacion.registrar", tipo=destino))

    no_sp = (request.form.get("no_sp") or "").strip()
    expediente, _ = resolver_expediente(no_sp)
    if not expediente:
        flash("El SP debe existir y estar activo para registrar el anexo.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    numero = _entero_anexo(request.form.get("numero_anexo"))
    es_vencido = request.form.get("anexo_vencido") == "1"
    if request.form.get("confirmacion_file_server") != "1":
        flash("Debe confirmar el número de anexo contra File Server.", "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    _estado, error = _validar_numero(expediente, numero, es_vencido)
    if error:
        flash(error, "warning")
        return redirect(url_for("anexos_inteligentes.nuevo"))

    titulo = definicion["titulo"]
    componentes = []
    if definicion["modo"] == "componentes":
        permitidos = {codigo for codigo, _etiqueta in COMPONENTES_REEMPLAZO}
        componentes = [
            valor for valor in request.form.getlist("componentes")
            if valor in permitidos
        ]
        titulo = _titulo_reemplazo(componentes)
        if not titulo:
            flash("Seleccione al menos un componente reemplazado.", "warning")
            return redirect(url_for("anexos_inteligentes.nuevo"))
    elif definicion["modo"] == "libre":
        titulo = (request.form.get("titulo_otro") or "").strip()
        if not titulo:
            flash("Escriba el nombre del tipo de anexo.", "warning")
            return redirect(url_for("anexos_inteligentes.nuevo"))
        titulo = titulo[:180]

    tipo_referencia = (request.form.get("tipo_referencia") or "RC").strip().upper()
    rc = _normalizar_referencia(tipo_referencia, request.form.get("rc"))
    providencia = (request.form.get("providencia") or "").strip() or None
    fecha_recepcion = _fecha(request.form.get("fecha_recepcion"))
    observaciones = (request.form.get("observaciones") or "").strip() or None
    folios = (request.form.get("folios") or "").strip() or None

    registro = _crear_base(
        "ANEXO",
        no_sp,
        rc,
        providencia,
        fecha_recepcion,
        observaciones,
        [no_sp, rc, providencia, titulo, fecha_recepcion, numero],
    )

    anexo = AnexoCoordinacion(
        registro_id=registro.id,
        tipo_anexo=definicion["titulo"][:120],
        titulo=titulo[:180],
        folios=folios,
        escaneado=False,
        numero_anexo=str(numero),
        es_vencido=es_vencido,
    )
    db.session.add(anexo)

    total_anterior = _actualizar_secuencia_vigente(expediente, numero, es_vencido)
    registrar_bitacora(
        accion="REGISTRAR_ANEXO_CATALOGO_VENCIDO" if es_vencido else "REGISTRAR_ANEXO_CATALOGO",
        modulo="Coordinación",
        descripcion=(
            f"Se registró {titulo} como Anexo {numero} del SP {expediente.no_sp}. "
            + (
                f"Marcado como histórico; la secuencia vigente permanece en {total_anterior}."
                if es_vencido
                else f"Total de anexos {total_anterior} -> {numero}."
            )
        ),
        usuario_id=current_user.id,
        expediente_id=expediente.id,
        entidad="RegistroCoordinacion",
        entidad_id=registro.id,
        datos_posteriores={
            "tipo": "ANEXO",
            "tipo_catalogo": codigo,
            "categoria": definicion["categoria"],
            "titulo": titulo,
            "componentes": componentes,
            "sp": expediente.no_sp,
            "numero_anexo": numero,
            "es_vencido": es_vencido,
            "anexos_rectificados": expediente.anexos_rectificados,
        },
        commit=False,
    )
    db.session.commit()

    if es_vencido:
        flash(
            f"{titulo} registrado como ANEXO VENCIDO/HISTÓRICO {numero} del SP {expediente.no_sp}.",
            "warning",
        )
    else:
        flash(f"{titulo} registrado correctamente como Anexo {numero}.", "success")
    return redirect(url_for("coordinacion.detalle", registro_id=registro.id))
