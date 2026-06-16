"""Encriptación AES-256-GCM para secrets guardados en la DB."""
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_HEX = os.environ.get("ENCRYPTION_KEY", "")


def _key() -> bytes:
    if not _KEY_HEX or len(_KEY_HEX) != 64:
        raise RuntimeError("ENCRYPTION_KEY debe ser 64 caracteres hex (32 bytes).")
    return bytes.fromhex(_KEY_HEX)


def encrypt(plain: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(enc: str) -> str:
    if not enc or enc.startswith("REEMPLAZAR"):
        return enc
    data = base64.b64decode(enc)
    nonce, ct = data[:12], data[12:]
    return AESGCM(_key()).decrypt(nonce, ct, None).decode()
