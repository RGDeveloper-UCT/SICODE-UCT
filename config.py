import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Endurecimiento de sesión para el entorno institucional.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "si"}
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_HOURS", "8")))

    # Límite global de cargas HTTP. El análisis documental aplica además su
    # propio límite más estricto y elimina el archivo temporal al finalizar.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "45")) * 1024 * 1024

    # Análisis documental asistido. El PDF nunca forma parte del repositorio de
    # SICODE: se procesa temporalmente y solo se persisten metadatos validados.
    DOCUMENT_ANALYSIS_MAX_MB = int(os.getenv("DOCUMENT_ANALYSIS_MAX_MB", "40"))
    DOCUMENT_ANALYSIS_MAX_PAGES = int(os.getenv("DOCUMENT_ANALYSIS_MAX_PAGES", "200"))
    DOCUMENT_ANALYSIS_OCR_ENABLED = os.getenv("DOCUMENT_ANALYSIS_OCR_ENABLED", "true").lower() in {
        "1", "true", "yes", "si"
    }
    DOCUMENT_ANALYSIS_OCR_LANGUAGE = os.getenv("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa")
    # Ruta explícita para instalaciones systemd con PATH restringido.
    DOCUMENT_ANALYSIS_TESSERACT_CMD = os.getenv("DOCUMENT_ANALYSIS_TESSERACT_CMD", "/usr/bin/tesseract")
    # En servidores CPU se prioriza una sola pasada OCR. La segunda pasada se
    # puede activar manualmente para documentos difíciles sin duplicar el costo
    # de todos los análisis normales.
    DOCUMENT_ANALYSIS_OCR_SECOND_PASS = os.getenv("DOCUMENT_ANALYSIS_OCR_SECOND_PASS", "false").lower() in {
        "1", "true", "yes", "si"
    }
    DOCUMENT_ANALYSIS_TEMP_DIR = os.getenv("DOCUMENT_ANALYSIS_TEMP_DIR") or None
    DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES = int(os.getenv("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", "30"))
    DOCUMENT_ANALYSIS_SHOW_DIAGNOSTICS = os.getenv("DOCUMENT_ANALYSIS_SHOW_DIAGNOSTICS", "true").lower() in {
        "1", "true", "yes", "si"
    }

    # Herramienta PostgreSQL para respaldos. Normalmente se autodetecta; esta
    # variable permite fijar la ruta cuando systemd/Gunicorn usa un PATH reducido.
    PG_DUMP_PATH = os.getenv("PG_DUMP_PATH")

    # IA local para búsquedas. Ollama se mantiene en loopback para que los
    # metadatos consultados no salgan del servidor institucional.
    AI_SEARCH_ENABLED = os.getenv("AI_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes", "si"}
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
    # El servidor institucional puede ejecutar Ollama únicamente con CPU. Se
    # concede un margen amplio antes de recurrir al intérprete básico seguro.
    OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))

    # IA documental reutiliza Ollama local, pero tiene límites independientes.
    # El límite de contexto por defecto se mantiene contenido para no prolongar
    # innecesariamente el worker HTTP en servidores sin GPU.
    DOCUMENT_ANALYSIS_AI_ENABLED = os.getenv("DOCUMENT_ANALYSIS_AI_ENABLED", "true").lower() in {
        "1", "true", "yes", "si"
    }
    DOCUMENT_ANALYSIS_AI_MODEL = os.getenv("DOCUMENT_ANALYSIS_AI_MODEL", OLLAMA_MODEL)
    DOCUMENT_ANALYSIS_AI_TIMEOUT = float(os.getenv("DOCUMENT_ANALYSIS_AI_TIMEOUT", "75"))
    DOCUMENT_ANALYSIS_AI_MAX_CHARS = int(os.getenv("DOCUMENT_ANALYSIS_AI_MAX_CHARS", "12000"))

    # UO · Usuarios Online. El navegador envía un pulso cada 20 segundos; una
    # presencia sin pulso deja de considerarse online al superar esta ventana.
    UO_ONLINE_TTL_SECONDS = int(os.getenv("UO_ONLINE_TTL_SECONDS", "75"))

    @classmethod
    def validar(cls):
        faltantes = []
        if not cls.SECRET_KEY:
            faltantes.append("SECRET_KEY")
        if not cls.SQLALCHEMY_DATABASE_URI:
            faltantes.append("DATABASE_URL")
        if faltantes:
            raise RuntimeError(
                "Faltan variables de entorno obligatorias para SICODE-UCT: " + ", ".join(faltantes)
            )
