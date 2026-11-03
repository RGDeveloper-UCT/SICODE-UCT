"""Inspección de seguridad versionada; CVE vinculados por decisión humana."""
from app.services.checklist_mantenimiento import validar_checklist, validar_cierre

VERSION = 1
GRUPOS = (
    ("sistema", "Sistema operativo y actualizaciones", (
        "Versión del sistema operativo y soporte vigente",
        "Actualizaciones de seguridad instaladas",
        "Reinicio requerido por parches verificado",
        "Programas no autorizados revisados",
    )),
    ("navegador", "Google Chrome y navegadores", (
        "Versión de Google Chrome identificada",
        "Google Chrome actualizado a versión corregida disponible",
        "Otros navegadores y extensiones revisados",
        "Navegación segura y protección contra sitios maliciosos",
    )),
    ("antivirus", "Antivirus y detección", (
        "Antivirus corporativo activo y actualizado",
        "Firmas y motor actualizados",
        "Análisis de amenazas ejecutado",
        "Hallazgos tratados y cuarentena revisada",
    )),
    ("firewall", "Firewall y red", (
        "Firewall del sistema habilitado según política",
        "Perfiles y reglas de firewall institucional verificadas",
        "Servicios expuestos y acceso remoto autorizados",
        "Conectividad institucional segura verificada",
    )),
    ("acceso", "Cuentas y protección de datos", (
        "Usuarios y privilegios autorizados",
        "Bloqueo automático de sesión configurado",
        "Cifrado y respaldos revisados según política",
        "Registro de eventos y controles de seguridad",
    )),
    ("cierre", "Verificación final", (
        "Acciones pendientes y responsable de seguimiento definidos",
        "Equipo operativo y entregado al usuario",
    )),
)


def plantilla(vulnerabilidades=()):
    filas = [
        {"grupo": grupo, "grupo_nombre": titulo, "codigo": f"{grupo}_{i}",
         "actividad": actividad, "resultado": "PENDIENTE", "observacion": ""}
        for grupo, titulo, actividades in GRUPOS for i, actividad in enumerate(actividades)
    ]
    for v in vulnerabilidades:
        filas.append({
            "grupo": "vulnerabilidades", "grupo_nombre": "Vulnerabilidades específicas / boletines CERT",
            "codigo": f"cve_{v.id}", "actividad": f"{v.cve or 'AVISO-'+str(v.id)} · {v.titulo}"[:320],
            "resultado": "PENDIENTE", "observacion": "",
            "vulnerabilidad_id": v.id, "severidad": v.severidad,
        })
    return filas


def validar_resultados(datos, base):
    return validar_checklist(datos, base)


def validar_finalizacion(checklist):
    validar_cierre(checklist)
