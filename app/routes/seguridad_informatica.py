"""Primer control de Seguridad Informática: numeral 9, inventario de equipos."""
from io import BytesIO
import ipaddress
from datetime import datetime
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from app.services.constancia_inventario_service import generar_constancia_inventario

from app import db
from app.models.equipo_institucional import EquipoInstitucional
from app.models.usuario import Usuario
from app.models.personal_institucional import PersonalInstitucional
from app.services.catalogo_institucional import COORDINACIONES
from app.services.bitacora_service import registrar_bitacora

seguridad_bp = Blueprint("seguridad", __name__, url_prefix="/coordinacion/seguridad")
TIPOS = ("COMPUTADORA", "PORTATIL", "SERVIDOR", "TABLETA", "MOVIL", "IMPRESORA", "ESCANER", "MULTIFUNCIONAL", "MONITOR", "TECLADO", "MOUSE", "PROYECTOR", "UPS", "SWITCH", "ROUTER", "TELEFONO_IP", "OTRO")
ESTADOS = ("ACTIVO", "EN_REVISION", "FUERA_DE_SERVICIO", "BAJA")
ACCESOS = ("INTERNO", "REMOTO", "AMBOS", "SIN_ACCESO")

def _editar_permitido():
    if not current_user.puede_modificar:
        abort(403)

def _normalizar(valor, maximo):
    dato = (valor or "").strip()
    if len(dato) > maximo:
        raise ValueError("Un campo supera la longitud permitida.")
    return dato or None

def _datos():
    datos = {
        "codigo": _normalizar(request.form.get("codigo"), 60),
        "tipo": _normalizar(request.form.get("tipo"), 40),
        "nombre": _normalizar(request.form.get("nombre"), 120),
        "marca": _normalizar(request.form.get("marca"), 100),
        "modelo": _normalizar(request.form.get("modelo"), 120),
        "serie": _normalizar(request.form.get("serie"), 120),
        "ip_estatica": _normalizar(request.form.get("ip_estatica"), 45),
        "area": _normalizar(request.form.get("area"), 160),
        "ubicacion": _normalizar(request.form.get("ubicacion"), 160),
        "tipo_acceso": _normalizar(request.form.get("tipo_acceso"), 40),
        "estado": _normalizar(request.form.get("estado"), 30),
        "observaciones": _normalizar(request.form.get("observaciones"), 2000),
        "acceso_institucional": request.form.get("acceso_institucional") == "si",
    }
    if not all(datos.get(clave) for clave in ("codigo", "tipo", "nombre")):
        raise ValueError("Código, tipo y nombre son obligatorios.")
    if datos["tipo"] not in TIPOS or datos["estado"] not in ESTADOS or datos["tipo_acceso"] not in ACCESOS:
        raise ValueError("Seleccione opciones válidas para el equipo.")
    if datos["area"] and datos["area"] not in COORDINACIONES:
        raise ValueError("Seleccione una coordinación válida.")
    if datos["ip_estatica"]:
        try:
            ipaddress.ip_address(datos["ip_estatica"])
        except ValueError:
            raise ValueError("La dirección IP estática no es válida.")
    valor = request.form.get("responsable_personal_id", "").strip()
    if valor:
        try:
            usuario_id = int(valor)
        except ValueError:
            raise ValueError("Responsable inválido.")
        personal = db.session.get(PersonalInstitucional, usuario_id)
        if not personal or not personal.activo:
            raise ValueError("El responsable no existe o está inactivo.")
        datos["responsable_personal_id"] = usuario_id
    else:
        datos["responsable_personal_id"] = None
    valor_uso = request.form.get("usuario_habitual_personal_id", "").strip()
    if valor_uso:
        try:
            persona_uso_id = int(valor_uso)
        except ValueError:
            raise ValueError("Usuario habitual inválido.")
        persona_uso = db.session.get(PersonalInstitucional, persona_uso_id)
        if not persona_uso or not persona_uso.activo:
            raise ValueError("Usuario habitual inexistente o inactivo.")
        datos["usuario_habitual_personal_id"] = persona_uso_id
    else:
        datos["usuario_habitual_personal_id"] = None
    return datos


CAMPOS_ADICIONALES = {
    "codigo": 60, "nombre": 120, "marca": 100, "modelo": 120, "serie": 120,
    "ip_estatica": 45, "ubicacion": 160, "observaciones": 2000,
}
MAX_ADICIONALES = 20


