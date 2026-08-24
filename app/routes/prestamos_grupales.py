from datetime import datetime
from io import BytesIO
import re
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from flask import Blueprint, flash, redirect, render_template, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import db
from app.forms.prestamo_grupal_form import PrestamoGrupalForm
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.prestamo_grupal import PrestamoGrupo, PrestamoGrupoDetalle
from app.models.traslado_virtual import TrasladoVirtualExpediente
from app.services.bitacora_service import registrar_bitacora
from app.services.sp_service import normalizar_sp


prestamos_grupales_bp = Blueprint("prestamos_grupales", __name__)
MAX_SP_POR_GRUPO = 404


def generar_numero_control_grupo(sp_desde, sp_hasta, modalidad):
    marca_tiempo = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    prefijo = "PGR-VIR" if modalidad == "VIRTUAL" else "PGR-FIS"
    return f"{prefijo}-{sp_desde:04d}-{sp_hasta:04d}-{marca_tiempo}"


def _normalizar_enlace_virtual(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    if not re.match(r"^https?://", texto, flags=re.IGNORECASE):
        texto = f"https://{texto}"
    analizado = urlparse(texto)
    if analizado.scheme.lower() not in {"http", "https"} or not analizado.netloc:
        return None
    return texto


def _numero_sp_entero(expediente):
    valor = normalizar_sp(expediente.no_sp)
    if valor and valor.isdigit():
        return int(valor)
    return None


def _resolver_rango(sp_desde, sp_hasta):
    mapa = {}
    for expediente in Expediente.query.all():
        numero = _numero_sp_entero(expediente)
        if numero is not None:
            mapa[numero] = expediente

    solicitados = list(range(sp_desde, sp_hasta + 1))
    faltantes = [numero for numero in solicitados if numero not in mapa]
    expedientes = [mapa[numero] for numero in solicitados if numero in mapa]
    return expedientes, faltantes


def _validar_expedientes_para_grupo(expedientes, modalidad):
    bloqueos = []
    prestamos_activos = {}
    if modalidad == "FISICO":
        ids = [expediente.id for expediente in expedientes]
        if ids:
            prestamos_activos = {
                prestamo.expediente_id: prestamo
                for prestamo in PrestamoExpediente.query.filter(
                    PrestamoExpediente.expediente_id.in_(ids),
                    PrestamoExpediente.estado == "En préstamo",
                    PrestamoExpediente.activo.is_(True),
                ).all()
            }

    for expediente in expedientes:
        motivos = []
        if not expediente.activo:
            motivos.append("SP inactivo")
        if not expediente.rectificacion_completa:
            motivos.append("folios/anexos pendientes de rectificación")

        if modalidad == "FISICO":
            if not expediente.expediente_fisico_registrado:
                motivos.append("sin expediente físico registrado")
            if expediente.id in prestamos_activos:
                motivos.append(f"préstamo activo {prestamos_activos[expediente.id].numero_control}")

        if motivos:
            bloqueos.append((expediente, motivos))
    return bloqueos


def _resumen_numeros(numeros, limite=20):
    if len(numeros) <= limite:
        return ", ".join(str(numero) for numero in numeros)
    visibles = ", ".join(str(numero) for numero in numeros[:limite])
    return f"{visibles} y {len(numeros) - limite} más"


def _render_formulario_error(form, mensaje, codigo=400):
    grupos = PrestamoGrupo.query.order_by(PrestamoGrupo.fecha_prestamo.desc(), PrestamoGrupo.id.desc()).limit(100).all()
    flash(mensaje, "danger")
    return render_template("prestamos/grupales.html", grupos=grupos, form=form), codigo


@prestamos_grupales_bp.route("/prestamos/grupales", methods=["GET"])
@login_required
def listado_grupos():
    grupos = PrestamoGrupo.query.order_by(PrestamoGrupo.fecha_prestamo.desc(), PrestamoGrupo.id.desc()).limit(100).all()
    form = PrestamoGrupalForm()
    return render_template("prestamos/grupales.html", grupos=grupos, form=form)


@prestamos_grupales_bp.route("/prestamos/grupales/nuevo", methods=["POST"])
@login_required
def nuevo_grupal():
    form = PrestamoGrupalForm()
    if not form.validate_on_submit():
        return _render_formulario_error(form, "Revise los datos del movimiento grupal.")

    modalidad = form.modalidad.data
    plataforma = None
    enlace_virtual = None
    asunto_virtual = None

    if modalidad == "VIRTUAL":
        plataforma = (form.plataforma.data or "").strip()
        enlace_virtual = _normalizar_enlace_virtual(form.enlace_virtual.data)
        asunto_virtual = (form.asunto_virtual.data or "").strip()
        errores_virtuales = []
        if not plataforma:
            errores_virtuales.append("seleccione la plataforma utilizada")
        if not enlace_virtual:
            errores_virtuales.append("registre un enlace de acceso válido (http o https)")
        if not asunto_virtual:
            errores_virtuales.append("indique el motivo o asunto del traslado virtual")
        if errores_virtuales:
            return _render_formulario_error(
                form,
                "Para un traslado virtual debe " + ", ".join(errores_virtuales) + ".",
            )

    sp_desde = form.sp_desde.data
    sp_hasta = form.sp_hasta.data
    if sp_hasta < sp_desde:
        flash("El SP final no puede ser menor que el SP inicial.", "danger")
        return redirect(url_for("prestamos_grupales.listado_grupos"))

    cantidad = sp_hasta - sp_desde + 1
    if cantidad > MAX_SP_POR_GRUPO:
        flash(f"Un movimiento grupal no puede incluir más de {MAX_SP_POR_GRUPO} SP.", "danger")
        return redirect(url_for("prestamos_grupales.listado_grupos"))

    expedientes, faltantes = _resolver_rango(sp_desde, sp_hasta)
    if faltantes:
        flash(
            "No se creó el movimiento grupal porque faltan SP dentro del rango: "
            f"{_resumen_numeros(faltantes)}.",
            "danger",
        )
        return redirect(url_for("prestamos_grupales.listado_grupos"))

    bloqueos = _validar_expedientes_para_grupo(expedientes, modalidad)
    if bloqueos:
        detalle = "; ".join(
            f"SP {expediente.no_sp}: {', '.join(motivos)}"
            for expediente, motivos in bloqueos[:12]
        )
        if len(bloqueos) > 12:
            detalle += f"; y {len(bloqueos) - 12} SP bloqueados más"
        flash(f"No se creó el movimiento grupal. {detalle}.", "warning")
        return redirect(url_for("prestamos_grupales.listado_grupos"))

    numero_control_grupo = generar_numero_control_grupo(sp_desde, sp_hasta, modalidad)
    try:
        grupo = PrestamoGrupo(
            numero_control=numero_control_grupo,
            sp_desde=sp_desde,
            sp_hasta=sp_hasta,
            modalidad=modalidad,
            solicitante=form.solicitante.data.strip(),
            persona_entrega=form.persona_entrega.data.strip(),
            persona_recibe=form.persona_recibe.data.strip(),
            fecha_estimada_devolucion=(
                form.fecha_estimada_devolucion.data if modalidad == "FISICO" else None
            ),
            plataforma=plataforma,
            enlace_virtual=enlace_virtual,
            asunto_virtual=asunto_virtual,
            observaciones=form.observaciones.data,
            creado_por_id=current_user.id,
        )
        db.session.add(grupo)
        db.session.flush()

        for orden, expediente in enumerate(expedientes, start=1):
            sp_limpio = re.sub(r"[^A-Za-z0-9_-]", "-", expediente.no_sp)
            control_individual = f"{numero_control_grupo}-SP-{sp_limpio}"

            if modalidad == "FISICO":
                prestamo = PrestamoExpediente(
                    expediente_id=expediente.id,
                    numero_control=control_individual,
                    solicitante=grupo.solicitante,
                    persona_entrega=grupo.persona_entrega,
                    persona_recibe=grupo.persona_recibe,
                    fecha_prestamo=grupo.fecha_prestamo,
                    fecha_estimada_devolucion=grupo.fecha_estimada_devolucion,
                    estado="En préstamo",
                    observaciones=grupo.observaciones,
                    activo=True,
                )
                db.session.add(prestamo)
                db.session.flush()

                detalle = PrestamoGrupoDetalle(
                    prestamo_grupo_id=grupo.id,
                    prestamo_id=prestamo.id,
                    traslado_virtual_id=None,
                    expediente_id=expediente.id,
                    orden=orden,
                )
                db.session.add(detalle)
                registrar_bitacora(
                    accion="REGISTRAR_PRESTAMO_GRUPAL_SP",
                    modulo="Préstamos",
                    descripcion=(
                        f"El SP {expediente.no_sp} fue asociado al préstamo físico grupal "
                        f"{grupo.numero_control}. Control individual: {prestamo.numero_control}."
                    ),
                    usuario_id=current_user.id,
                    expediente_id=expediente.id,
                    entidad="PrestamoExpediente",
                    entidad_id=prestamo.id,
                    datos_posteriores={
                        "movimiento_grupal": grupo.numero_control,
                        "modalidad": grupo.modalidad,
                        "control_individual": prestamo.numero_control,
                        "sp_desde": grupo.sp_desde,
                        "sp_hasta": grupo.sp_hasta,
                    },
                    commit=False,
                )
            else:
                traslado = TrasladoVirtualExpediente(
                    expediente_id=expediente.id,
                    usuario_id=current_user.id,
                    numero_constancia=control_individual,
                    destinatario=grupo.persona_recibe,
                    dependencia_destino=None,
                    plataforma=grupo.plataforma,
                    enlace_corto=grupo.enlace_virtual,
                    asunto=grupo.asunto_virtual,
                    observaciones=grupo.observaciones,
                    creado_en=grupo.fecha_prestamo,
                )
                db.session.add(traslado)
                db.session.flush()

                detalle = PrestamoGrupoDetalle(
                    prestamo_grupo_id=grupo.id,
                    prestamo_id=None,
                    traslado_virtual_id=traslado.id,
                    expediente_id=expediente.id,
                    orden=orden,
                )
                db.session.add(detalle)
                registrar_bitacora(
                    accion="REGISTRAR_TRASLADO_VIRTUAL_GRUPAL_SP",
                    modulo="Préstamos",
                    descripcion=(
                        f"El SP {expediente.no_sp} fue asociado al traslado virtual grupal "
                        f"{grupo.numero_control} mediante {grupo.plataforma}. "
                        f"Constancia individual: {traslado.numero_constancia}."
                    ),
                    usuario_id=current_user.id,
                    expediente_id=expediente.id,
                    entidad="TrasladoVirtualExpediente",
                    entidad_id=traslado.id,
                    datos_posteriores={
                        "movimiento_grupal": grupo.numero_control,
                        "modalidad": grupo.modalidad,
                        "plataforma": grupo.plataforma,
                        "enlace_virtual": grupo.enlace_virtual,
                        "control_individual": traslado.numero_constancia,
                        "sp_desde": grupo.sp_desde,
                        "sp_hasta": grupo.sp_hasta,
                    },
                    commit=False,
                )

        registrar_bitacora(
            accion="REGISTRAR_MOVIMIENTO_GRUPAL_RANGO",
            modulo="Préstamos",
            descripcion=(
                f"Se registró el movimiento grupal {grupo.numero_control} de modalidad {grupo.modalidad} "
                f"para el rango SP {sp_desde} al {sp_hasta}, con {len(expedientes)} expedientes."
            ),
            usuario_id=current_user.id,
            entidad="PrestamoGrupo",
            entidad_id=grupo.id,
            datos_posteriores={
                "numero_control": grupo.numero_control,
                "modalidad": grupo.modalidad,
                "plataforma": grupo.plataforma,
                "enlace_virtual": grupo.enlace_virtual,
                "sp_desde": grupo.sp_desde,
                "sp_hasta": grupo.sp_hasta,
                "total_expedientes": len(expedientes),
            },
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    descripcion_modalidad = "traslado virtual" if modalidad == "VIRTUAL" else "préstamo físico"
    flash(
        f"Movimiento grupal {numero_control_grupo} creado correctamente como {descripcion_modalidad} con {len(expedientes)} SP.",
        "success",
    )
    return redirect(url_for("prestamos_grupales.constancia_grupal_pdf", grupo_id=grupo.id))


@prestamos_grupales_bp.route("/prestamos/grupales/<int:grupo_id>/constancia/pdf")
@login_required
def constancia_grupal_pdf(grupo_id):
    grupo = PrestamoGrupo.query.get_or_404(grupo_id)
    detalles = sorted(grupo.detalles, key=lambda detalle: detalle.orden)

    def valor_pdf(valor):
        if valor is None or valor == "":
            return "Sin dato"
        return escape(str(valor))

    archivo_pdf = BytesIO()
    doc = SimpleDocTemplate(
        archivo_pdf,
        pagesize=letter,
        rightMargin=30,
        leftMargin=30,
        topMargin=32,
        bottomMargin=32,
    )
    estilos = getSampleStyleSheet()
    normal_pequeno = estilos["Normal"]
    normal_pequeno.fontSize = 7.5
    normal_pequeno.leading = 9

    if grupo.es_virtual:
        titulo = "CONSTANCIA GRUPAL DE TRASLADO VIRTUAL DE EXPEDIENTES"
        introduccion = (
            "Documento administrativo de control del traslado virtual de expedientes. Cada SP listado "
            "queda registrado como traslado virtual individual dentro de SICODE-UCT y asociado a este control grupal. "
            "Este movimiento no modifica la disponibilidad del expediente físico."
        )
    else:
        titulo = "CONSTANCIA GRUPAL DE PRÉSTAMO FÍSICO DE EXPEDIENTES"
        introduccion = (
            "Documento administrativo de control de movimiento físico. Cada expediente listado "
            "queda registrado además como préstamo individual dentro de SICODE-UCT y asociado a este control grupal."
        )

    elementos = [
        Paragraph("SICODE-UCT", estilos["Title"]),
        Paragraph(titulo, estilos["Heading2"]),
        Spacer(1, 8),
        Paragraph(introduccion, estilos["Normal"]),
        Spacer(1, 12),
    ]

    datos_control = [
        ["Control grupal", valor_pdf(grupo.numero_control)],
        ["Modalidad", "Virtual" if grupo.es_virtual else "Físico"],
        ["Rango", f"SP {grupo.sp_desde} al SP {grupo.sp_hasta}"],
        ["Total de expedientes", str(len(detalles))],
        ["Fecha y hora", grupo.fecha_prestamo.strftime("%d/%m/%Y %H:%M") if grupo.fecha_prestamo else "Sin dato"],
        ["Solicitante / responsable", valor_pdf(grupo.solicitante)],
        ["Persona que entrega / comparte", valor_pdf(grupo.persona_entrega)],
        ["Persona que recibe / destinataria", valor_pdf(grupo.persona_recibe)],
    ]
    if grupo.es_virtual:
        datos_control.extend([
            ["Plataforma utilizada", valor_pdf(grupo.plataforma)],
            ["Enlace de acceso", Paragraph(valor_pdf(grupo.enlace_virtual), estilos["BodyText"])],
            ["Motivo / asunto", valor_pdf(grupo.asunto_virtual)],
        ])
    else:
        datos_control.append([
            "Devolución estimada",
            grupo.fecha_estimada_devolucion.strftime("%d/%m/%Y") if grupo.fecha_estimada_devolucion else "Sin dato",
        ])
    datos_control.append(["Registrado por", valor_pdf(grupo.creado_por.nombre if grupo.creado_por else None)])

    tabla_control = Table(datos_control, colWidths=[1.9 * inch, 5.1 * inch])
    tabla_control.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8edf5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.extend([tabla_control, Spacer(1, 14), Paragraph("Expedientes incluidos", estilos["Heading3"])])

    filas = [["#", "SP", "Código SICODE", "Nombre", "Folios", "Anexos", "Control individual", "Estado"]]
    for detalle in detalles:
        expediente = detalle.expediente
        filas.append([
            str(detalle.orden),
            valor_pdf(expediente.no_sp),
            Paragraph(valor_pdf(expediente.codigo_interno), normal_pequeno),
            Paragraph(valor_pdf(expediente.nombre_referencia), normal_pequeno),
            valor_pdf(expediente.folios_rectificados),
            valor_pdf(expediente.anexos_rectificados),
            Paragraph(valor_pdf(detalle.control_individual), normal_pequeno),
            valor_pdf(detalle.estado_movimiento),
        ])

    tabla_expedientes = Table(
        filas,
        repeatRows=1,
        colWidths=[0.25 * inch, 0.4 * inch, 0.85 * inch, 1.3 * inch, 0.45 * inch, 0.45 * inch, 2.35 * inch, 0.75 * inch],
    )
    tabla_expedientes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17233c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (4, 1), (5, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([
        tabla_expedientes,
        Spacer(1, 14),
        Paragraph("Observaciones generales", estilos["Heading3"]),
        Paragraph(valor_pdf(grupo.observaciones), estilos["Normal"]),
        Spacer(1, 22),
    ])

    if grupo.es_fisico:
        firmas = [
            ["Persona que entrega", "Persona que recibe"],
            ["", ""],
            ["____________________________", "____________________________"],
            [valor_pdf(grupo.persona_entrega), valor_pdf(grupo.persona_recibe)],
        ]
        tabla_firmas = Table(firmas, colWidths=[3.5 * inch, 3.5 * inch])
        tabla_firmas.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TOPPADDING", (0, 1), (-1, 1), 24),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        elementos.extend([
            Paragraph("Control de firmas", estilos["Heading3"]),
            tabla_firmas,
            Spacer(1, 12),
            Paragraph(
                "La devolución se controla individualmente por cada SP en SICODE-UCT, conservando la asociación histórica con esta constancia grupal.",
                estilos["Italic"],
            ),
        ])
    else:
        elementos.append(Paragraph(
            "Constancia administrativa de traslado virtual sin firma. SICODE-UCT registra la plataforma y el enlace como metadatos de control; "
            "el sistema no almacena una copia completa del expediente compartido.",
            estilos["Italic"],
        ))

    doc.build(elementos)
    archivo_pdf.seek(0)

    registrar_bitacora(
        accion="EXPORTAR_CONSTANCIA_GRUPAL_RANGO_PDF",
        modulo="Préstamos",
        descripcion=(
            f"Se generó la constancia PDF del movimiento grupal {grupo.numero_control} "
            f"de modalidad {grupo.modalidad}, con {len(detalles)} expedientes."
        ),
        usuario_id=current_user.id,
        entidad="PrestamoGrupo",
        entidad_id=grupo.id,
    )

    tipo_archivo = "traslado_virtual_grupal" if grupo.es_virtual else "prestamo_fisico_grupal"
    nombre_archivo = f"constancia_{tipo_archivo}_{grupo.numero_control}.pdf".replace(" ", "_").replace("/", "-")
    return send_file(
        archivo_pdf,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )
