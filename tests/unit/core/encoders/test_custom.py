"""测试 core/encoders/custom.py"""
from __future__ import annotations

import pytest

from automisc.core.encoders.custom import (
    bcd_decode,
    bcd_encode,
    ieee754_decode,
    ieee754_encode,
    multi_layer_decode,
    unicode_tags_decode,
    unicode_tags_encode,
    utf16_decode,
    utf16_encode,
    variation_selectors_decode,
)


# === BCD ===

def test_bcd_encode():
    assert bcd_encode(25) == "00100101"  # 2=0010 5=0101


def test_bcd_decode():
    assert bcd_decode("00100101") == "25"


def test_bcd_invalid_nibble_raises():
    with pytest.raises(ValueError, match="nibble"):
        bcd_decode("1111")  # 15 > 9


def test_bcd_non_binary_raises():
    with pytest.raises(ValueError, match="binary"):
        bcd_decode("xyz")


# === IEEE 754 ===

def test_ieee754_float_roundtrip():
    import struct
    original = 3.14159
    encoded = ieee754_encode(original)
    assert len(encoded) == 4
    assert ieee754_decode(encoded) == pytest.approx(original)


def test_ieee754_double_roundtrip():
    original = 3.141592653589793
    encoded = ieee754_encode(original, double=True)
    assert len(encoded) == 8
    assert ieee754_decode(encoded, double=True) == original


# === UTF-16 ===

def test_utf16_le_roundtrip():
    s = "Hello 世界"
    encoded = utf16_encode(s, little_endian=True)
    decoded = utf16_decode(encoded, little_endian=True)
    assert decoded == s


def test_utf16_be_roundtrip():
    s = "Hello"
    encoded = utf16_encode(s, little_endian=False)
    decoded = utf16_decode(encoded, little_endian=False)
    assert decoded == s


# === Unicode Tags ===

def test_unicode_tags_decode():
    """U+E0048 = 'H' (E0048 - E0000 = 0x48 = 'H')"""
    s = "\U000E0048\U000E0049"
    assert unicode_tags_decode(s) == "HI"


def test_unicode_tags_roundtrip():
    s = "FLAG"
    encoded = unicode_tags_encode(s)
    assert unicode_tags_decode(encoded) == "FLAG"


# === Variation Selectors ===

def test_variation_selectors_decode_removes_vs():
    """U+FE0F (emoji variation selector) 应被移除"""
    s = "Hello\uFE0F World"
    assert variation_selectors_decode(s) == "Hello World"


# === Multi-layer ===

def test_multi_layer_decode_single():
    """无嵌套 → 空链或单层"""
    result = multi_layer_decode("just plain text", max_depth=3)
    assert isinstance(result, list)


def test_multi_layer_decode_double_base64():
    """base64(base64("hello")) = 'aGVsbG8=' → decode → b'hello' → encode → 'aGVsbG8='"""
    from automisc.core.encoders.base import encode_base64
    inner = encode_base64(b"hello")  # "aGVsbG8="
    outer = encode_base64(inner.encode())  # base64 of base64 string
    result = multi_layer_decode(outer)
    # 应该至少 1 层 base64 解码成功
    assert len(result) >= 1
    assert result[0][0].startswith("base")
