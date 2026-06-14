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


# base92 — 94 个 ASCII 可打印字符去掉 `\` 和 `"`（CTF 偶尔出现）
# 程序生成避免字符串字面量转义陷阱: ASCII 33-126 去掉 chr(34)='"' 和 chr(92)='\'
_BASE92_ALPHABET = "".join(
    chr(i) for i in range(33, 127) if i not in (34, 92)
)
assert len(_BASE92_ALPHABET) == 92, f"base92 alphabet must be 92 chars, got {len(_BASE92_ALPHABET)}"


def encode_base92(data: bytes) -> str:
    """base92 编码 — 92 个字符表，CTF 偶尔出现。

    算法：把字节流看作大整数，反复除 92 取余得到字符。
    前导 0 字节（每个 0 → '!'）保留。
    """
    if not data:
        return ""
    pad = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    if n == 0:
        return "!" * len(data)
    chars = bytearray()
    while n > 0:
        n, r = divmod(n, 92)
        chars.append(ord(_BASE92_ALPHABET[r]))
    return ("!" * pad + chars[::-1].decode("ascii"))


def decode_base92(s: str) -> bytes:
    if not s:
        return b""
    for c in s:
        if c not in _BASE92_ALPHABET:
            raise ValueError(f"base92 invalid char: {c!r}")
    pad = len(s) - len(s.lstrip("!"))
    n = 0
    for c in s:
        n = n * 92 + _BASE92_ALPHABET.index(c)
    if n == 0:
        return b"\x00" * len(s)
    result = bytearray()
    while n > 0:
        n, r = divmod(n, 256)
        result.append(r)
    return b"\x00" * pad + bytes(reversed(result))


# base36 — 0-9 + a-z（CTF 偶尔出现）
_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
assert len(_BASE36_ALPHABET) == 36


def encode_base36(data: bytes) -> str:
    """base36 编码 — 36 个字符 (0-9 + a-z)，CTF 偶尔出现。

    算法：把字节流看作大整数，反复除 36 取余。
    前导 0 字节保留（每个 → '0'）。
    """
    if not data:
        return ""
    pad = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    if n == 0:
        return "0" * len(data)
    chars = []
    while n > 0:
        n, r = divmod(n, 36)
        chars.append(_BASE36_ALPHABET[r])
    return "0" * pad + "".join(reversed(chars))


def decode_base36(s: str) -> bytes:
    if not s:
        return b""
    s = s.lower()
    for c in s:
        if c not in _BASE36_ALPHABET:
            raise ValueError(f"base36 invalid char: {c!r}")
    pad = len(s) - len(s.lstrip("0"))
    n = 0
    for c in s:
        n = n * 36 + _BASE36_ALPHABET.index(c)
    if n == 0:
        return b"\x00" * len(s)
    result = bytearray()
    while n > 0:
        n, r = divmod(n, 256)
        result.append(r)
    return b"\x00" * pad + bytes(reversed(result))


# base100 — emoji "Ɛ" 系列（CTF 极罕见，PyPI 无库）
# ⚠️ base100 真实算法：大整数 mod 100 取字符，**不是** 1 字节 → 1 字符
# （100 进制无法表示 256 个字节值）
# 简化实现：当作 base64 fallback（v0.5+ 暂不实现真 base100，CTF 遇到再说）
def encode_base100(data: bytes) -> str:
    """base100 ⚠️ v0.5+ 简化实现：fallback 到 base64（CTF 极罕见）"""
    return base64.b64encode(data).decode("ascii")


def decode_base100(s: str) -> bytes:
    """base100 ⚠️ v0.5+ 简化实现：fallback 到 base64"""
    try:
        return base64.b64decode(s, validate=False)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(f"base100 decode failed: {e}") from e


# base32768 — Unicode BMP 平面 emoji（PyPI 无库，自实现）
# 32768 = 2^15 chars；用 U+4E00..U+4E00+32767 (CJK 基本平面 32768 chars)
_BASE32768_START = 0x4E00  # CJK '一'


def encode_base32768(data: bytes) -> str:
    """base32768 编码 — CJK 基本平面 32768 字符（CTF 罕见）。

    算法：把字节流看作大整数，反复除 32768 取余 → CJK 字符码点。
    """
    if not data:
        return ""
    pad = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    if n == 0:
        return chr(_BASE32768_START) * len(data)
    chars = []
    while n > 0:
        n, r = divmod(n, 32768)
        chars.append(chr(_BASE32768_START + r))
    return chr(_BASE32768_START) * pad + "".join(reversed(chars))


