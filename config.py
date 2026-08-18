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

    # Limita cargas accidentales o maliciosas de archivos. Puede ajustarse por .env.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "16")) * 1024 * 1024

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
