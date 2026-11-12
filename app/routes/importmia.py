"""ImportM.IA v4: alta supervisada sin documentos binarios."""
import hashlib
import json
from collections import Counter
from datetime import date

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app import db
from app.models.coordinacion import (
    AnexoCoordinacion, AnalisisRiesgo, PagoCoordinacion, RegistroCoordinacion,
    ReporteMonitoreo,
)
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.services.bitacora_service import registrar_bitacora
from app.services.catalogo_anexos_service import catalogo_plano
from app.services.importmia_simple_service import (
    conciliar, ImportMIAInvalido, fecha, importe, referencia, texto,
)
from app.services.importacion_indice_fileserver_service import normalizar
from app.routes.monitoreo_anexos import _validar_numero, _actualizar_secuencia_vigente

importmia_bp = Blueprint("importmia", __name__, url_prefix="/importmia")
MAX_BYTES = 8 * 1024 * 1024


def _firmador():
    return URLSafeTimedSerializer(current_app.secret_key, salt="importmia-simple-v4")


def _huella(resultado):
    filas = []
    for hoja, grupo in resultado["grupos"].items():
        for r in grupo:
            filas.append([hoja, str(r["fila"]), r["sp"], r["estado"], r["detalle"]])
    return hashlib.sha256(json.dumps(filas, ensure_ascii=False).encode("utf-8")).hexdigest()


def _archivo():
    entrada = request.files.get("archivo")
    if not entrada or not (entrada.filename or "").lower().endswith(".xlsx"):
        raise ImportMIAInvalido("Seleccione un Excel .xlsx preparado para ImportM.IA v4.")
    contenido = entrada.stream.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise ImportMIAInvalido("El Excel supera los 8 MB permitidos.")
    return contenido


def _redirigir():
    return redirect(url_for("importmia.inicio"))


@importmia_bp.route("/", methods=["GET", "POST"])
@login_required
def inicio():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    resultado = None
    token = None
    if request.method == "POST":
        if request.form.get("accion") != "previsualizar":
            abort(400)
        try:
            datos = _archivo()
            resultado = conciliar(datos)
            token = _firmador().dumps({
                "usuario": current_user.id,
                "archivo": hashlib.sha256(datos).hexdigest(),
                "huella": _huella(resultado),
            })
        except ImportMIAInvalido as error:
            flash(str(error), "danger")
    return render_template("importmia/inicio.html", resultado=resultado, token=token)


