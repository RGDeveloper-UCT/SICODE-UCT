"""Checklist institucional versionado. Solo resultados técnicos, nunca respaldos ni credenciales."""
VERSION = 2
GRUPOS = (
    ("respaldo", "Respaldo de información", (
        "Escritorio", "Documentos", "Descargas institucionales", "Carpetas de trabajo",
        "Bases de datos y archivos locales", "Favoritos y configuraciones",
        "Otros archivos identificados", "Verificación de archivos respaldados",
        "Confirmación de respaldo en repositorio autorizado",
    )),
    ("hardware", "Mantenimiento de hardware", (
        "Limpieza externa e interna", "Revisión del disco y almacenamiento",
        "Revisión de memoria RAM", "Verificación de temperatura y rendimiento",
        "Revisión de puertos, cables y periféricos", "Comprobación de pantalla, teclado y mouse",
        "Revisión de impresora o escáner", "Revisión de aparato telefónico (si aplica)",
    )),
    ("software", "Mantenimiento de software", (
        "Actualización del sistema operativo", "Software autorizado instalado/actualizado",
        "Revisión de controladores", "Análisis antivirus o antimalware",
        "Optimización de rendimiento", "Revisión de espacio en disco",
        "Configuración de impresoras o escáneres", "Verificación de línea telefónica (si aplica)",
        "Verificación del funcionamiento del antivirus",
    )),
    ("seguridad", "Controles de seguridad informática", (
        "Extensiones de navegador permitidas", "Programas instalados permitidos",
        "Detección de programas no autorizados", "Navegación segura activada",
        "Protección frente a sitios maliciosos", "Actualizaciones de seguridad",
        "Configuración de seguridad institucional",
        "Verificación de los controles del Firewall de Windows",
    )),
    ("final", "Verificación final", (
        "Encendido y funcionamiento general", "Acceso a la red e internet",
        "Aplicaciones institucionales funcionando", "Acceso a impresoras o escáneres",
        "Pantalla, teclado, mouse y periféricos", "Entrega del equipo al usuario",
        "Registro y cierre de la intervención",
    )),
)
RESULTADOS = {"CUMPLE", "NO_CUMPLE", "NO_APLICA", "PENDIENTE"}

def plantilla():
    return [
        {"grupo": clave, "grupo_nombre": nombre, "codigo": f"{clave}_{i}",
         "actividad": actividad, "resultado": "PENDIENTE", "observacion": ""}
        for clave, nombre, items in GRUPOS for i, actividad in enumerate(items)
    ]

def validar_checklist(datos, plantilla_actual=None):
    """Nunca aceptar códigos/etiquetas arbitrarios procedentes del navegador."""
    base = plantilla_actual or plantilla()
    esperado = {fila["codigo"]: fila for fila in base}
    if not isinstance(datos, list) or len(datos) != len(esperado):
        raise ValueError("Checklist incompleto.")
    vistos = set()
    resultado = []
    for fila in datos:
        if not isinstance(fila, dict):
            raise ValueError("Actividad inválida.")
        codigo = fila.get("codigo")
        if codigo not in esperado or codigo in vistos:
            raise ValueError("Actividad duplicada o desconocida.")
        vistos.add(codigo)
        estado = fila.get("resultado", "PENDIENTE")
        observacion = str(fila.get("observacion") or "").strip()
        if estado not in RESULTADOS or len(observacion) > 1000:
            raise ValueError("Resultado u observación inválidos.")
        if estado == "NO_CUMPLE" and not observacion:
            raise ValueError("Cada control no conforme requiere observación.")
        resultado.append({**esperado[codigo], "resultado": estado, "observacion": observacion})
    return resultado

def validar_cierre(checklist):
    if any(f["resultado"] == "PENDIENTE" for f in checklist):
        raise ValueError("Para finalizar, evalúe todas las actividades (incluya No aplica cuando corresponda).")


def actualizar_checklist_pendiente(checklist):
    """Añade controles nuevos a registros abiertos sin cambiar respuestas previas.

    Los códigos ya existentes conservan sus posiciones y sus resultados.
    Las constancias finalizadas mantienen su versión histórica.
    """
    actual = list(checklist or [])
    existentes = {fila["codigo"] for fila in actual}
    nuevos = [fila for fila in plantilla() if fila["codigo"] not in existentes]
    for nuevo in nuevos:
        posiciones = [i for i, fila in enumerate(actual) if fila["grupo"] == nuevo["grupo"]]
        indice = posiciones[-1] + 1 if posiciones else len(actual)
        actual.insert(indice, nuevo)
    return actual
