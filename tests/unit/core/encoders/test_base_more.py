"""测试 core/encoders/base.py 新增算法（per v0.5-base-rot-decoders PR1）

覆盖: base36 / base92 / base100 / base32768 / base65536 + try_decode 扩展
"""
from __future__ import annotations

import pytest

from automisc.core.encoders.base import (
    decode_base36,
    decode_base91,
    decode_base92,
    decode_base100,
    decode_base32768,
    decode_base65536,
    encode_base36,
    encode_base91,
    encode_base92,
    encode_base100,
    encode_base32768,
    encode_base65536,
    try_decode,
)


# === base36 ===

def test_base36_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base36(data)
    assert decode_base36(encoded) == data


def test_base36_encode_decode_with_leading_zeros():
    """前导 0 字节保留"""
    data = b"\x00\x00hello"
    encoded = encode_base36(data)
    # 开头应有 2 个 '0'
    assert encoded.startswith("00")
    assert decode_base36(encoded) == data


def test_base36_decode_invalid_raises():
    with pytest.raises(ValueError, match="base36 invalid char"):
        decode_base36("!")  # '!' 不在 0-9 a-z 字符集


def test_base36_known_value():
    """base36 '10' = 36 (十进制) = 0x24 = '$'"""
    assert decode_base36("10") == b"$"


def test_base36_empty():
    assert encode_base36(b"") == ""
    assert decode_base36("") == b""


# === base92 ===

def test_base92_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base92(data)
    assert decode_base92(encoded) == data


def test_base92_encode_decode_with_leading_zeros():
    data = b"\x00\x00hello"
    encoded = encode_base92(data)
    assert encoded.startswith("!!")
    assert decode_base92(encoded) == data


def test_base92_decode_invalid_raises():
    with pytest.raises(ValueError, match="base92 invalid char"):
        # 双引号不在 base92 字符集（ASCII 34 被排除）
        decode_base92('"')


def test_base92_empty():
    assert encode_base92(b"") == ""
    assert decode_base92("") == b""


# === base100 ===

def test_base100_encode_decode_roundtrip():
    """base100 v0.5+ 是 fallback 实现（base64），roundtrip 应仍工作"""
    data = b"hello"
    encoded = encode_base100(data)
    assert decode_base100(encoded) == data


def test_base100_empty():
    assert encode_base100(b"") == ""
    assert decode_base100("") == b""


# === base32768 ===

def test_base32768_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base32768(data)
    assert decode_base32768(encoded) == data


def test_base32768_encode_decode_with_leading_zeros():
    data = b"\x00\x00hello"
    encoded = encode_base32768(data)
    # 前导 0 字节 → '一' (U+4E00)
    assert encoded.startswith("一一")
    assert decode_base32768(encoded) == data


def test_base32768_decode_invalid_raises():
    """ASCII 不在 base32768 字符集"""
    with pytest.raises(ValueError, match="base32768 invalid char"):
        decode_base32768("a")  # 'a' = U+0061 < U+4E00


def test_base32768_empty():
    assert encode_base32768(b"") == ""
    assert decode_base32768("") == b""


# === base65536 ===

def test_base65536_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base65536(data)
    assert decode_base65536(encoded) == data


def test_base65536_empty():
    assert encode_base65536(b"") == ""
    assert decode_base65536("") == b""


# === try_decode 扩展（v0.5+ 新增 base36/91/92 判定）===

def test_try_decode_base36():
    """base36 字符串应被 try_decode 识别为 base36"""
    encoded = encode_base36(b"hello")
    result = try_decode(encoded)
    assert result is not None
    assert result[0] == "base36"
    assert result[1] == b"hello"


def test_try_decode_base91():
    """base91 字符串应被 try_decode 识别为 base91"""
    encoded = encode_base91(b"hello")
    result = try_decode(encoded)
    assert result is not None
    assert result[0] == "base91"
    assert result[1] == b"hello"


def test_try_decode_base92():
    """base92 字符串应被 try_decode 识别为 base92"""
    encoded = encode_base92(b"hello")
    result = try_decode(encoded)
    assert result is not None
    assert result[0] == "base92"
    assert result[1] == b"hello"


def test_try_decode_existing_base16_still_works():
    """回归：try_decode 仍识别 base16"""
    result = try_decode("68656c6c6f")
    assert result is not None
    assert result[0] == "base16"
    assert result[1] == b"hello"


def test_try_decode_short_string_returns_none():
    """< 4 字符返回 None"""
    assert try_decode("ab") is None
    assert try_decode("") is None
