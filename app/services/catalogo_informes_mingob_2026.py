"""Catálogo inicial de los TRES informes de Dirección de Informática / MINGOB de octubre de 2026.

Solo datos técnicos extraídos de los informes recibidos y referencias públicas
oficiales; NO contiene sus archivos originales, logos ni datos privados.

Este comando es idempotente. No notifica 19 veces por registros históricos.
Un CVE mencionado por el informe no acredita exposición del inventario local.
"""
from datetime import date

from app import db
from app.models.seguridad_operativa import VulnerabilidadTI
from app.services.bitacora_service import registrar_bitacora

CHROME_29 = "https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_02107719452.html"
CHROME_27 = "https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_0562499947.html"
CHROME_20 = "https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_02018666648.html"
CHROME_13 = "https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_01668083673.html"
ORACLE = "https://www.oracle.com/security-alerts/cpuoct2026.html"
PYTHON = "https://www.python.org/downloads/release/python-31410/"
EXPAT = "https://github.com/libexpat/libexpat/blob/R_2_9_0/expat/Changes"
PHP = "https://www.php.net/archive/2026.php"

# CVE, producto, título, severidad del informe, fecha, referencia, medida
AVISOS = {
    "CHROME": [
        ("CVE-2026-76024", "MediaStream: corrupción de memoria", "CRITICA", "2026-10-29", CHROME_29),
        ("CVE-2026-118306", "FileSystem: corrupción de memoria", "CRITICA", "2026-10-27", CHROME_27),
        ("CVE-2026-118331", "FileAPI: validación inadecuada de entradas", "CRITICA", "2026-10-27", CHROME_27),
        ("CVE-2026-118348", "Skia: validación inadecuada de entradas", "CRITICA", "2026-10-27", CHROME_27),
        ("CVE-2026-118344", "Layout: uso de memoria después de liberarla", "CRITICA", "2026-10-27", CHROME_27),
        ("CVE-2026-113303", "WebRTC: corrupción de memoria", "CRITICA", "2026-10-20", CHROME_20),
        ("CVE-2026-110136", "Visor de PDF: uso de memoria después de liberarla", "CRITICA", "2026-10-13", CHROME_13),
        ("CVE-2026-118318", "V8: controles de acceso inadecuados", "ALTA", "2026-10-27", CHROME_27),
        ("CVE-2026-119269", "Blink: uso de memoria después de liberarla", "ALTA", "2026-10-29", CHROME_29),
    ],
    "JAVA": [
        ("CVE-2026-91484", "Java Plugin: acceso y alteración de datos con código no confiable", "ALTA", "2026-10-20", ORACLE),
        ("CVE-2026-43660", "JavaFX / WebKitGTK: confidencialidad, integridad y disponibilidad", "ALTA", "2026-10-20", ORACLE),
        ("CVE-2026-91415", "Java 2D: problemas de seguridad y disponibilidad", "ALTA", "2026-10-20", ORACLE),
        ("CVE-2026-91395", "Utilidades de Java: posible alteración o indisponibilidad", "MEDIA", "2026-10-20", ORACLE),
    ],
    "PYTHON": [
        ("CVE-2026-115557", "ssl: desconfianza de claves intermedias eMudhra comprometidas", "DESCONOCIDA", "2026-10-26", PYTHON),
        ("CVE-2026-114583", "tarfile: rechazo de enlaces que sustituyen destinos", "DESCONOCIDA", "2026-10-26", PYTHON),
        ("CVE-2026-77214", "Expat / XML_ParseBuffer: lectura fuera de límites", "DESCONOCIDA", "2026-10-26", EXPAT),
        ("CVE-2026-102633", "Expat / expat_realloc: desbordamiento en plataformas de 32 bits", "DESCONOCIDA", "2026-10-26", EXPAT),
    ],
    "PHP": [
        ("CVE-2026-109618", "PHP: corrupción de memoria por agotamiento OOM", "CRITICA", "2026-10-21", PHP),
        ("CVE-2026-109619", "PHP: acceso a estado global liberado (use-after-free)", "CRITICA", "2026-10-21", PHP),
    ],
}

RECOMENDACIONES = {
    "CHROME": (
        "Identificar versión, plataforma y canal de Chrome; consultar el boletín vigente, "
        "actualizar y reiniciar. Como referencia al 29/10/2026: 156.0.8078.79/.80 "
        "en Windows/macOS y 156.0.8078.79 en Linux. Verificar la versión vigente para "
        "el canal/plataforma y documentar el resultado."
    ),
    "JAVA": (
        "Verificar Java SE, JavaFX, Java Plugin, GraalVM y componentes realmente utilizados "
        "contra la matriz de Oracle del 20/10/2026; aplicar parches oficiales, realizar "
        "respaldo/pruebas y validar compatibilidad de aplicaciones. Las versiones "
        "listadas como afectadas NO son necesariamente versiones corregidas."
    ),
    "PYTHON": (
        "Verificar todas las instalaciones y entornos virtuales de Python. El aviso "
        "del 26/10/2026 menciona 3.15.2, 3.14.10, 3.13.18, 3.12.16 y 3.11.18 "
        "como versiones de mantenimiento; comprobar el canal del proveedor y sus "
        "parches retroportados. Revisar ssl/certificados, archivos TAR y Expat/XML."
    ),
    "PHP": (
        "Actualizar PHP a versión corregida por el proveedor: 8.2.35, 8.3.36, "
        "8.4.27 o 8.5.12 (según rama); reiniciar servicios y verificar aplicaciones. "
        "Las medidas temporales no sustituyen la actualización; validar con el "
        "administrador y plan de cambio antes de modificar parámetros de servidor."
    ),
}


def cargar_catalogo_octubre_2026():
    nuevos, actualizados = 0, 0
    for producto, filas in AVISOS.items():
        for cve, titulo, severidad, fecha, url in filas:
            v = VulnerabilidadTI.query.filter_by(cve=cve).first()
            if v is None:
                v = VulnerabilidadTI(
                    cve=cve, titulo=titulo, fuente="MINGOB", fuentes=["MINGOB"],
                    fabricante={"CHROME": "Google", "JAVA": "Oracle", "PYTHON": "Python / Expat",
                                "PHP": "PHP Group"}[producto],
                    producto=producto, severidad=severidad, descripcion=titulo,
                    recomendacion=RECOMENDACIONES[producto],
                    referencia=url, fecha_publicacion=date.fromisoformat(fecha),
                    explotada=False,
                )
                db.session.add(v)
                nuevos += 1
            else:
                fuentes = sorted(set((v.fuentes or []) + ["MINGOB"]))
                if fuentes != (v.fuentes or []):
                    v.fuentes = fuentes
                    actualizados += 1
                if not v.recomendacion:
                    v.recomendacion = RECOMENDACIONES[producto]
                if not v.fecha_publicacion:
                    v.fecha_publicacion = date.fromisoformat(fecha)
                if v.severidad == "DESCONOCIDA" and severidad != "DESCONOCIDA":
                    v.severidad = severidad
    registrar_bitacora(
        accion="CARGA_INFORMES_SEGURIDAD_2026", modulo="Seguridad Informática",
        descripcion=f"Catálogo MINGOB (metadatos): {nuevos} CVE nuevos, {actualizados} vinculados.",
        usuario_id=None, commit=False,
    )
    db.session.commit()
    return {"nuevos": nuevos, "existentes_vinculados": actualizados, "total_catalogo_informes": sum(map(len, AVISOS.values()))}
