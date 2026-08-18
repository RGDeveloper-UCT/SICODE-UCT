import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from flask import current_app
from sqlalchemy.engine import make_url


class BackupError(RuntimeError):
    pass


def obtener_directorio_backups():
    directorio = Path(current_app.root_path).parent / "backups"
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio


def listar_backups():
    archivos = []
    for archivo in obtener_directorio_backups().glob("backup_sicode_uct_*.sql"):
        stat = archivo.stat()
        archivos.append({
            "nombre": archivo.name,
            "tamano_mb": round(stat.st_size / (1024 * 1024), 2),
            "modificado": datetime.fromtimestamp(stat.st_mtime),
        })
    return sorted(archivos, key=lambda item: item["modificado"], reverse=True)


def _validar_dump(ruta):
    if not ruta.exists() or ruta.stat().st_size <= 0:
        raise BackupError("El respaldo generado está vacío.")
    try:
        muestra = ruta.read_bytes()[: 2 * 1024 * 1024]
    except OSError as error:
        raise BackupError("No fue posible validar el archivo de respaldo.") from error
    texto = muestra.decode("utf-8", errors="ignore")
    if "PostgreSQL database dump" not in texto:
        raise BackupError("El archivo generado no tiene la estructura esperada de un dump PostgreSQL.")


def generar_backup(database_url, timeout=180):
    if not database_url:
        raise BackupError("No se encontró la configuración de la base de datos.")

    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise BackupError("La generación de backups institucionales requiere PostgreSQL.")

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise BackupError("No se encontró pg_dump en el servidor.")

    directorio = obtener_directorio_backups()
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = directorio / f"backup_sicode_uct_{marca_tiempo}.sql"

    comando = [pg_dump]
    if url.host:
        comando.extend(["--host", url.host])
    if url.port:
        comando.extend(["--port", str(url.port)])
    if url.username:
        comando.extend(["--username", url.username])
    comando.extend([
        "--dbname", url.database,
        "--file", str(ruta),
        "--format", "plain",
        "--encoding", "UTF8",
        "--no-owner",
        "--no-privileges",
    ])

    entorno = os.environ.copy()
    if url.password:
        # Evita colocar la contraseña en la línea de comando visible por otros
        # procesos del sistema operativo.
        entorno["PGPASSWORD"] = url.password

    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=entorno,
        )
    except subprocess.TimeoutExpired as error:
        ruta.unlink(missing_ok=True)
        raise BackupError("El respaldo excedió el tiempo máximo permitido.") from error
    except OSError as error:
        ruta.unlink(missing_ok=True)
        raise BackupError("No fue posible ejecutar pg_dump.") from error

    if resultado.returncode != 0:
        ruta.unlink(missing_ok=True)
        current_app.logger.error("pg_dump falló: %s", resultado.stderr.strip())
        raise BackupError("PostgreSQL no pudo completar el respaldo. Revise el log del servidor.")

    _validar_dump(ruta)
    return ruta


def resolver_backup(nombre_archivo):
    if not nombre_archivo.startswith("backup_sicode_uct_") or not nombre_archivo.endswith(".sql"):
        raise BackupError("Nombre de archivo no permitido.")

    directorio = obtener_directorio_backups().resolve()
    ruta = (directorio / nombre_archivo).resolve()
    if ruta.parent != directorio or not ruta.exists() or not ruta.is_file():
        raise BackupError("El respaldo solicitado no existe o no es accesible.")
    return ruta
