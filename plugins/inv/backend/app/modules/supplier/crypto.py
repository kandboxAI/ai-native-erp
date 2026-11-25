"""供应商收款账号的加密与脱敏。

平台暂无统一的字段加密服务，这里用标准库实现带校验的对称加密（SHA-256 计数器密钥流 + HMAC-SHA256），
密钥由 JWT 密钥派生。平台提供统一加密服务后替换本文件即可（存量密文需重新加密）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from app.core.config import get_settings

_VERSION = b"v1"


def _keys() -> tuple[bytes, bytes]:
    root = hashlib.sha256(f"md_supplier_bank_account:{get_settings().jwt_secret}".encode()).digest()
    return hashlib.sha256(root + b"enc").digest(), hashlib.sha256(root + b"mac").digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(out[:length])


def encrypt_account_no(plain: str) -> str:
    enc_key, mac_key = _keys()
    nonce = secrets.token_bytes(16)
    data = plain.encode()
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(enc_key, nonce, len(data))))
    tag = hmac.new(mac_key, _VERSION + nonce + cipher, hashlib.sha256).digest()
    return (_VERSION + b":" + base64.urlsafe_b64encode(nonce + cipher + tag)).decode()


def decrypt_account_no(token: str) -> str:
    enc_key, mac_key = _keys()
    version, _, body = token.encode().partition(b":")
    raw = base64.urlsafe_b64decode(body)
    nonce, cipher, tag = raw[:16], raw[16:-32], raw[-32:]
    expected = hmac.new(mac_key, version + nonce + cipher, hashlib.sha256).digest()
    if version != _VERSION or not hmac.compare_digest(tag, expected):
        raise ValueError("收款账号密文校验失败")
    return bytes(a ^ b for a, b in zip(cipher, _keystream(enc_key, nonce, len(cipher)))).decode()


def mask_account_no(plain: str) -> str:
    digits = plain.replace(" ", "")
    if len(digits) <= 8:
        return "*" * max(len(digits) - 2, 0) + digits[-2:]
    return f"{digits[:4]}{'*' * (len(digits) - 8)}{digits[-4:]}"
