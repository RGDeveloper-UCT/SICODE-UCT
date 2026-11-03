"""Inspección de seguridad versionada; CVE vinculados por decisión humana."""
from app.services.checklist_mantenimiento import validar_checklist, validar_cierre

VERSION = 3
GRUPOS = (
    ("sistema", "Sistema operativo y actualizaciones", (
        "Versión del sistema operativo y soporte vigente",
        "Actualizaciones de seguridad instaladas",
        "Reinicio requerido por parches verificado",
        "Programas no autorizados revisados",
    )),
    ("navegador", "Google Chrome y navegadores", (
        "Versión instalada y canal de Google Chrome comprobados",
        "Google Chrome actualizado a la versión corregida de su plataforma/canal",
        "Google Chrome reiniciado para activar los parches de seguridad",
        "Otros navegadores y extensiones revisados",
        "Navegación segura y protección contra sitios maliciosos",
    )),
    # Apartados 4.1 y 4.2 del protocolo recibido; no repetir controles
    # generales que ya aparecen en "navegador", "antivirus" o "firewall".
    ("cert_chrome_prioritario", "CERT Chrome · verificaciones prioritarias (4.1)", (
        "Identificar y registrar la dependencia o responsable del equipo (4.1.4)",
        "Registrar fecha de revisión del equipo en la boleta (4.1.5)",
        "Verificar el procedimiento institucional de actualización en sistemas sensibles (4.1.10)",
        "Comprobar que Chrome recibe actualizaciones automáticas (4.1.11)",
        "Revisar alertas de antivirus/EDR relacionadas con Chrome (4.1.12)",
        "Revisar descargas inusuales o procesos sospechosos y reportarlos según procedimiento (4.1.13)",
        "Registrar incidencias, fecha y actividades de corrección pendientes (4.1.14)",
    )),
    ("cert_chrome_temporal", "CERT Chrome · medidas temporales si no se puede actualizar (4.2)", (
        "Reducir temporalmente el uso de Chrome cuando no se pueda actualizar (4.2.16)",
        "Evitar descargas o apertura de archivos inesperados (4.2.18)",
        "Verificar que no se habiliten extensiones de Chrome no oficiales (4.2.19)",
        "Revisar conectividad con repositorios de actualización (4.2.20)",
        "Coordinar instalación del parche mediante herramientas de administración disponibles (4.2.21)",
    )),
    ("java", "Java y JavaFX (si están instalados)", (
        "Identificar si Java/JavaFX está instalado y registrar versión y edición",
        "Contrastar Java SE, Java Plugin, JavaFX o GraalVM con matriz Oracle de octubre 2026",
        "Aplicar parches del proveedor si corresponden y comprobar compatibilidad",
    )),
    ("python", "Python y librerías (si están instaladas)", (
        "Identificar versiones de Python y entornos virtuales instalados",
        "Comprobar corrección de ssl / certificados eMudhra según versión y proveedor",
        "Revisar procesamiento de TAR externos y filtro de seguridad tarfile",
        "Verificar Expat/XML, biblioteca incorporada o parche retroportado del proveedor",
    )),
    ("php", "PHP y servicios web (si corresponden)", (
        "Identificar versión y rama de PHP y servicio web/FPM utilizado",
        "Verificar parches de CVE-2026-109618 y CVE-2026-109619",
        "Comprobar reinicio de PHP-FPM/servidor web y operación de aplicaciones tras actualizar",
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
            "tecnologia": tecnologia_del_cve(v.cve) or "",
        })
    return filas


def validar_resultados(datos, base):
    return validar_checklist(datos, base)


def validar_finalizacion(checklist):
    validar_cierre(checklist)


# El mapa procede exclusivamente de los CVE de los tres informes MINGOB;
# no se infiere la tecnología por palabras arbitrarias del catálogo mundial.
def tecnologia_del_cve(cve):
    from app.services.catalogo_informes_mingob_2026 import AVISOS
    for tecnologia, filas in AVISOS.items():
        if any(fila[0] == cve for fila in filas):
            return tecnologia
    return None


def normalizar_por_instalacion(checklist, versiones, finalizar=False):
    """CVE institucionales: ausencia verificada => No aplica.

    Una tecnología por verificar no puede cerrar CVE asociados. El técnico
    siempre decide el cumplimiento si la tecnología sí está instalada.
    """
    mapeo = {"CHROME": "chrome", "JAVA": "java", "PYTHON": "python", "PHP": "php"}
    salida = []
    for original in checklist:
        fila = dict(original)
        grupo_tecnologia = {"java": "java", "python": "python", "php": "php",
                            "cert_chrome_prioritario": "chrome", "cert_chrome_temporal": "chrome"}
        if fila.get("grupo") in grupo_tecnologia:
            componente = grupo_tecnologia[fila["grupo"]]
            if versiones.get("instalado_" + componente) == "NO":
                fila["resultado"] = "NO_APLICA"
                fila["observacion"] = "Componente no instalado; verificación declarada por el técnico."
        if fila.get("grupo") == "vulnerabilidades":
            cve = fila.get("actividad", "").split(" · ", 1)[0]
            tecnologia = fila.get("tecnologia") or tecnologia_del_cve(cve)
            estado = versiones.get("instalado_" + mapeo[tecnologia], "NO_VERIFICADO") if tecnologia in mapeo else None
            if estado == "NO":
                fila["resultado"] = "NO_APLICA"
                fila["observacion"] = ("Componente no instalado; verificación declarada por el técnico.")
            elif finalizar and estado == "NO_VERIFICADO":
                raise ValueError(f"Antes de finalizar, indique si {tecnologia} está instalado para evaluar {cve}.")
        salida.append(fila)
    return salida
