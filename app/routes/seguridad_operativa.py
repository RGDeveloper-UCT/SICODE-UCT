"""Catálogo de vulnerabilidades y boletas de Seguridad Informática."""
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_, cast, String
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.seguridad_operativa import BoletaSeguridadTI, VulnerabilidadTI, SincronizacionVulnerabilidadesTI
from app.services.agenda_service import notificar
from app.models.usuario import Usuario
from app.services.bitacora_service import registrar_bitacora
from app.services.checklist_seguridad import VERSION, plantilla, validar_resultados, validar_finalizacion, normalizar_por_instalacion
from app.services.constancia_seguridad_service import generar_boleta_seguridad
from app.services.sincronizacion_vulnerabilidades import CVE_PATTERN
from app.services.catalogo_informes_mingob_2026 import AVISOS

seguridad_operativa_bp = Blueprint("seguridad_operativa", __name__, url_prefix="/seguridad-informatica")
SEVERIDADES = {"CRITICA", "ALTA", "MEDIA", "BAJA", "DESCONOCIDA"}
RESULTADOS = {"OPERATIVO", "CON_HALLAZGOS", "REQUIERE_INTERVENCION"}
TIPOS_EQUIPO = {"COMPUTADORA", "PORTATIL", "SERVIDOR", "TABLETA"}
TAMANO_PDF_MAXIMO = 8 * 1024 * 1024
CERT_19_CVES = tuple(fila[0] for grupo in AVISOS.values() for fila in grupo)


def _escritura():
    if not current_user.puede_modificar:
        abort(403)


def _admin():
    if current_user.rol != Usuario.ROL_ADMINISTRADOR:
        abort(403)


def _auditoria(accion, entidad, id_, descripcion, posteriores=None):
    registrar_bitacora(
        accion, "Seguridad Informática", descripcion,
        usuario_id=current_user.id, entidad=entidad, entidad_id=id_,
        datos_posteriores=posteriores, commit=False,
    )