@importmia_bp.post("/confirmar")
@login_required
def confirmar():
    if not getattr(current_user, "puede_modificar", False):
        abort(403)
    try:
        token = _firmador().loads(request.form.get("token", ""), max_age=1800)
        datos = _archivo()
        if token["usuario"] != current_user.id or token["archivo"] != hashlib.sha256(datos).hexdigest():
            raise ImportMIAInvalido("El archivo o usuario no coincide con la previsualización.")
        resultado = conciliar(datos)
        if _huella(resultado) != token["huella"]:
            raise ImportMIAInvalido("SICODE cambió; vuelva a previsualizar.")

        # Bloqueo y nueva consulta para impedir duplicados entre confirmaciones.
        sps = sorted({r["sp"] for grupo in resultado["grupos"].values()
                      for r in grupo if r["sp"]})
        Expediente.query.with_entities(Expediente.id).filter(
            Expediente.no_sp.in_(sps)
        ).order_by(Expediente.id).with_for_update(of=Expediente).all()
        resultado = conciliar(datos)
        if _huella(resultado) != token["huella"]:
            raise ImportMIAInvalido("Los datos cambiaron durante la confirmación.")

        nuevos_indice = [x for x in resultado["grupos"]["Indice"] if x["estado"] == "NUEVO"]
        nuevos_anexos = [x for x in resultado["grupos"]["ANEXOS"] if x["estado"] == "NUEVO"]
        nuevos_pagos = [x for x in resultado["grupos"]["PAGOS"] if x["estado"] == "NUEVO"]

        # Los pagos no modifican solvencia directamente: pagos_service la deriva.
        for d in nuevos_pagos:
            r = d["original"]
            exp = Expediente.query.filter_by(no_sp=d["sp"], activo=True).first()
            reg = RegistroCoordinacion(
                tipo="PAGO", expediente_id=exp.id, no_sp_referencia=exp.no_sp,
                rc=referencia(r), providencia=texto(r.get("providencia"), 120),
                fecha_recepcion=fecha(r.get("fecha_recepcion")),
                usuario_id=current_user.id, usuario_origen=current_user.nombre,
                estado="Completo", origen_registro="MASIVO",
                archivo_origen="ImportMIA-v4", lote_importacion=token["archivo"][:64],
                hoja_origen="PAGOS", fila_origen=d["fila"],
                observaciones=texto(r.get("observaciones"), 1000) or None,
            )
            db.session.add(reg)
            db.session.flush()
            db.session.add(PagoCoordinacion(
                registro_id=reg.id, banco=texto(r.get("banco"), 120),
                boleta=texto(r.get("boleta"), 120), total=importe(r.get("monto")),
                periodo_desde=fecha(r.get("periodo_desde")),
                periodo_hasta=fecha(r.get("periodo_hasta")),
            ))

        # Anexos: conservar número físico y aplicar las reglas de secuencia.
        catalogo = catalogo_plano()
        for d in sorted(nuevos_anexos, key=lambda x: (x["sp"], x["numero"])):
            r = d["original"]
            exp = Expediente.query.filter_by(no_sp=d["sp"], activo=True).first()
            vencido = texto(r.get("es_vencido"), 20).upper() == "SI"
            _, error = _validar_numero(exp, d["numero"], vencido)
            if error:
                raise ImportMIAInvalido(f"SP {d['sp']} Anexo {d['numero']}: {error}")
            codigo = texto(r.get("tipo_codigo"), 100).upper()
            tipo = "ANALISIS_RIESGO" if codigo == "ANALISIS_RIESGO" else (
                "MONITOREO" if codigo == "REPORTE_MONITOREO" else "ANEXO"
            )
            reg = RegistroCoordinacion(
                tipo=tipo, expediente_id=exp.id, no_sp_referencia=exp.no_sp,
                rc=referencia(r), providencia=texto(r.get("providencia"), 120) or None,
                fecha_recepcion=fecha(r.get("fecha_recepcion")),
                persona_entrega=texto(r.get("persona_entrega"), 180) or None,
                folios_recepcion=texto(r.get("folios_recibidos"), 80) or None,
                usuario_id=current_user.id, usuario_origen=current_user.nombre,
                estado="Completo", origen_registro="MASIVO",
                archivo_origen="ImportMIA-v4", lote_importacion=token["archivo"][:64],
                hoja_origen="ANEXOS", fila_origen=d["fila"],
                observaciones=texto(r.get("observaciones"), 1000) or None,
            )
            db.session.add(reg)
            db.session.flush()
            titulo = texto(r.get("titulo"), 180) or catalogo[codigo]["titulo"]
            db.session.add(AnexoCoordinacion(
                registro_id=reg.id, numero_anexo=str(d["numero"]),
                tipo_anexo=catalogo[codigo]["titulo"][:120],
                titulo=titulo[:180], es_vencido=vencido,
                folios=texto(r.get("folios_recibidos"), 80) or None,
                escaneado=False,
            ))
            if codigo == "ANALISIS_RIESGO":
                db.session.add(AnalisisRiesgo(
                    registro_id=reg.id, correlativo=texto(r.get("correlativo_analisis"), 120),
                    tipo_evento=texto(r.get("tipo_evento"), 180) or None,
                ))
            elif codigo == "REPORTE_MONITOREO":
                db.session.add(ReporteMonitoreo(
                    registro_id=reg.id,
                    numero_reporte=texto(r.get("numero_reporte"), 120) or None,
                    tipo_evento=texto(r.get("tipo_evento"), 180) or None,
                ))
            _actualizar_secuencia_vigente(exp, d["numero"], vencido)
            db.session.flush()

        # Índice: solo NUEVO con folios acreditados; ni Verificado ni
        # rectificaciones manuales se sustituyen.
        numeros = Counter((d["original"]["expediente_id"], d["original"]["numero_anexo"])
                          for d in resultado["grupos"]["Indice"]
                          if d["original"]["seccion"] == "ANEXO")
        for d in nuevos_indice:
            r = d["original"]
            doc = DocumentoExpediente(
                expediente_id=r["expediente_id"],
                nombre_documento=r["nombre_documento"],
                tipo_documento=r["tipo_documento"],
                folio_inicio=r["folio_inicial"], folio_fin=r["folio_final"],
                total_folios=r["folio_final"] - r["folio_inicial"] + 1,
                estado_revision="Pendiente de revisión",
                es_anexo=r["seccion"] == "ANEXO",
                indice_numero_anexo=r["numero_anexo"],
                indice_titulo_anexo=r["titulo_anexo"] or None,
                indice_orden=r["orden"], observaciones=r["observaciones"] or None,
                activo=True,
            )
            db.session.add(doc)
            db.session.flush()
            if r["seccion"] == "ANEXO" and r.get("anexo_coordinacion_id"):
                a = db.session.get(AnexoCoordinacion, r["anexo_coordinacion_id"])
                fuerte = a and (
                    (r["titulo_anexo"] and a.titulo and
                     normalizar(r["titulo_anexo"]) == normalizar(a.titulo)) or
                    (r["rc"] and a.registro.rc and normalizar(r["rc"]) == normalizar(a.registro.rc))
                )
                if (fuerte and a.documento_expediente_id is None and
                        numeros[(r["expediente_id"], r["numero_anexo"])] == 1):
                    a.documento_expediente_id = doc.id
            elif r["seccion"] == "ANEXO" and not r.get("anexo_coordinacion_id"):
                # Un anexo creado en este mismo lote puede vincularse si
                # es el único número del SP y tiene título/RC concordante.
                candidatos = (AnexoCoordinacion.query.join(RegistroCoordinacion)
                    .filter(RegistroCoordinacion.expediente_id == r["expediente_id"],
                            AnexoCoordinacion.numero_anexo == str(r["numero_anexo"]),
                            AnexoCoordinacion.documento_expediente_id.is_(None)).all())
                if len(candidatos) == 1 and numeros[(r["expediente_id"], r["numero_anexo"])] == 1:
                    a = candidatos[0]
                    fuerte = ((r["titulo_anexo"] and a.titulo and
                               normalizar(r["titulo_anexo"]) == normalizar(a.titulo))
                              or (r["rc"] and a.registro.rc and
                                  normalizar(r["rc"]) == normalizar(a.registro.rc)))
                    if fuerte:
                        a.documento_expediente_id = doc.id

        registrar_bitacora(
            accion="IMPORTMIA_V4_CONFIRMAR", modulo="ImportM.IA",
            descripcion=(f"Importados: índice {len(nuevos_indice)}, anexos "
                         f"{len(nuevos_anexos)}, pagos {len(nuevos_pagos)}."),
            usuario_id=current_user.id, entidad="ImportMIA",
            datos_posteriores={
                "excel_sha256": token["archivo"],
                "indice": len(nuevos_indice), "anexos": len(nuevos_anexos),
                "pagos": len(nuevos_pagos), "expediente_fisico_modificado": False,
            }, commit=False,
        )
        db.session.commit()
        flash("Importación confirmada. Revisa pagos, anexos e índice en cada SP.", "success")
    except (ImportMIAInvalido, BadSignature, SignatureExpired, KeyError) as error:
        db.session.rollback()
        flash(f"Importación cancelada: {error}", "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Fallo al importar ImportM.IA v4")
        flash("Importación cancelada por error interno. No se guardó el lote.", "danger")
    return _redirigir()


@importmia_bp.post("/confirmar-indice")
@login_required
def confirmar_indice():
    # Evita que clientes anteriores utilicen el contrato v3 por accidente.
    abort(410)
