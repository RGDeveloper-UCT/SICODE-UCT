"""Checklist BSI v3: revisión CERT/MINGOB 4.1 y 4.2 sin duplicar controles.

La imagen recibida enumera las medidas 1–14 y 16–21 (no tiene 15).
Los controles antiguos de boletas ya creadas permanecen como snapshot.
"""
from app.services.checklist_mantenimiento import validar_checklist, validar_cierre
from app.services.catalogo_informes_mingob_2026 import AVISOS

VERSION = 3
CVE_CERT_PRODUCTO = {
    cve: producto.lower()
    for producto, filas in AVISOS.items()
    for cve, *_ in filas
}
CVE_CERT_19 = tuple(CVE_CERT_PRODUCTO)
TECNOLOGIAS = ("chrome", "java", "python", "php")
NOMBRES_TECNOLOGIA = {
    "chrome": "Google Chrome", "java": "Java/JavaFX",
    "python": "Python/Expat", "php": "PHP",
}

# La hoja CERT rotula 1–14 y después 16–21. Respetamos esos números.
CERT_41 = (
    (1, "Confirmar si Google Chrome está instalado en el equipo."),
    (2, "Registrar la versión de Google Chrome instalada."),
    (3, "Registrar el sistema operativo y su versión."),
    (4, "Identificar y registrar la dependencia responsable del equipo."),
    (5, "Registrar la fecha en que se realiza esta revisión."),
    (6, "Comprobar si Chrome cuenta con la actualización de seguridad aplicable."),
    (7, "Si existe una actualización disponible, ejecutar la actualización del navegador."),
    (8, "Reiniciar Google Chrome para que la actualización quede aplicada."),
    (9, "Verificar la versión desde Menú > Ayuda > Acerca de Google Chrome o chrome://settings/help."),
    (10, "Determinar si el equipo utiliza sistemas sensibles o información de acceso restringido."),
    (11, "Comprobar si el equipo recibe actualizaciones automáticas de Chrome."),
    (12, "Revisar alertas del antivirus/EDR relacionadas con Chrome."),
    (13, "Revisar descargas inusuales, procesos sospechosos o comportamiento anómalo del navegador."),
    (14, "Registrar fecha de actualización, responsable, incidencias y actividades pendientes."),
)
CERT_42 = (
    (16, "Si Chrome no puede actualizarse, reducir temporalmente su uso en equipos de alta exposición."),
    (17, "Evitar el acceso a sitios web no confiables."),
    (18, "Evitar descargas o abrir archivos inesperados."),
    (19, "Verificar que no se habiliten extensiones de Chrome de origen desconocido."),
    (20, "Revisar la conectividad del equipo con los repositorios de actualización."),
    (21, "Coordinar la instalación mediante las herramientas de administración disponibles."),
)
# Estos controles administrativos sí se registran incluso si Chrome está ausente.
CERT_41_AUN_SIN_CHROME = frozenset({1, 3, 4, 5, 14})

