#!/usr/bin/env python3
"""Backup programado de PostgreSQL para SICODE-UCT.

Genera primero un dump validado mediante el servicio institucional de backups y
solo después elimina respaldos locales antiguos que respeten el patrón propio
de SICODE. La retención local no sustituye una copia externa/cifrada.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from app import create_app
from app.services.backup_service import generar_backup, listar_backups, obtener_directorio_backups


def _retencion_dias() -> int:
    try:
        return max(1, int(os.getenv("SICODE_BACKUP_RETENTION_DAYS", "14")))
    except ValueError:
        return 14


def main() -> int:
    app = create_app()
    with app.app_context():
        ruta = generar_backup(app.config["SQLALCHEMY_DATABASE_URI"])
        limite = datetime.now() - timedelta(days=_retencion_dias())
        eliminados = []
        directorio = obtener_directorio_backups()

        for item in listar_backups():
            nombre = item["nombre"]
            if nombre == ruta.name or item["modificado"] >= limite:
                continue
            candidato = directorio / nombre
            if candidato.parent == directorio and candidato.name.startswith("backup_sicode_uct_") and candidato.suffix == ".sql":
                candidato.unlink(missing_ok=True)
                eliminados.append(nombre)

        print(f"BACKUP_OK={ruta}")
        print(f"RETENCION_DIAS={_retencion_dias()}")
        print(f"BACKUPS_ELIMINADOS={len(eliminados)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
