from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app

from app.checks import HallazgoIntegridad


def _parece_dump_postgresql(archivo):
    try:
        with archivo.open("rb") as manejador:
            muestra = manejador.read(2 * 1024 * 1024)
    except OSError:
        return False

    texto = muestra.decode("utf-8", errors="ignore")
    return (
        "PostgreSQL database dump" in texto
        and ("CREATE TABLE" in texto or "COPY " in texto or "INSERT INTO" in texto)
    )


def ejecutar():
    hallazgos = []
    directorio = Path(current_app.root_path).parent / "backups"
    archivos = list(directorio.glob("backup_sicode_uct_*.sql")) if directorio.exists() else []

    if not archivos:
        hallazgos.append(HallazgoIntegridad(
            codigo="BKP-AUSENTE-001",
            severidad="error",
            modulo="Backups",
            entidad="Sistema",
            registro="Respaldo PostgreSQL",
            descripcion="No se encontró ningún respaldo generado por SICODE.",
            recomendacion="Generar un backup antes de cambios, migraciones o cierre de jornada.",
        ))
        return hallazgos

    ultimo = max(archivos, key=lambda archivo: archivo.stat().st_mtime)
    modificado = datetime.fromtimestamp(ultimo.stat().st_mtime)

    if ultimo.stat().st_size == 0:
        hallazgos.append(HallazgoIntegridad(
            codigo="BKP-VACIO-001",
            severidad="error",
            modulo="Backups",
            entidad="Archivo",
            registro=ultimo.name,
            descripcion="El respaldo más reciente tiene tamaño cero.",
            recomendacion="Generar un nuevo respaldo y validar el funcionamiento de pg_dump.",
        ))
    elif not _parece_dump_postgresql(ultimo):
        hallazgos.append(HallazgoIntegridad(
            codigo="BKP-FORMATO-001",
            severidad="error",
            modulo="Backups",
            entidad="Archivo",
            registro=ultimo.name,
            descripcion="El archivo no presenta la estructura esperada de un dump SQL de PostgreSQL.",
            recomendacion="No confiar en este respaldo; generar otro y ejecutar la prueba de restauración del runbook técnico.",
        ))
    elif modificado < datetime.now() - timedelta(hours=24):
        hallazgos.append(HallazgoIntegridad(
            codigo="BKP-ANTIGUO-001",
            severidad="advertencia",
            modulo="Backups",
            entidad="Archivo",
            registro=ultimo.name,
            descripcion=f"El último respaldo es del {modificado.strftime('%d/%m/%Y %H:%M')}.",
            recomendacion="Generar un respaldo reciente según la rutina institucional definida.",
        ))

    return hallazgos
