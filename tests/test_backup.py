from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.services import backup_service


@pytest.fixture()
def app_backup():
    app = create_app()
    app.config.update(TESTING=True)
    return app


def test_pg_dump_no_expone_password_en_argumentos(app_backup, tmp_path, monkeypatch):
    capturado = {}

    monkeypatch.setattr(backup_service, "obtener_directorio_backups", lambda: tmp_path)
    monkeypatch.setattr(backup_service.shutil, "which", lambda nombre: "/usr/bin/pg_dump")

    def ejecutar(comando, **kwargs):
        capturado["comando"] = comando
        capturado["env"] = kwargs["env"]
        ruta = comando[comando.index("--file") + 1]
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write("-- PostgreSQL database dump\nCREATE TABLE prueba (id integer);\n")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(backup_service.subprocess, "run", ejecutar)

    with app_backup.app_context():
        ruta = backup_service.generar_backup(
            "postgresql+psycopg2://sicode:secreto-super@localhost:5432/sicode"
        )

    assert ruta.exists()
    assert "secreto-super" not in " ".join(capturado["comando"])
    assert capturado["env"]["PGPASSWORD"] == "secreto-super"


def test_pg_dump_admite_ruta_explicitamente_configurada(app_backup, tmp_path, monkeypatch):
    ejecutable = tmp_path / "pg_dump"
    ejecutable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ejecutable.chmod(0o755)

    monkeypatch.setattr(backup_service.shutil, "which", lambda _nombre: None)
    app_backup.config["PG_DUMP_PATH"] = str(ejecutable)

    with app_backup.app_context():
        encontrado = backup_service.resolver_pg_dump()

    assert encontrado == str(ejecutable.resolve())


def test_pg_dump_prioriza_path_si_no_hay_configuracion(app_backup, monkeypatch):
    app_backup.config["PG_DUMP_PATH"] = None
    monkeypatch.setattr(backup_service.shutil, "which", lambda nombre: "/ruta/desde/path/pg_dump")

    with app_backup.app_context():
        encontrado = backup_service.resolver_pg_dump()

    assert encontrado == "/ruta/desde/path/pg_dump"


def test_resolver_backup_impide_escape_de_directorio(app_backup, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "obtener_directorio_backups", lambda: tmp_path)

    with app_backup.app_context():
        with pytest.raises(backup_service.BackupError):
            backup_service.resolver_backup("../backup_sicode_uct_robo.sql")


def test_servicio_systemd_define_pythonpath_del_proyecto():
    plantilla = Path("deploy/systemd/sicode-backup.service.template").read_text(encoding="utf-8")
    assert "WorkingDirectory=__SICODE_APPDIR__" in plantilla
    assert "Environment=PYTHONPATH=__SICODE_APPDIR__" in plantilla
    assert "ExecStart=__SICODE_PYTHON__ __SICODE_APPDIR__/scripts/backup_programado.py" in plantilla