def _fecha(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ValueError("Fecha inválida (AAAA-MM-DD).")


def _texto(nombre, maximo, obligatorio=False):
    texto = (request.form.get(nombre) or "").strip()
    if len(texto) > maximo or (obligatorio and not texto):
        raise ValueError(f"Campo {nombre} inválido o demasiado largo.")
    return texto


def _snapshot(e):
    return {
        "codigo": e.codigo, "nombre": e.nombre, "tipo": e.tipo,
        "marca": e.marca, "modelo": e.modelo, "serie": e.serie,
        "ip_estatica": e.ip_estatica, "area": e.area, "ubicacion": e.ubicacion,
        "custodio": e.nombre_responsable, "usuario_habitual": e.nombre_usuario_habitual,
    }


def _archivo_carpeta():
    return Path(current_app.instance_path) / "seguridad" / "avisos_cert"


@seguridad_operativa_bp.get("/")
@login_required
def inicio():
    total = VulnerabilidadTI.query.count()
    altas = VulnerabilidadTI.query.filter(
        or_(VulnerabilidadTI.explotada.is_(True), VulnerabilidadTI.severidad.in_(("ALTA", "CRITICA")))
    ).count()
    boletas = BoletaSeguridadTI.query.filter(BoletaSeguridadTI.estado != "ANULADA").count()
    pendientes = BoletaSeguridadTI.query.filter(BoletaSeguridadTI.estado.notin_(("FINALIZADO", "ANULADA"))).count()
    recientes = VulnerabilidadTI.query.order_by(VulnerabilidadTI.creado_en.desc(), VulnerabilidadTI.id.desc()).limit(8).all()
    fuentes = SincronizacionVulnerabilidadesTI.query.order_by(SincronizacionVulnerabilidadesTI.fuente).all()
    return render_template("seguridad_operativa/inicio.html", total=total, altas=altas,
                           boletas=boletas, pendientes=pendientes, recientes=recientes, fuentes=fuentes)


@seguridad_operativa_bp.get("/vulnerabilidades")
@login_required
def vulnerabilidades():
    q = request.args.get("q", "").strip()[:120]
    fuente = request.args.get("fuente", "").strip()[:24]
    consulta = VulnerabilidadTI.query
    if q:
        consulta = consulta.filter(or_(
            VulnerabilidadTI.cve.ilike(f"%{q}%"),
            VulnerabilidadTI.titulo.ilike(f"%{q}%"),
            VulnerabilidadTI.producto.ilike(f"%{q}%"),
            VulnerabilidadTI.fabricante.ilike(f"%{q}%"),
        ))
    if fuente in {"CERT", "MINGOB", "CISA_KEV", "NVD"}:
        consulta = consulta.filter(or_(
            VulnerabilidadTI.fuente == fuente,
            cast(VulnerabilidadTI.fuentes, String).ilike('%"' + fuente + '"%'),
        ))
    page = max(1, request.args.get("page", 1, type=int))
    registros = consulta.order_by(VulnerabilidadTI.explotada.desc(),
                                  VulnerabilidadTI.creado_en.desc(), VulnerabilidadTI.id.desc()).paginate(
                                      page=page, per_page=30, error_out=False)
    return render_template("seguridad_operativa/vulnerabilidades.html", registros=registros, q=q, fuente=fuente)


@seguridad_operativa_bp.route("/vulnerabilidades/nueva", methods=["GET", "POST"])
@login_required
def nueva_vulnerabilidad():
    _escritura()
    if request.method == "POST":
        ruta_archivo = None
        try:
            cve = _texto("cve", 28).upper() or None
            if cve and not CVE_PATTERN.fullmatch(cve):
                raise ValueError("CVE inválido. Use CVE-AAAA-NNNN.")
            if cve and VulnerabilidadTI.query.filter_by(cve=cve).first():
                raise ValueError("Este CVE ya está en el catálogo; no se duplicará.")
            titulo = _texto("titulo", 220, True)
            severidad = _texto("severidad", 16, True)
            if severidad not in SEVERIDADES:
                raise ValueError("Severidad inválida.")
            referencia = _texto("referencia", 500) or None
            if referencia:
                url = urlparse(referencia)
                if url.scheme not in {"https", "http"} or not url.hostname:
                    raise ValueError("La referencia debe ser una dirección web HTTP(S).")
            documento = request.files.get("archivo_pdf")
            archivo = None
            if documento and documento.filename:
                # Nunca aceptar la ruta/nombre enviado por el cliente.
                if not documento.filename.lower().endswith(".pdf"):
                    raise ValueError("Solo se admiten avisos PDF.")
                datos = documento.stream.read(TAMANO_PDF_MAXIMO + 1)
                if len(datos) > TAMANO_PDF_MAXIMO or not datos.startswith(b"%PDF-"):
                    raise ValueError("PDF inválido o mayor a 8 MB.")
                archivo = uuid4().hex + ".pdf"
                carpeta = _archivo_carpeta()
                carpeta.mkdir(parents=True, exist_ok=True)
                ruta_archivo = carpeta / archivo
                ruta_archivo.write_bytes(datos)
            v = VulnerabilidadTI(
                cve=cve, fuente="CERT", fuentes=["CERT"], titulo=titulo, severidad=severidad,
                fabricante=_texto("fabricante", 140) or None,
                producto=_texto("producto", 160) or None,
                descripcion=_texto("descripcion", 4000),
                recomendacion=_texto("recomendacion", 4000),
                referencia=referencia,
                fecha_publicacion=_fecha(request.form.get("fecha_publicacion")),
                fecha_recibido=_fecha(request.form.get("fecha_recibido")),
                explotada=request.form.get("explotada") == "si",
                archivo_pdf=archivo,
            )
            db.session.add(v)
            db.session.flush()
            usuarios = [u.id for u in Usuario.query.filter_by(activo=True).all() if u.puede_modificar]
            notificar(usuarios, None, "Aviso CERT registrado: " + titulo[:110],
                     "Nuevo aviso CERT. Verificar aplicabilidad por equipo: " + (cve or titulo)[:160],
                     prioridad="alta" if v.explotada or severidad == "CRITICA" else "media",
                     obligatoria=False, clave=f"seguridad-ti:cert:{v.id}")
            _auditoria("REGISTRAR_AVISO_CERT", "VulnerabilidadTI", v.id, titulo)
            db.session.commit()
            flash("Aviso CERT registrado correctamente.", "success")
            return redirect(url_for("seguridad_operativa.vulnerabilidades"))
        except (ValueError, TypeError, IntegrityError, OSError) as error:
            db.session.rollback()
            if ruta_archivo:
                ruta_archivo.unlink(missing_ok=True)
            flash(str(error), "warning")
    return render_template("seguridad_operativa/nueva_vulnerabilidad.html")


@seguridad_operativa_bp.get("/vulnerabilidades/<int:id_>/pdf")
@login_required
def aviso_pdf(id_):
    v = db.get_or_404(VulnerabilidadTI, id_)
    if not v.archivo_pdf or not re.fullmatch(r"[0-9a-f]{32}\.pdf", v.archivo_pdf):
        abort(404)
    return send_from_directory(_archivo_carpeta(), v.archivo_pdf,
                               as_attachment=True, mimetype="application/pdf",
                               download_name=f"aviso_cert_{v.id}.pdf")


@seguridad_operativa_bp.get("/boletas")
@login_required
def boletas():
    q = request.args.get("q", "").strip()[:120]
    mostrar_anuladas = request.args.get("anuladas") == "1" and current_user.rol == Usuario.ROL_ADMINISTRADOR
    consulta = BoletaSeguridadTI.query.join(EquipoInstitucional)
    consulta = consulta.filter(BoletaSeguridadTI.estado == "ANULADA" if mostrar_anuladas else
                               BoletaSeguridadTI.estado != "ANULADA")
    if q:
        consulta = consulta.filter(or_(EquipoInstitucional.codigo.ilike(f"%{q}%"),
                                      EquipoInstitucional.nombre.ilike(f"%{q}%")))
    page = max(1, request.args.get("page", 1, type=int))
    registros = consulta.order_by(BoletaSeguridadTI.id.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("seguridad_operativa/boletas.html", registros=registros, q=q, mostrar_anuladas=mostrar_anuladas)


@seguridad_operativa_bp.route("/boletas/nueva", methods=["GET", "POST"])
@login_required
def nueva_boleta():
    _escritura()
    equipos = EquipoInstitucional.query.filter(EquipoInstitucional.tipo.in_(TIPOS_EQUIPO)).order_by(
        EquipoInstitucional.codigo).all()
    # Los 19 CVE del informe CERT se cargan como lote predeterminado,
    # aunque el catálogo mundial ya haya superado sus primeros 200 resultados.
    cert = VulnerabilidadTI.query.filter(VulnerabilidadTI.cve.in_(CERT_19_CVES)).all()
    cert.sort(key=lambda v: CERT_19_CVES.index(v.cve))
    catalogo = VulnerabilidadTI.query.filter(
        ~VulnerabilidadTI.cve.in_(CERT_19_CVES)
    ).order_by(VulnerabilidadTI.explotada.desc(),
               VulnerabilidadTI.creado_en.desc()).limit(100).all()
    if request.method == "POST":
        try:
            equipo = db.session.get(EquipoInstitucional, int(request.form.get("equipo_id", "")))
            if equipo is None or equipo.tipo not in TIPOS_EQUIPO:
                raise ValueError("Seleccione un equipo informático existente del inventario.")
            bruto = request.form.getlist("vulnerabilidad_ids")
            if len(bruto) > 11 or len(set(bruto)) != len(bruto):
                raise ValueError("Seleccione hasta 11 vulnerabilidades adicionales distintas.")
            ids = [int(x) for x in bruto]
            extras = VulnerabilidadTI.query.filter(VulnerabilidadTI.id.in_(ids)).all() if ids else []
            if len(extras) != len(ids):
                raise ValueError("Hay vulnerabilidades inexistentes en la selección.")
            incluir_cert = request.form.get("incluir_cert_19") == "si"
            seleccionadas = list(cert) if incluir_cert else []
            ids_ya = {v.id for v in seleccionadas}
            seleccionadas.extend(v for v in extras if v.id not in ids_ya)
            if len(seleccionadas) > 30:
                raise ValueError("Límite de 30 CVE por boleta.")

            b = BoletaSeguridadTI(
                equipo_id=equipo.id, tecnico_id=current_user.id, estado="BORRADOR",
                checklist_version=VERSION, checklist=plantilla(seleccionadas),
                datos_equipo=_snapshot(equipo),
            )
            db.session.add(b)
            db.session.flush()
            _auditoria("CREAR_BOLETA_SEGURIDAD", "BoletaSeguridadTI", b.id, b.numero)
            db.session.commit()
            return redirect(url_for("seguridad_operativa.editar_boleta", id_=b.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template("seguridad_operativa/nueva_boleta.html", equipos=equipos, catalogo=catalogo, cert=cert)


@seguridad_operativa_bp.get("/boletas/<int:id_>")
@login_required
def detalle_boleta(id_):
    b = db.get_or_404(BoletaSeguridadTI, id_)
    return render_template("seguridad_operativa/detalle_boleta.html", b=b)


@seguridad_operativa_bp.route("/boletas/<int:id_>/editar", methods=["GET", "POST"])
@login_required
def editar_boleta(id_):
    _escritura()
    b = db.get_or_404(BoletaSeguridadTI, id_)
    if b.estado in {"FINALIZADO", "ANULADA"}:
        flash("Esta boleta está cerrada y es de solo lectura.", "warning")
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
            validados = validar_resultados(datos, b.checklist)
            diagnostico = _texto("diagnostico", 4000)
            acciones = _texto("acciones", 8000)
            resultado = _texto("resultado_final", 30) or None
            versiones = {}
            for campo in ("sistema", "chrome", "java", "python", "php", "antivirus"):
                versiones[campo] = _texto("version_" + campo, 100)
            for campo in ("chrome", "java", "python", "php"):
                presente = _texto("instalado_" + campo, 16) or "NO_VERIFICADO"
                if presente not in {"SI", "NO", "NO_VERIFICADO"}:
                    raise ValueError("Estado de instalación inválido para " + campo)
                versiones["instalado_" + campo] = presente

            if resultado and resultado not in RESULTADOS:
                raise ValueError("Resultado final inválido.")
            validados = normalizar_por_instalacion(validados, versiones, finalizar=accion == "finalizar")
            if accion == "finalizar":
                validar_finalizacion(validados)
                if not b.iniciado_en or not resultado:
                    raise ValueError("Para finalizar inicie el reloj y seleccione el resultado final.")
                if b.tramo_iniciado_en:
                    b.cambiar_reloj("pausar")
                b.estado = "FINALIZADO"
                b.cerrado_en = datetime.utcnow()
            b.checklist = validados
            b.diagnostico = diagnostico
            b.acciones = acciones
            b.versiones = versiones
            b.resultado_final = resultado
            b.requiere_seguimiento = request.form.get("requiere_seguimiento") == "si"
            _auditoria("FINALIZAR_BOLETA_SEGURIDAD" if accion == "finalizar" else "GUARDAR_BOLETA_SEGURIDAD",
                       "BoletaSeguridadTI", b.id, b.numero,
                       {"estado": b.estado, "segundos": b.segundos()})
            db.session.commit()
            flash("Boleta finalizada." if accion == "finalizar" else "Avance guardado.", "success")
            return redirect(url_for("seguridad_operativa.detalle_boleta" if accion == "finalizar" else
                                    "seguridad_operativa.editar_boleta", id_=b.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "warning")
    return render_template("seguridad_operativa/editar_boleta.html", b=b, checklist=b.checklist)


@seguridad_operativa_bp.post("/boletas/<int:id_>/reloj")
@login_required
def reloj(id_):
    _escritura()
    b = db.get_or_404(BoletaSeguridadTI, id_)
    if request.form.get("accion") not in {"iniciar", "pausar"}:
        abort(400)
    try:
        b.cambiar_reloj(request.form["accion"])
        _auditoria("RELOJ_BOLETA_SEGURIDAD", "BoletaSeguridadTI", b.id, b.numero)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "warning")
    return redirect(url_for("seguridad_operativa.editar_boleta" if b.estado != "FINALIZADO" else
                            "seguridad_operativa.detalle_boleta", id_=b.id))




@seguridad_operativa_bp.post("/boletas/<int:id_>/eliminar")
@login_required
def eliminar_boleta(id_):
    """Anulación lógica: nunca reutilizar folio ni borrar evidencia de auditoría."""
    _escritura()
    b = db.get_or_404(BoletaSeguridadTI, id_)
    es_admin = current_user.rol == Usuario.ROL_ADMINISTRADOR
    if not es_admin and (b.tecnico_id != current_user.id or b.estado == "FINALIZADO"):
        abort(403)
    if b.estado == "ANULADA":
        flash("Esta boleta ya está anulada.", "warning")
        return redirect(url_for("seguridad_operativa.boletas"))
    motivo = _texto("motivo", 500, True)
    if len(motivo) < 8:
        flash("Indique un motivo de al menos 8 caracteres para eliminar la boleta.", "warning")
        return redirect(url_for("seguridad_operativa.detalle_boleta", id_=id_))
    estado_anterior = b.estado
    if b.tramo_iniciado_en:
        b.cambiar_reloj("pausar")
    b.estado = "ANULADA"
    _auditoria("ANULAR_BOLETA_SEGURIDAD", "BoletaSeguridadTI", b.id,
               f"{b.numero}: {motivo}",
               {"estado_anterior": estado_anterior, "estado": "ANULADA",
                "motivo": motivo, "SICOIN": (b.datos_equipo or {}).get("codigo")})
    db.session.commit()
    flash(f"{b.numero} anulada. No aparecerá en informes ni se reutilizará su número.", "success")
    return redirect(url_for("seguridad_operativa.boletas"))

@seguridad_operativa_bp.get("/boletas/<int:id_>/pdf")
@login_required
def boleta_pdf(id_):
    b = db.get_or_404(BoletaSeguridadTI, id_)
    if b.estado != "FINALIZADO":
        flash("El PDF definitivo requiere una boleta finalizada.", "warning")
        return redirect(url_for("seguridad_operativa.detalle_boleta", id_=id_))
    archivo = generar_boleta_seguridad(b)
    registrar_bitacora("EXPORTAR_BOLETA_SEGURIDAD", "Seguridad Informática",
                       b.numero, usuario_id=current_user.id, entidad="BoletaSeguridadTI", entidad_id=b.id)
    return send_file(archivo, mimetype="application/pdf", as_attachment=True,
                     download_name=f"{b.numero}_seguridad_informatica.pdf")


def _celda_segura(valor):
    texto = str(valor or "")
    return "'" + texto if texto.lstrip().startswith(("=", "+", "-", "@")) else texto


@seguridad_operativa_bp.get("/boletas/informe.xlsx")
@login_required
def informe():
    _escritura()
    wb = Workbook()
    ws = wb.active
    ws.title = "Boletas"
    ws.append(["Número", "SICOIN", "Equipo", "Área", "Técnico", "Estado", "Creado",
               "Inicio", "Cierre", "Duración (s)", "Resultado", "Seguimiento",
               "Cumple", "No cumple", "No aplica", "Pendiente", "CVE verificados", "Diagnóstico", "Acciones",
               "Versión SO", "Versión Chrome", "Versión Java", "Versión Python", "Versión PHP", "Antivirus"])
    ws_h = wb.create_sheet("Hallazgos")
    ws_h.append(["Boleta", "SICOIN", "Grupo", "Control / CVE", "Resultado", "Observación"])
    ws_e = wb.create_sheet("Por equipo")
    ws_e.append(["SICOIN", "Equipo", "Total boletas", "Finalizadas", "Última boleta",
                 "Último resultado", "Con hallazgos"])
    por_equipo = {}
    for b in BoletaSeguridadTI.query.filter(BoletaSeguridadTI.estado != "ANULADA").order_by(BoletaSeguridadTI.id.desc()).yield_per(100):
        datos = b.datos_equipo or {}
        cod = datos.get("codigo") or b.equipo.codigo
        respuestas = [f.get("resultado") for f in b.checklist]
        ws.append([
            b.numero, _celda_segura(cod), _celda_segura(datos.get("nombre")), _celda_segura(datos.get("area")),
            _celda_segura(b.tecnico.nombre), b.estado,
            b.creado_en.isoformat(sep=" ", timespec="minutes") if b.creado_en else "",
            b.iniciado_en.isoformat(sep=" ", timespec="minutes") if b.iniciado_en else "",
            b.cerrado_en.isoformat(sep=" ", timespec="minutes") if b.cerrado_en else "",
            b.segundos(), b.resultado_final or "", "Sí" if b.requiere_seguimiento else "No",
            respuestas.count("CUMPLE"), respuestas.count("NO_CUMPLE"), respuestas.count("NO_APLICA"),
            respuestas.count("PENDIENTE"), ", ".join(f.get("actividad", "").split(" · ", 1)[0] for f in b.checklist if f["codigo"].startswith("cve_")),
            _celda_segura(b.diagnostico), _celda_segura(b.acciones),
            *[_celda_segura((b.versiones or {}).get(f)) for f in ("sistema", "chrome", "java", "python", "php", "antivirus")],
        ])
        for f in b.checklist:
            if f.get("resultado") == "NO_CUMPLE":
                ws_h.append([b.numero, _celda_segura(cod), f.get("grupo_nombre"),
                             _celda_segura(f.get("actividad")), "NO_CUMPLE", _celda_segura(f.get("observacion"))])
        if cod not in por_equipo:
            por_equipo[cod] = [cod, datos.get("nombre"), 0, 0, b.numero, b.resultado_final or "", False]
        r = por_equipo[cod]
        r[2] += 1
        r[3] += int(b.estado == "FINALIZADO")
        r[6] |= "NO_CUMPLE" in respuestas
    for fila in sorted(por_equipo.values()):
        fila[0] = _celda_segura(fila[0])
        fila[1] = _celda_segura(fila[1])
        fila[6] = "Sí" if fila[6] else "No"
        ws_e.append(fila)
    for hoja in wb:
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions
        hoja.row_dimensions[1].height = 28
        for celda in hoja[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="1F2D44")
        for columna in hoja.columns:
            letra = columna[0].column_letter
            hoja.column_dimensions[letra].width = min(52, max(14, max(len(str(c.value or "")) for c in list(columna)[:150]) + 2))
    memoria = BytesIO()
    wb.save(memoria)
    memoria.seek(0)
    registrar_bitacora("EXPORTAR_INFORME_SEGURIDAD", "Seguridad Informática",
                       "Informe masivo XLSX de boletas por equipo", usuario_id=current_user.id)
    return send_file(memoria, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="SICODE_informe_seguridad_informatica.xlsx")
