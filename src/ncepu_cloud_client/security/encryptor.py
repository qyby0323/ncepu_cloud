from __future__ import annotations

import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except Exception:  # pragma: no cover
    AESGCM = None
    PBKDF2HMAC = None
    hashes = None

MAGIC = b"NCEPUENC1"
SALT_SIZE = 16
NONCE_SIZE = 12


class Encryptor:
    def __init__(self, password: str):
        if AESGCM is None:
            raise RuntimeError("cryptography 未安装，请执行 pip install cryptography")
        self.password = password.encode("utf-8")

    def encrypt_file(self, source: Path, target: Path | None = None) -> Path:
        target = target or source.with_name(source.name + ".ncepuenc")
        salt = os.urandom(SALT_SIZE)
        nonce = os.urandom(NONCE_SIZE)
        key = self._derive_key(salt)
        encrypted = AESGCM(key).encrypt(nonce, source.read_bytes(), None)
        target.write_bytes(MAGIC + salt + nonce + encrypted)
        return target

    def decrypt_file(self, source: Path, target: Path | None = None) -> Path:
        data = source.read_bytes()
        if not data.startswith(MAGIC):
            raise ValueError("不是华电云盘加密文件")
        offset = len(MAGIC)
        salt = data[offset:offset + SALT_SIZE]
        offset += SALT_SIZE
        nonce = data[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE
        encrypted = data[offset:]
        key = self._derive_key(salt)
        plain = AESGCM(key).decrypt(nonce, encrypted, None)
        target = target or source.with_suffix("")
        target.write_bytes(plain)
        return target

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
        return kdf.derive(self.password)