GRUPOS = (
    ("sistema", "Seguridad del sistema operativo", (
        "Actualizaciones de seguridad del sistema instaladas",
        "Reinicio del sistema requerido por parches verificado",
        "Programas no autorizados revisados",
    )),
    ("navegador", "Otros navegadores y navegación segura", (
        "Otros navegadores instalados revisados y actualizados",
        "Protección frente a sitios maliciosos y navegación segura verificada",
    )),
    ("java", "Java y JavaFX (si están instalados)", (
        "Identificar si Java/JavaFX está instalado y registrar versión y edición",
        "Contrastar Java SE, Java Plugin, JavaFX o GraalVM con matriz del proveedor",
        "Aplicar parches del proveedor si corresponden y comprobar compatibilidad",
    )),
    ("python", "Python y bibliotecas (si están instaladas)", (
        "Identificar versiones de Python y entornos virtuales instalados",
        "Comprobar corrección de ssl / certificados eMudhra según versión y proveedor",
        "Revisar procesamiento de TAR externos y filtro de seguridad tarfile",
        "Verificar Expat/XML, biblioteca incorporada o parche retroportado del proveedor",
    )),
    ("php", "PHP y servicios web (si corresponden)", (
        "Identificar versión y rama de PHP y servicio web/FPM utilizado",
        "Verificar parches de CVE-2026-109618 y CVE-2026-109619",
        "Comprobar reinicio de PHP-FPM/servidor web y operación posterior",
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
    filas = []
    for grupo, titulo, actividades in GRUPOS:
        if grupo == "navegador":
            for seccion, nombre, controles in (
                ("cert41", "CERT/MINGOB · Acciones prioritarias (numeral 4.1)", CERT_41),
                ("cert42", "CERT/MINGOB · Medidas temporales (numeral 4.2)", CERT_42),
            ):
                for numero, actividad in controles:
                    filas.append({
                        "grupo": seccion, "grupo_nombre": nombre,
                        "codigo": f"{seccion}_{numero}", "numero_cert": numero,
                        "tecnologia": "chrome",
                        "actividad": f"{numero}. {actividad}",
                        "resultado": "PENDIENTE", "observacion": "",
                    })
        for i, actividad in enumerate(actividades):
            filas.append({
                "grupo": grupo, "grupo_nombre": titulo,
                "codigo": f"{grupo}_{i}", "actividad": actividad,
                "tecnologia": grupo if grupo in TECNOLOGIAS else None,
                "resultado": "PENDIENTE", "observacion": "",
            })
    for v in vulnerabilidades:
        tecnologia = CVE_CERT_PRODUCTO.get(v.cve or "") or (
            str(v.producto or "").lower()
            if str(v.producto or "").lower() in TECNOLOGIAS else None
        )
        filas.append({
            "grupo": "vulnerabilidades",
            "grupo_nombre": "CVE seleccionados · verificaciones CERT / otras fuentes",
            "codigo": f"cve_{v.id}",
            "actividad": f"{v.cve or 'AVISO-'+str(v.id)} · {v.titulo}"[:320],
            "resultado": "PENDIENTE", "observacion": "",
            "vulnerabilidad_id": v.id, "severidad": v.severidad,
            "tecnologia": tecnologia,
            "origen_cert": bool((v.cve or "") in CVE_CERT_PRODUCTO),
        })
    return filas


def corresponde_no_aplica(fila, versiones):
    tecnologia = fila.get("tecnologia")
    if tecnologia not in TECNOLOGIAS:
        return False
    if (versiones or {}).get("instalado_" + tecnologia) != "NO":
        return False
    if fila.get("grupo") == "cert41" and fila.get("numero_cert") in CERT_41_AUN_SIN_CHROME:
        return False
    return True


def aplicar_ausencias(datos, base, versiones):
    """Con la tecnología ausente no se exige evaluar sus CVE, pero queda evidencia."""
    por_codigo = {fila["codigo"]: fila for fila in base}
    salida = []
    for fila in datos:
        copiada = dict(fila)
        original = por_codigo.get(copiada.get("codigo")) or {}
        if corresponde_no_aplica(original, versiones):
            tecnologia = original["tecnologia"]
            copiada["resultado"] = "NO_APLICA"
            copiada["observacion"] = (
                f"No instalado: {NOMBRES_TECNOLOGIA[tecnologia]}. "
                "Ausencia verificada y declarada por el técnico."
            )
        salida.append(copiada)
    return salida


def validar_resultados(datos, base):
    return validar_checklist(datos, base)


def validar_finalizacion(checklist, versiones=None):
    validar_cierre(checklist)
    if versiones is None:
        return
    for tecnologia in TECNOLOGIAS:
        estado = versiones.get("instalado_" + tecnologia)
        if estado not in {"SI", "NO"}:
            raise ValueError(
                f"Indique si {NOMBRES_TECNOLOGIA[tecnologia]} está instalado o no."
            )
    for fila in checklist:
        tecnologia = fila.get("tecnologia")
        if not fila.get("codigo", "").startswith("cve_") or tecnologia not in TECNOLOGIAS:
            continue
        if versiones.get("instalado_" + tecnologia) == "SI":
            if not (versiones.get(tecnologia) or "").strip():
                raise ValueError(
                    f"Registre la versión instalada de {NOMBRES_TECNOLOGIA[tecnologia]}."
                )
            if fila["resultado"] == "NO_APLICA" and not fila["observacion"]:
                raise ValueError(
                    f"Justifique por qué {fila['actividad'].split(' · ')[0]} no afecta "
                    "a esta versión instalada."
                )