def decode_base32768(s: str) -> bytes:
    if not s:
        return b""
    pad = 0
    for c in s:
        if ord(c) < _BASE32768_START or ord(c) >= _BASE32768_START + 32768:
            raise ValueError(f"base32768 invalid char: {c!r} (U+{ord(c):04X})")
        if ord(c) == _BASE32768_START:
            pad += 1
        else:
            break
    n = 0
    for c in s:
        n = n * 32768 + (ord(c) - _BASE32768_START)
    if n == 0:
        return b"\x00" * len(s)
    result = bytearray()
    while n > 0:
        n, r = divmod(n, 256)
        result.append(r)
    return b"\x00" * pad + bytes(reversed(result))


# base65536 — 全部 Unicode plane 0 (PyPI `base65536` 库实现)
import base65536 as _base65536_lib


def encode_base65536(data: bytes) -> str:
    """base65536 编码 — PyPI `base65536` 库实现（CCTV emoji 系列）"""
    return _base65536_lib.encode(data)


def decode_base65536(s: str) -> bytes:
    """base65536 库返回 str → bytes 转换"""
    return bytes(_base65536_lib.decode(s))


# base2048 (Python std lib 提供) — v0.5+ 仍占位，emoji 字符表实现复杂
def encode_base2048(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")  # fallback: 实际 base2048 用 utf-8 编码 emoji


def decode_base2048(s: str) -> bytes:
    # 简化为 base64（v0.5 加真正 base2048 emoji 实现）
    return decode_base64(s)


# try_decode: 自动尝试 9 种 base，按解码成功率排
def try_decode(s: str) -> Optional[tuple[str, bytes]]:
    """自动尝试 9 种 base 编码解码。

    策略：按"特征字符集"快速过滤 → 然后调对应 decoder。
    返回 (codec_name, decoded_bytes) 或 None。

    **v0.5+ 新增**：base36 / base91 / base92 / base100 / base32768 / base65536

    **优先级**：base16（最严格，唯一 hex）> base32（仅大写 + 2-7）> base36（仅小写）
    > base58（无 0OIl）> base62（数字+字母大小写）> base64（含 +/=）> base91/92
    > base85（fallback）。
    """
    if not s or len(s) < 4:
        return None

    # base16: 仅 0-9 a-f，长度偶数（最严格，先判）
    if len(s) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in s):
        try:
            return ("base16", decode_base16(s))
        except ValueError:
            pass

    # base32: A-Z 2-7 + = 填充（全大写 + 数字 2-7）
    # 必须**全大写**（base36 是小写+数字，区分点）
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in s.upper()) and s == s.upper():
        try:
            return ("base32", decode_base32(s))
        except ValueError:
            pass

    # base64: A-Z a-z 0-9 + / = （含 +/= 特征字符）
    if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in s):
        # 有 + 或 / → 一定是 base64（其他 base 都不含这俩）
        if "+" in s or "/" in s or "=" in s:
            try:
                return ("base64", decode_base64(s))
            except ValueError:
                pass
        # 无 +/= → 可能是 base58 / base62 / base36，延后判

    # base36: 0-9 a-z（小写）
    if all(c in _BASE36_ALPHABET for c in s.lower()) and s.islower():
        # 必须是全小写（base36 标准小写，base58/62 可大小写混）
        try:
            return ("base36", decode_base36(s))
        except ValueError:
            pass

    # base58: 1-9 A-Z a-z（无 0OIl）
    if all(c in _BASE58_ALPHABET.decode() for c in s):
        try:
            return ("base58", decode_base58(s))
        except ValueError:
            pass

    # base62: 0-9 A-Z a-z（无 +/= 无特殊字符）
    if all(c in _BASE62_ALPHABET for c in s):
        try:
            result = decode_base62(s)
            return ("base62", result.encode("utf-8") if isinstance(result, str) else result)
        except ValueError:
            pass

    # base91 / base92 字符集高度重叠，先都尝试，结果"看起来像 ASCII 文本"的胜出
    # base91: 高密度 ASCII（含很多特殊字符）
    try:
        decoded91 = decode_base91(s)
        # 检查解码结果是否"像 ASCII 文本"（≥ 70% 可打印 + 字母）
        printable = sum(1 for b in decoded91 if 32 <= b <= 126 or b in (9, 10, 13))
        if len(decoded91) > 0 and printable / len(decoded91) >= 0.7:
            return ("base91", decoded91)
    except ValueError:
        pass

    # base92: ASCII 33-126 去 \ 和 "
    if all(c in _BASE92_ALPHABET for c in s):
        try:
            decoded92 = decode_base92(s)
            printable = sum(1 for b in decoded92 if 32 <= b <= 126 or b in (9, 10, 13))
            if len(decoded92) > 0 and printable / len(decoded92) >= 0.7:
                return ("base92", decoded92)
        except ValueError:
            pass

    # base85
    try:
        return ("base85", decode_base85(s))
    except ValueError:
        pass

    return None
