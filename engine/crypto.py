"""AES-256-GCM with PBKDF2-SHA256. The browser decrypts the same format with WebCrypto."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 120_000


def _key(passphrase: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(passphrase.encode())


def encrypt_bytes(passphrase: str, data: bytes) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    sealed = AESGCM(_key(passphrase, salt)).encrypt(iv, data, None)
    return base64.b64encode(salt + iv + sealed).decode()


def decrypt_bytes(passphrase: str, blob: str) -> bytes:
    raw = base64.b64decode(blob.strip())
    return AESGCM(_key(passphrase, raw[:16])).decrypt(raw[16:28], raw[28:], None)


def encrypt_json(passphrase: str, value: Any) -> str:
    return encrypt_bytes(passphrase, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def decrypt_json(passphrase: str, blob: str) -> Any:
    return json.loads(decrypt_bytes(passphrase, blob).decode())
