"""Configuración segura común para la suite pytest de SICODE-UCT.

Objetivos:
- permitir importar ``app`` aunque pytest se invoque mediante el ejecutable del sistema;
- impedir que una ejecución accidental de pytest en el servidor use la base productiva;
- conservar bases explícitamente identificadas como pruebas/CI.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _es_base_segura_para_pruebas(url: str) -> bool:
    texto = (url or "").strip()
    if not texto:
        return False

    if texto.lower().startswith("sqlite:"):
        return True

    try:
        nombre_bd = (urlparse(texto).path or "").strip("/").lower()
    except ValueError:
        return False

    return bool(nombre_bd) and ("test" in nombre_bd or "pytest" in nombre_bd or nombre_bd.endswith("_ci"))


_url_actual = os.environ.get("DATABASE_URL", "")
if not _es_base_segura_para_pruebas(_url_actual):
    ruta_sqlite = Path(tempfile.gettempdir()) / f"sicode_pytest_{os.getpid()}.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{ruta_sqlite}"

# Configuración exclusivamente de pruebas. load_dotenv() no reemplaza estas
# variables porque ya existen en el entorno antes de importar config.py.
os.environ.setdefault("SECRET_KEY", "sicode-pytest-secret-local")
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["AI_SEARCH_ENABLED"] = "false"
