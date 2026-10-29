"""Criptografía de HashPass HP-001: sin claves persistidas ni cifrado casero.

El servidor recibe la maestra para cada operación, la usa para derivar una
KEK con Argon2id y la descarta al finalizar la petición. NO es E2EE:
un servidor web comprometido puede observar los secretos en uso.
"""
import json
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1
ARGON_TIME = 3
ARGON_MEMORY_KIB = 65536
ARGON_PARALLELISM = 2


def _derivar(maestra: str, sal: bytes) -> bytes:
    if not isinstance(maestra, str) or not 15 <= len(maestra) <= 1024:
        raise ValueError("Contraseña maestra inválida")
    return hash_secret_raw(
        secret=maestra.encode("utf-8"), salt=sal, time_cost=ARGON_TIME,
        memory_cost=ARGON_MEMORY_KIB, parallelism=ARGON_PARALLELISM,
        hash_len=32, type=Type.ID,
    )


def crear_boveda(maestra: str, usuario_id: int):
    """Retorna (sal, nonce, DEK envuelta), nunca persiste la DEK."""
    sal, nonce, dek = os.urandom(16), os.urandom(12), os.urandom(32)
    envuelta = AESGCM(_derivar(maestra, sal)).encrypt(
        nonce, dek, f"hashpass:v1:boveda:{usuario_id}".encode("ascii"),
    )
    return sal, nonce, envuelta


def abrir_boveda(maestra: str, usuario_id: int, sal: bytes, nonce: bytes, envuelta: bytes):
    """Incorrecta/tampered: cryptography.exceptions.InvalidTag."""
    return AESGCM(_derivar(maestra, sal)).decrypt(
        nonce, envuelta, f"hashpass:v1:boveda:{usuario_id}".encode("ascii"),
    )


def reenvolver_clave(dek: bytes, nueva_maestra: str, usuario_id: int):
    if len(dek) != 32:
        raise ValueError("DEK inválida")
    sal, nonce = os.urandom(16), os.urandom(12)
    envuelta = AESGCM(_derivar(nueva_maestra, sal)).encrypt(
        nonce, dek, f"hashpass:v1:boveda:{usuario_id}".encode("ascii"),
    )
    return sal, nonce, envuelta


def cifrar_registro(dek: bytes, usuario_id: int, registro_id: str, datos: dict):
    if len(dek) != 32 or not isinstance(datos, dict):
        raise ValueError("Datos inválidos")
    nonce = os.urandom(12)
    plano = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cifrado = AESGCM(dek).encrypt(
        nonce, plano, f"hashpass:v1:registro:{usuario_id}:{registro_id}".encode("ascii"),
    )
    return nonce, cifrado


def descifrar_registro(dek: bytes, usuario_id: int, registro_id: str, nonce: bytes, cifrado: bytes):
    plano = AESGCM(dek).decrypt(
        nonce, cifrado, f"hashpass:v1:registro:{usuario_id}:{registro_id}".encode("ascii"),
    )
    return json.loads(plano.decode("utf-8"))
