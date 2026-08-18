import os
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def obtener_version():
    configurada = os.getenv("SICODE_VERSION")
    if configurada:
        return configurada.strip()

    raiz = Path(__file__).resolve().parents[2]
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=raiz,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return resultado.stdout.strip() or "desconocida"
    except (OSError, subprocess.SubprocessError):
        return "desconocida"
