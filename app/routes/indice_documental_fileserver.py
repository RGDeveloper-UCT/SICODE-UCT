"""Conciliación multi-SP de metadatos File Server, sin sobrescribir datos existentes."""
import hashlib
import json
from collections import Counter, defaultdict
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app import db
from app.models.documento_expediente import DocumentoExpediente
from app.models.coordinacion import AnexoCoordinacion
from app.models.expediente import Expediente
from app.routes.indice_documental import indice_documental_bp, _exigir_modificacion
from app.services.bitacora_service import registrar_bitacora
from app.services.importacion_indice_fileserver_service import (
    ESTADOS_EXPLICADOS, IndiceFileServerInvalido, leer_excel, planificar, normalizar,
)

def _firma():
    return URLSafeTimedSerializer(current_app.secret_key, salt="sicode-fileserver-v1")

def _resumen_firma(decisiones):
    datos = [(r["fila"],r["sp"],r["estado"],r["expediente_id"],
              r["anexo_coordinacion_id"],r["detalle"]) for r in decisiones]
    return hashlib.sha256(json.dumps(datos,ensure_ascii=False).encode()).hexdigest()

@indice_documental_bp.route("/expedientes/indice-documental/importacion-fileserver", methods=["GET","POST"])
@login_required
def importar_indice_fileserver():
    _exigir_modificacion()
    decisiones, resumen, token = [], {}, None
    if request.method == "POST":
        try:
            accion = request.form.get("accion")
            if accion == "previsualizar":
                archivo = request.files.get("archivo")
                if not archivo or not archivo.filename:
                    raise IndiceFileServerInvalido("Seleccione un Excel .xlsx.")
                filas = leer_excel(archivo)
                decisiones, resumen = planificar(filas)
                token = _firma().dumps({"usuario":current_user.id,"filas":filas,
                                        "huella":_resumen_firma(decisiones)})
            elif accion == "confirmar":
                try:
                    paquete = _firma().loads(request.form.get("token",""), max_age=1800)
                except (BadSignature,SignatureExpired) as error:
                    raise IndiceFileServerInvalido(
                        "Vista previa caducada o alterada. Cargue el Excel de nuevo.") from error
                if paquete.get("usuario") != current_user.id:
                    abort(403)
                filas = paquete["filas"]
                Expediente.query.filter(Expediente.no_sp.in_(
                    sorted({r["sp"] for r in filas})
                )).order_by(Expediente.id).with_for_update().all()
                decisiones,resumen = planificar(filas)
                if _resumen_firma(decisiones) != paquete.get("huella"):
                    raise IndiceFileServerInvalido(
                        "El índice cambió desde la previsualización. No se aplicó ningún cambio.")
                nuevos = [r for r in decisiones if r["estado"] == "NUEVO"]
                grupos_anexo = Counter(
                    (r["expediente_id"], r["numero_anexo"])
                    for r in decisiones if r["seccion"] == "ANEXO"
                )
                importados_por_sp = defaultdict(list)
                for r in nuevos:
                    documento = DocumentoExpediente(
                        expediente_id=r["expediente_id"],nombre_documento=r["nombre_documento"],
                        tipo_documento=r["tipo_documento"],folio_inicio=r["folio_inicial"],
                        folio_fin=r["folio_final"],total_folios=r["folio_final"]-r["folio_inicial"]+1,
                        estado_revision="Pendiente de revisión",
                        es_anexo=r["seccion"]=="ANEXO",indice_numero_anexo=r["numero_anexo"],
                        indice_titulo_anexo=r["titulo_anexo"] or None,indice_orden=r["orden"],
                        observaciones=r["observaciones"] or None,activo=True)
                    db.session.add(documento)
                    db.session.flush()
                    importados_por_sp[r["expediente_id"]].append({
                        "documento_id": documento.id, "fila": r["fila"],
                        "ref_file_server": r["referencia_file_server"],
                    })
                    if r["seccion"] == "ANEXO" and r["anexo_coordinacion_id"]:
                        anexo = db.session.get(AnexoCoordinacion, r["anexo_coordinacion_id"])
                        fuerte = anexo and (
                            (r["titulo_anexo"] and anexo.titulo and
                             normalizar(r["titulo_anexo"]) == normalizar(anexo.titulo))
                            or (r["rc"] and anexo.registro.rc and
                                normalizar(r["rc"]) == normalizar(anexo.registro.rc))
                        )
                        if (anexo and anexo.documento_expediente_id is None
                            and grupos_anexo[(r["expediente_id"], r["numero_anexo"])] == 1
                            and fuerte):
                            anexo.documento_expediente_id = documento.id
                for expediente_id, registros in importados_por_sp.items():
                    registrar_bitacora(
                        accion="IMPORTAR_INDICE_FILESERVER_SP", modulo="Índice documental",
                        descripcion=f"Se agregaron {len(registros)} metadatos de índice; "
                                    "se preservan registros y rectificación física.",
                        usuario_id=current_user.id, expediente_id=expediente_id,
                        entidad="Expediente", entidad_id=expediente_id,
                        datos_posteriores={"origen": "FILE_SERVER_EXCEL",
                                         "nuevos": registros[:200]}, commit=False)
                registrar_bitacora(
                    accion="CONCILIAR_INDICE_FILESERVER_MASIVO",modulo="Índice documental",
                    descripcion=f"Excel File Server: {len(filas)} filas y {len(nuevos)} nuevas.",
                    usuario_id=current_user.id,entidad="DocumentoExpediente",
                    datos_posteriores={"estados":resumen,"huella":paquete["huella"],
                        "sp_involucrados":len({r["sp"] for r in filas}),
                        "registros_nuevos":len(nuevos),"sin_modificar_manuales":True,
                        "sin_rectificacion_automatica":True},commit=False)
                db.session.commit()
                flash(f"Importación terminada: {len(nuevos)} filas nuevas, "
                      "sin sustituir documentos manuales ni rectificaciones.", "success")
                return redirect(url_for("indice_documental.importar_indice_fileserver"))
            else:
                raise IndiceFileServerInvalido("Acción desconocida.")
        except IndiceFileServerInvalido as error:
            db.session.rollback()
            flash(str(error),"danger")
        except Exception:
            db.session.rollback()
            raise
    return render_template("indice_documental/importar_fileserver.html",
        decisiones=decisiones,resumen=resumen,token=token,
        explicaciones=ESTADOS_EXPLICADOS,nuevos=resumen.get("NUEVO",0),
        diferencias=sum(v for k,v in resumen.items() if k not in {"NUEVO","COINCIDE"}))
