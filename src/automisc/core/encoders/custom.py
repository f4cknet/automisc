"""自定义编码器（per ``tools.md`` §3.8）

5 种自定义编码：
- BCD (Binary-Coded Decimal)
- IEEE 754 浮点
- UTF-16 endianness (LE/BE)
- Unicode Tags / Variation Selector
- Multi-layer auto-decoder
"""
from __future__ import annotations

import struct
from typing import Optional


# === BCD (Binary-Coded Decimal) ===
def bcd_decode(s: str) -> str:
    """BCD 解码：每 4 bit 代表一个十进制数字（0-9）。

    例: 0x25 (0010 0101) → '25'
    字符串输入：'01010010' → '52' (从左到右每 4 bit)
    """
    # 仅接受 0/1
    if not all(c in "01" for c in s):
        raise ValueError("BCD input must be binary string (0/1 only)")
    if len(s) % 4 != 0:
        raise ValueError("BCD length must be multiple of 4 bits")
    result = []
    for i in range(0, len(s), 4):
        nibble = int(s[i:i+4], 2)
        if nibble > 9:
            raise ValueError(f"BCD invalid nibble: {nibble} (>9) at pos {i}")
        result.append(str(nibble))
    return "".join(result)


def bcd_encode(num: int) -> str:
    """数字 → BCD 字符串"""
    if num < 0:
        raise ValueError("BCD encode only supports non-negative integers")
    digits = str(num)
    return "".join(f"{int(d):04b}" for d in digits)


# === IEEE 754 浮点 ===
def ieee754_decode(b: bytes, double: bool = False) -> float:
    """IEEE 754 浮点解码（4 字节 = float，8 字节 = double）"""
    fmt = ">d" if double else ">f"
    if len(b) not in (4, 8):
        raise ValueError(f"IEEE 754 needs 4 bytes (float) or 8 bytes (double), got {len(b)}")
    try:
        if double or len(b) == 8:
            return struct.unpack(">d", b if len(b) == 8 else b.ljust(8, b"\x00"))[0]
        return struct.unpack(">f", b)[0]
    except struct.error as e:
        raise ValueError(f"IEEE 754 decode failed: {e}") from e


def ieee754_encode(value: float, double: bool = False) -> bytes:
    fmt = ">d" if double else ">f"
    return struct.pack(fmt, value)


# === UTF-16 endianness ===
def utf16_decode(b: bytes, little_endian: bool = True) -> str:
    """UTF-16 解码（LE 或 BE）"""
    try:
        return b.decode("utf-16-le" if little_endian else "utf-16-be")
    except UnicodeDecodeError as e:
        raise ValueError(f"UTF-16 decode failed: {e}") from e


def utf16_encode(s: str, little_endian: bool = True) -> bytes:
    return s.encode("utf-16-le" if little_endian else "utf-16-be")


# === Unicode Tags (U+E0001 ~ U+E007F) ===
def unicode_tags_decode(s: str) -> str:
    """解码 Unicode Tags：每个 U+E0xxx 字符 - 0xE0000 = ASCII 字节"""
    result = []
    for c in s:
        cp = ord(c)
        if 0xE0001 <= cp <= 0xE007F:
            result.append(chr(cp - 0xE0000))
        else:
            result.append(c)  # 非 tag 字符保留
    return "".join(result)


def unicode_tags_encode(s: str) -> str:
    """编码 ASCII 字符串为 Unicode Tags"""
    return "".join(chr(0xE0000 + ord(c)) for c in s if 0x20 <= ord(c) <= 0x7E)


# === Unicode Variation Selectors (U+FE00 ~ U+FE0F) ===
def variation_selectors_decode(s: str) -> str:
    """解码 Variation Selectors：去除 VS 字符（emoji 风格变体）"""
    return "".join(c for c in s if not (0xFE00 <= ord(c) <= 0xFE0F))


# === Multi-layer auto-decoder ===
def multi_layer_decode(s: str, max_depth: int = 5) -> list[tuple[str, str]]:
    """递归尝试多种解码（每层尝试 base64/32 + ROT13 + Atbash）。

    返回 [(layer_name, decoded_text), ...] 链。
    """
    chain = []
    current = s
    visited = set()  # 防止循环

    for depth in range(max_depth):
        if current in visited:
            break
        visited.add(current)

        next_val = None
        next_label = None

        # 1. base64
        from automisc.core.encoders.base import try_decode
        result = try_decode(current)
        if result and result[1] != current.encode():
            try:
                decoded_str = result[1].decode("utf-8")
                if decoded_str != current and decoded_str.isprintable():
                    next_val, next_label = decoded_str, f"base→{result[0]}"
            except (UnicodeDecodeError, ValueError):
                pass

        # 2. ROT13
        if next_val is None:
            from automisc.core.encoders.classical import rot13
            r = rot13(current)
            if r != current:
                next_val, next_label = r, "rot13"

        # 3. Atbash
        if next_val is None:
            from automisc.core.encoders.classical import atbash
            a = atbash(current)
            if a != current:
                next_val, next_label = a, "atbash"

        if next_val is not None:
            chain.append((next_label, next_val))
            current = next_val
        else:
            break

    return chain