def _datos_adicionales(principal):
    """Validación integral antes de guardar; el guardado se hace en una transacción."""
    valores = {k: request.form.getlist("adicional_" + k) for k in
               (*CAMPOS_ADICIONALES, "tipo", "area", "tipo_acceso", "estado", "acceso_institucional")}
    cantidad = len(valores["codigo"])
    if cantidad > MAX_ADICIONALES:
        raise ValueError("Solo se permiten hasta 20 equipos adicionales por registro.")
    if any(len(lista) != cantidad for lista in valores.values()):
        raise ValueError("Datos incompletos en los equipos adicionales.")
    resultado = []
    for i in range(cantidad):
        datos = {campo: _normalizar(valores[campo][i], limite)
                 for campo, limite in CAMPOS_ADICIONALES.items()}
        for campo, maximo in (("tipo", 40), ("area", 160), ("tipo_acceso", 40), ("estado", 30)):
            datos[campo] = _normalizar(valores[campo][i], maximo)
        datos["acceso_institucional"] = valores["acceso_institucional"][i] == "si"
        if not datos["codigo"] or not datos["nombre"]:
            raise ValueError(f"El equipo adicional {i + 1} requiere SICOIN y nombre.")
        if datos["tipo"] not in TIPOS or datos["tipo_acceso"] not in ACCESOS or datos["estado"] not in ESTADOS:
            raise ValueError(f"Opciones incorrectas en equipo adicional {i + 1}.")
        if datos["area"] and datos["area"] not in COORDINACIONES:
            raise ValueError(f"Coordinación incorrecta en equipo adicional {i + 1}.")
        if datos["ip_estatica"]:
            try:
                ipaddress.ip_address(datos["ip_estatica"])
            except ValueError:
                raise ValueError(f"IP incorrecta en equipo adicional {i + 1}.")
        datos["responsable_personal_id"] = principal["responsable_personal_id"]
        datos["usuario_habitual_personal_id"] = principal["usuario_habitual_personal_id"]
        resultado.append(datos)
    codigos = [principal["codigo"]] + [e["codigo"] for e in resultado]
    if len(codigos) != len(set(codigos)):
        raise ValueError("Los códigos SICOIN no pueden repetirse en el registro.")
    series = [e["serie"] for e in [principal, *resultado] if e.get("serie")]
    if len(series) != len(set(series)):
        raise ValueError("Las series no pueden repetirse en el registro.")
    return resultado

def _guardar_auditoria(equipo, accion, anterior=None, motivo=None):
    registrar_bitacora(
        accion=accion, modulo="Seguridad Informática",
        descripcion=f"Inventario de equipos: {equipo.codigo}",
        usuario_id=current_user.id, entidad="EquipoInstitucional",
        entidad_id=equipo.id, datos_anteriores=anterior,
        datos_posteriores=equipo.snapshot(), motivo=motivo, commit=False,
    )

@seguridad_bp.route("/")
@login_required
def inicio():
    consulta = EquipoInstitucional.query.filter(EquipoInstitucional.equipo_principal_id.is_(None))
    q = request.args.get("q", "").strip()[:120]
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(or_(EquipoInstitucional.codigo.ilike(patron),
            EquipoInstitucional.nombre.ilike(patron), EquipoInstitucional.ip_estatica.ilike(patron),
            EquipoInstitucional.serie.ilike(patron)))
    pagina = max(1, request.args.get("page", 1, type=int))
    equipos = consulta.order_by(EquipoInstitucional.codigo).paginate(page=pagina, per_page=25, error_out=False)
    return render_template("seguridad/inicio.html", equipos=equipos, q=q)

