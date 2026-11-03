"""Formulario independiente BSI: medidas de los avisos CERT/MINGOB de octubre 2026.

El contenido procede de los apartados 4.1 y 4.2 de los informes de
Chrome, Java/Python y PHP aportados por la unidad; no automatiza parches.
"""
from app.services.checklist_mantenimiento import validar_checklist, validar_cierre

VERSION_MEDIDAS = 1
GRUPOS_MEDIDAS = (
    ("mp_chrome_41", "Google Chrome · 4.1 Acciones prioritarias", "chrome", (
        "Identificar equipos con Chrome instalado y registrar versión, sistema operativo, dependencia responsable y fecha de revisión.",
        "Actualizar Chrome a la versión de seguridad aplicable y reiniciar el navegador para activar el parche.",
        "Comprobar la versión instalada en Menú > Ayuda > Acerca de Google Chrome o chrome://settings/help.",
        "Priorizar puestos con sistemas sensibles, correo institucional y navegación frecuente; revisar equipos sin actualizaciones automáticas.",
        "Supervisar alertas de antivirus/EDR, descargas inusuales, procesos de Chrome y reportes de comportamiento anómalo.",
        "Registrar fecha de actualización, responsable, equipos pendientes e incidencias; comunicar resultados a coordinación de seguridad.",
    )),
    ("mp_chrome_42", "Google Chrome · 4.2 Medidas temporales", "chrome", (
        "Reducir temporalmente el uso de Chrome en equipos con alta exposición cuando no exista versión corregida instalada.",
        "Evitar sitios no confiables, descargas o archivos inesperados y extensiones de origen desconocido.",
        "Revisar conectividad a repositorios de actualización y coordinar instalación mediante herramientas de administración disponibles.",
    )),
    ("mp_java_python_41", "Java y Python · 4.1 Acciones prioritarias", "java_python", (
        "Identificar equipos, servidores y aplicaciones que utilizan Java o Python; registrar versión, sistema operativo, responsable y exposición a Internet.",
        "Consultar las matrices de Oracle y comunicados de Python para confirmar afectación; considerar JavaFX, GraalVM y bibliotecas integradas.",
        "Actualizar los componentes afectados mediante paquetes oficiales o equivalentes del proveedor, con respaldo y pruebas previas.",
        "Validar tras la actualización aplicaciones, autenticación, HTTPS, integraciones, formularios y tareas automatizadas.",
        "Revisar registros y monitoreo para detectar errores inusuales, intentos de acceso, fallos del servicio y actividad inesperada.",
        "Documentar versiones verificadas, parches, responsable y hallazgos; informar a coordinación de seguridad.",
    )),
    ("mp_java_python_42", "Java y Python · 4.2 Medidas temporales", "java_python", (
        "Si se aplaza la actualización, limitar temporalmente los servicios expuestos conforme al análisis del administrador.",
        "Reducir permisos y restringir el uso de código o archivos de origen no confiable mientras se corrige.",
        "Vigilar registros del sistema y servicios expuestos para identificar actividad anómala.",
        "En Python, evitar procesar TAR o XML de origen desconocido sin controles de seguridad.",
        "En Java, identificar los componentes vulnerables realmente utilizados antes de aplicar mitigaciones temporales.",
    )),
    ("mp_php_41", "PHP · 4.1 Acciones prioritarias", "php", (
        "Identificar servidores y aplicaciones PHP; registrar versión, sistema operativo, tipo de despliegue y exposición a Internet.",
        "Aplicar versiones corregidas del 21 de octubre o paquetes equivalentes verificados, previa copia de seguridad y plan de reversión.",
        "En instalaciones Windows, comprobar compilación «-1» cuando corresponda y revisar el uso de cURL/Brotli.",
        "Comprobar portales, inicio de sesión, formularios, carga de documentos y servicios críticos después de actualizar.",
        "Revisar registros del servidor, PHP, WAF y monitoreo por solicitudes anómalas, errores de memoria, reinicios y actividad inusual.",
        "Documentar resultados, fecha de actualización, responsable y hallazgos; comunicar al canal de coordinación de seguridad.",
    )),
    ("mp_php_42", "PHP · 4.2 Medidas temporales", "php", (
        "Si no puede corregirse CVE-2026-109619, evaluar desactivar session.upload_progress.enabled y reiniciar servicios según aviso del proveedor.",
        "Si aplica PHP 8.5 afectado, evaluar desactivar fatal_error_backtraces conforme al aviso oficial.",
        "Para CVE-2026-109618, evaluar límites estrictos a solicitudes HTTP y cargas, y cambios controlados de memory_limit según impacto.",
        "Revisar configuraciones obsoletas, fallos fatales accesibles externamente y reglas firewall/WAF como defensa adicional.",
    )),
)


def plantilla_medidas():
    return [
        {
            "grupo": clave, "grupo_nombre": titulo, "tecnologia": tecnologia,
            "codigo": f"{clave}_{i}", "actividad": actividad,
            "resultado": "PENDIENTE", "observacion": "",
        }
        for clave, titulo, tecnologia, actividades in GRUPOS_MEDIDAS
        for i, actividad in enumerate(actividades)
    ]


def validar_medidas(datos, existente, versiones, finalizar=False):
    """No confundir tecnología ausente con medida corregida o aplicada."""
    validados = validar_checklist(datos, existente)
    for fila in validados:
        tec = fila.get("tecnologia")
        if tec == "java_python":
            ausente = (versiones.get("instalado_java") == "NO"
                       and versiones.get("instalado_python") == "NO")
            sin_verificar = (versiones.get("instalado_java") == "NO_VERIFICADO"
                            or versiones.get("instalado_python") == "NO_VERIFICADO")
        else:
            estado = versiones.get("instalado_" + tec, "NO_VERIFICADO")
            ausente = estado == "NO"
            sin_verificar = estado == "NO_VERIFICADO"
        if ausente:
            fila["resultado"] = "NO_APLICA"
            fila["observacion"] = "Tecnología no instalada, según verificación declarada por el técnico."
        elif finalizar and sin_verificar:
            raise ValueError("Verifique si la tecnología está instalada antes de cerrar: " + fila["grupo_nombre"])
    if finalizar:
        validar_cierre(validados)
    return validados
