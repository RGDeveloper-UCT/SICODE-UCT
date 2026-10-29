"""Cifrado de la bóveda institucional compartida de HashPass.

Modelo custodial: la clave grupal se proporciona por un secreto del servidor,
NO se incluye en Git, ni en la base de datos. Cada usuario debe desbloquear
su propia bóveda Argon2id antes de consultar o modificar registros compartidos.

ATENCIÓN: alguien con acceso simultáneo a la clave del servicio y la BD
podría descifrar todos los registros. No es E2EE ni equivale a KeePass.
"""
import base64
import binascii
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_LENGTH = 32
_NONCE_LENGTH = 12


class SharedVaultKeyError(ValueError):
    """Configuración institucional de cifrado ausente o incorrecta."""


def obtener_clave_compartida(config):
    codificada = config.get("HASHPASS_SHARED_KEY_B64")
    if not isinstance(codificada, str) or not codificada:
        raise SharedVaultKeyError("Falta la clave de custodia de HashPass.")
    try:
        clave = base64.b64decode(codificada, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SharedVaultKeyError("Formato de clave institucional inválido.") from exc
    if len(clave) != _KEY_LENGTH:
        raise SharedVaultKeyError("La clave institucional debe tener 256 bits.")
    return clave


def cifrar_compartido(clave: bytes, id_registro: str, datos: dict):
    if len(clave) != _KEY_LENGTH or not isinstance(datos, dict):
        raise ValueError("Datos de cifrado inválidos")
    nonce = os.urandom(_NONCE_LENGTH)
    plano = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cifrado = AESGCM(clave).encrypt(
        nonce, plano, f"hashpass:compartido:v1:{id_registro}".encode("ascii"),
    )
    return nonce, cifrado


def descifrar_compartido(clave: bytes, id_registro: str, nonce: bytes, cifrado: bytes):
    plano = AESGCM(clave).decrypt(
        nonce, cifrado, f"hashpass:compartido:v1:{id_registro}".encode("ascii"),
    )
    resultado = json.loads(plano.decode("utf-8"))
    if not isinstance(resultado, dict):
        raise ValueError("Estructura de secreto inválida")
    return resultado
