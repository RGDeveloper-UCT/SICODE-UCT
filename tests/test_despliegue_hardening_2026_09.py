import inspect
from pathlib import Path

from app.routes import sicode_ia_jobs


def test_worker_ia_usa_venv_institucional_configurable():
    plantilla = Path("deploy/systemd/sicode-ia-worker.service.template").read_text(encoding="utf-8")
    assert "ExecStart=__SICODE_VENV__/bin/rq worker sicode_ia" in plantilla
    assert "__SICODE_APPDIR__/.venv/bin/rq" not in plantilla
    assert "NoNewPrivileges=true" in plantilla


def test_actualizador_reinicia_worker_ia_si_esta_instalado():
    script = Path("scripts/actualizar_servidor_seguro.sh").read_text(encoding="utf-8")
    assert 'IA_WORKER_SERVICE="${SICODE_IA_WORKER_SERVICE:-sicode-ia-worker.service}"' in script
    assert 'sudo systemctl restart "$IA_WORKER_SERVICE"' in script
    assert "python -m pip check" in script


def test_sicode_ia_jobs_exige_permiso_de_modificacion():
    fuente = inspect.getsource(sicode_ia_jobs._exigir_modificacion)
    assert "puede_modificar" in fuente
    assert "abort(403)" in fuente


def test_estado_job_no_expone_traceback_al_navegador():
    fuente = inspect.getsource(sicode_ia_jobs.estado)
    assert "exc_info" not in fuente
    assert "Revise el servicio sicode-ia-worker con un administrador" in fuente
