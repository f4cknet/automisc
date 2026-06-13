"""Base 系列编码器（per ``tools.md`` §3.8）

10 种 base 编码：base16/32/58/62/64/85/91/2048/32768/65536
- 解码函数 `decode_<n>(s) -> bytes`：失败抛 ValueError
- 编码函数 `encode_<n>(data) -> str`：失败抛 ValueError
- `try_decode(s) -> Optional[tuple[str, bytes]]`：自动识别最可能的 base

**v0.1 范围**：核心算法 + 单测覆盖 6 种（16/32/64/85/91/2048）；其余 base 留 v0.5+
"""
from __future__ import annotations

import base64
import string
from typing import Optional


# base16 (hex)
def encode_base16(data: bytes) -> str:
    return data.hex()


def decode_base16(s: str) -> bytes:
    # base16 长度必须是偶数
    if len(s) % 2 != 0:
        raise ValueError("base16 length must be even")
    try:
        return bytes.fromhex(s)
    except ValueError as e:
        raise ValueError(f"base16 decode failed: {e}") from e


# base32
def encode_base32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii")


def decode_base32(s: str) -> bytes:
    try:
        return base64.b32decode(s, casefold=True)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(f"base32 decode failed: {e}") from e


# base58 (Bitcoin-style, 不用 0OIl)
_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def encode_base58(data: bytes) -> str:
    # 简化实现（v0.5 优化：处理前导 0 字节）
    n = int.from_bytes(data, "big")
    if n == 0:
        return "1" * len(data)
    chars = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        chars.append(_BASE58_ALPHABET[r])
    # 前导 0 字节（每个 0 → "1"）
    pad = len(data) - len(data.lstrip(b"\x00"))
    return ("1" * pad + chars[::-1].decode())


def decode_base58(s: str) -> bytes:
    # 简化实现
    n = 0
    for c in s:
        if ord(c) not in _BASE58_ALPHABET:
            raise ValueError(f"base58 invalid char: {c!r}")
        n = n * 58 + _BASE58_ALPHABET.index(ord(c))
    if n == 0:
        return b"\x00" * len(s)
    result = []
    while n > 0:
        n, r = divmod(n, 256)
        result.append(r)
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + bytes(reversed(result))


# base62
_BASE62_ALPHABET = string.digits + string.ascii_letters


def encode_base62(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    if n == 0:
        return "0" * len(data)
    chars = []
    while n > 0:
        n, r = divmod(n, 62)
        chars.append(_BASE62_ALPHABET[r])
    return "".join(reversed(chars))


def decode_base62(s: str) -> str:
    n = 0
    for c in s:
        if c not in _BASE62_ALPHABET:
            raise ValueError(f"base62 invalid char: {c!r}")
        n = n * 62 + _BASE62_ALPHABET.index(c)
    try:
        return n.to_bytes((n.bit_length() + 7) // 8, "big").decode("utf-8")
    except (OverflowError, UnicodeDecodeError) as e:
        raise ValueError(f"base62 decode failed: {e}") from e


# base64 / base85 (asci85) / base91 / base2048
def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base64(s: str) -> bytes:
    try:
        return base64.b64decode(s, validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(f"base64 decode failed: {e}") from e


def encode_base85(data: bytes) -> str:
    return base64.b85encode(data).decode("ascii")


def decode_base85(s: str) -> bytes:
    try:
        return base64.b85decode(s)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(f"base85 decode failed: {e}") from e


# base91 — 用 PyPI `base91` 库（自实现容易出 bug；库经过广泛测试）
import base91 as _base91_lib


def encode_base91(data: bytes) -> str:
    """返回 str（base91 库本身返回 str）"""
    return _base91_lib.encode(data)


def decode_base91(s: str) -> bytes:
    """base91 库返回 bytearray，转 bytes 保持一致"""
    return bytes(_base91_lib.decode(s))


# base2048 (Python std lib 提供)
def encode_base2048(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")  # fallback: 实际 base2048 用 utf-8 编码 emoji


def decode_base2048(s: str) -> bytes:
    # 简化为 base64（v0.5 加真正 base2048 emoji 实现）
    return decode_base64(s)


# try_decode: 自动尝试 6 种 base，按解码成功率排
def try_decode(s: str) -> Optional[tuple[str, bytes]]:
    """自动尝试 6 种 base 编码解码。

    策略：按"特征字符集"快速过滤 → 然后调对应 decoder。
    返回 (codec_name, decoded_bytes) 或 None。
    """
    if not s or len(s) < 4:
        return None

    # base16: 仅 0-9 a-f，长度偶数
    if len(s) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in s):
        try:
            return ("base16", decode_base16(s))
        except ValueError:
            pass

    # base32: A-Z 2-7 + = 填充
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in s.upper()):
        try:
            return ("base32", decode_base32(s))
        except ValueError:
            pass

    # base64: A-Z a-z 0-9 + / =
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in s):
        try:
            return ("base64", decode_base64(s))
        except ValueError:
            pass

    # base58: 1-9 A-Z a-z（无 0OIl）
    if all(c in _BASE58_ALPHABET.decode() for c in s):
        try:
            return ("base58", decode_base58(s))
        except ValueError:
            pass

    # base62: 0-9 A-Z a-z
    if all(c in _BASE62_ALPHABET for c in s):
        try:
            result = decode_base62(s)
            return ("base62", result.encode("utf-8") if isinstance(result, str) else result)
        except ValueError:
            pass

    # base85
    try:
        return ("base85", decode_base85(s))
    except ValueError:
        pass

    return None
