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


def test_resolver_backup_impide_escape_de_directorio(app_backup, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "obtener_directorio_backups", lambda: tmp_path)

    with app_backup.app_context():
        with pytest.raises(backup_service.BackupError):
            backup_service.resolver_backup("../backup_sicode_uct_robo.sql")
