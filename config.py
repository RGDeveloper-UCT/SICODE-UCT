import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "si"}
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_HOURS", "8")))

    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "45")) * 1024 * 1024

    DOCUMENT_ANALYSIS_MAX_MB = int(os.getenv("DOCUMENT_ANALYSIS_MAX_MB", "40"))
    DOCUMENT_ANALYSIS_MAX_PAGES = int(os.getenv("DOCUMENT_ANALYSIS_MAX_PAGES", "200"))
    DOCUMENT_ANALYSIS_OCR_ENABLED = os.getenv("DOCUMENT_ANALYSIS_OCR_ENABLED", "true").lower() in {"1", "true", "yes", "si"}
    DOCUMENT_ANALYSIS_OCR_LANGUAGE = os.getenv("DOCUMENT_ANALYSIS_OCR_LANGUAGE", "spa")
    DOCUMENT_ANALYSIS_TESSERACT_CMD = os.getenv("DOCUMENT_ANALYSIS_TESSERACT_CMD", "/usr/bin/tesseract")
    DOCUMENT_ANALYSIS_OCR_SECOND_PASS = os.getenv("DOCUMENT_ANALYSIS_OCR_SECOND_PASS", "false").lower() in {"1", "true", "yes", "si"}
    DOCUMENT_ANALYSIS_OCR_WORKERS = max(1, int(os.getenv("DOCUMENT_ANALYSIS_OCR_WORKERS", "2")))
    DOCUMENT_ANALYSIS_TEMP_DIR = os.getenv("DOCUMENT_ANALYSIS_TEMP_DIR") or None
    DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES = int(os.getenv("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES", "30"))
    DOCUMENT_ANALYSIS_SHOW_DIAGNOSTICS = os.getenv("DOCUMENT_ANALYSIS_SHOW_DIAGNOSTICS", "true").lower() in {"1", "true", "yes", "si"}

    # SICODE.IA en segundo plano: Redis/RQ desacopla OCR/IA de Gunicorn.
    SICODE_REDIS_URL = os.getenv("SICODE_REDIS_URL", "redis://127.0.0.1:6379/0")
    SICODE_IA_QUEUE = os.getenv("SICODE_IA_QUEUE", "sicode_ia")
    SICODE_IA_JOB_TIMEOUT = int(os.getenv("SICODE_IA_JOB_TIMEOUT", "3600"))
    SICODE_IA_RESULT_TTL = int(os.getenv("SICODE_IA_RESULT_TTL", "86400"))
    SICODE_IA_QUEUE_TEMP_DIR = os.getenv("SICODE_IA_QUEUE_TEMP_DIR") or DOCUMENT_ANALYSIS_TEMP_DIR
    SICODE_IA_FAST_MODEL = os.getenv("SICODE_IA_FAST_MODEL", "qwen3:0.6b")

    PG_DUMP_PATH = os.getenv("PG_DUMP_PATH")

    AI_SEARCH_ENABLED = os.getenv("AI_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes", "si"}
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
    OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))

    DOCUMENT_ANALYSIS_AI_ENABLED = os.getenv("DOCUMENT_ANALYSIS_AI_ENABLED", "true").lower() in {"1", "true", "yes", "si"}
    DOCUMENT_ANALYSIS_AI_MODEL = os.getenv("DOCUMENT_ANALYSIS_AI_MODEL", OLLAMA_MODEL)
    DOCUMENT_ANALYSIS_AI_TIMEOUT = float(os.getenv("DOCUMENT_ANALYSIS_AI_TIMEOUT", "180"))
    DOCUMENT_ANALYSIS_AI_MAX_CHARS = int(os.getenv("DOCUMENT_ANALYSIS_AI_MAX_CHARS", "12000"))

    UO_ONLINE_TTL_SECONDS = int(os.getenv("UO_ONLINE_TTL_SECONDS", "75"))

    @classmethod
    def validar(cls):
        faltantes = []
        if not cls.SECRET_KEY:
            faltantes.append("SECRET_KEY")
        if not cls.SQLALCHEMY_DATABASE_URI:
            faltantes.append("DATABASE_URL")
        if faltantes:
            raise RuntimeError("Faltan variables de entorno obligatorias para SICODE-UCT: " + ", ".join(faltantes))