@seguridad_bp.route("/equipos/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    _editar_permitido()
    if request.method == "POST":
        try:
            principal = _datos()
            adicionales = _datos_adicionales(principal)
            equipo = EquipoInstitucional(**principal, creado_por_id=current_user.id)
            db.session.add(equipo)
            db.session.flush()
            _guardar_auditoria(equipo, "CREAR_EQUIPO_INSTITUCIONAL")
            for datos in adicionales:
                adicional = EquipoInstitucional(**datos, creado_por_id=current_user.id,
                                                equipo_principal_id=equipo.id)
                db.session.add(adicional)
                db.session.flush()
                _guardar_auditoria(adicional, "CREAR_EQUIPO_INSTITUCIONAL")
            db.session.commit()
            flash(f"Registro guardado con {1 + len(adicionales)} equipo(s) y auditoría.", "success")
            return redirect(url_for("seguridad.inicio"))
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash("No se guardó: revise los datos y los identificadores únicos." if isinstance(error, IntegrityError) else str(error), "warning")
    return render_template("seguridad/formulario.html", equipo=None, personal=_personal(), coordinaciones=COORDINACIONES, tipos=TIPOS, estados=ESTADOS, accesos=ACCESOS)

def _personal():
    return PersonalInstitucional.query.filter_by(activo=True).order_by(PersonalInstitucional.nombre, PersonalInstitucional.apellido).all()

@seguridad_bp.route("/personal/nuevo", methods=["POST"])
@login_required
def agregar_personal():
    _editar_permitido()
    nombre = _normalizar(request.form.get("nombre"), 100)
    apellido = _normalizar(request.form.get("apellido"), 120)
    coordinacion = _normalizar(request.form.get("coordinacion"), 160)
    if request.form.get("destino", "responsable") not in ("responsable", "usuario_habitual"):
        abort(400)
    if not nombre or not apellido or coordinacion not in COORDINACIONES:
        flash("Nombre, apellido y coordinación son obligatorios.", "warning")
        return redirect(url_for("seguridad.nuevo"))
    existente = PersonalInstitucional.query.filter(
        func.lower(PersonalInstitucional.nombre) == nombre.lower(),
        func.lower(PersonalInstitucional.apellido) == apellido.lower(),
        PersonalInstitucional.coordinacion == coordinacion,
    ).first()
    if existente:
        flash("El responsable ya está registrado en esa coordinación.", "warning")
        return redirect(url_for("seguridad.nuevo", **{request.form.get("destino", "responsable"): existente.id}))
    persona = PersonalInstitucional(nombre=nombre, apellido=apellido, coordinacion=coordinacion)
    db.session.add(persona)
    try:
        db.session.flush()
        registrar_bitacora(accion="CREAR_PERSONAL_INSTITUCIONAL", modulo="Seguridad Informática",
            usuario_id=current_user.id, entidad="PersonalInstitucional", entidad_id=persona.id,
            descripcion=f"Alta de personal: {persona.nombre_completo}",
            datos_posteriores={"nombre": persona.nombre, "apellido": persona.apellido, "coordinacion": persona.coordinacion}, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    flash("Responsable agregado a Personal Institucional.", "success")
    return redirect(url_for("seguridad.nuevo", **{request.form.get("destino", "responsable"): persona.id}))

@seguridad_bp.route("/equipos/<int:equipo_id>/editar", methods=["GET", "POST"])
@login_required
def editar(equipo_id):
    _editar_permitido()
    equipo = db.get_or_404(EquipoInstitucional, equipo_id)
    if request.method == "POST":
        motivo = _normalizar(request.form.get("motivo"), 500)
        if not motivo:
            flash("Indique el motivo de la modificación.", "warning")
        else:
            try:
                valores = _datos()
                anterior = equipo.snapshot()
                if any(anterior[k] != v for k, v in valores.items()):
                    for clave, valor in valores.items():
                        setattr(equipo, clave, valor)
                    db.session.flush()
                    _guardar_auditoria(equipo, "EDITAR_EQUIPO_INSTITUCIONAL", anterior, motivo)
                    db.session.commit()
                    flash("Cambios guardados en bitácora.", "success")
                    return redirect(url_for("seguridad.inicio"))
                flash("No hay cambios para guardar.", "warning")
            except (ValueError, IntegrityError) as error:
                db.session.rollback()
                flash("No se guardó: revise los identificadores únicos." if isinstance(error, IntegrityError) else str(error), "warning")
    return render_template("seguridad/formulario.html", equipo=equipo, personal=_personal(), coordinaciones=COORDINACIONES, tipos=TIPOS, estados=ESTADOS, accesos=ACCESOS)

@seguridad_bp.route("/equipos/<int:equipo_id>/constancia.pdf")
@login_required
def constancia(equipo_id):
    equipo = db.get_or_404(EquipoInstitucional, equipo_id)
    principal = equipo.equipo_principal or equipo
    integrantes = [principal, *principal.accesorios]
    buffer = generar_constancia_inventario(principal, integrantes)
    registrar_bitacora("GENERAR_CONSTANCIA_INVENTARIO_EQUIPO", "Seguridad Informática",
        usuario_id=current_user.id, entidad="EquipoInstitucional", entidad_id=principal.id,
        descripcion=f"Constancia conjunta consultada: {principal.numero_registro} ({len(integrantes)} activos)",
        datos_posteriores={"equipos": [e.snapshot() for e in integrantes]})
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"constancia_inventario_{principal.id:06d}.pdf")
