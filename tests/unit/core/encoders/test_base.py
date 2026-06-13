"""测试 core/encoders/base.py"""
from __future__ import annotations

import pytest

from automisc.core.encoders.base import (
    decode_base16,
    decode_base32,
    decode_base58,
    decode_base62,
    decode_base64,
    decode_base85,
    decode_base91,
    encode_base16,
    encode_base32,
    encode_base58,
    encode_base62,
    encode_base64,
    encode_base85,
    encode_base91,
    try_decode,
)


# === base16 ===

def test_base16_encode_decode_roundtrip():
    data = b"hello world"
    encoded = encode_base16(data)
    assert encoded == "68656c6c6f20776f726c64"
    assert decode_base16(encoded) == data


def test_base16_decode_odd_length_raises():
    with pytest.raises(ValueError, match="even"):
        decode_base16("abc")


def test_base16_decode_invalid_raises():
    with pytest.raises(ValueError):
        decode_base16("xyz")  # 非 hex


# === base32 ===

def test_base32_encode_decode_roundtrip():
    data = b"hello world!!"
    encoded = encode_base32(data)
    assert decode_base32(encoded) == data


def test_base32_decode_invalid_raises():
    with pytest.raises(ValueError):
        decode_base32("12345")  # 含 '1'（base32 不用）


# === base58 ===

def test_base58_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base58(data)
    assert decode_base58(encoded) == data


def test_base58_excludes_0OIl():
    """base58 不含 0 / O / I / l"""
    data = b"abcdefghijklmnopqrstuvwxyz0123456789"
    encoded = encode_base58(data)
    for excluded in "0OIl":
        assert excluded not in encoded


# === base62 ===

def test_base62_encode_decode_roundtrip():
    data = "Hello, World!"
    encoded = encode_base62(data.encode())
    decoded = decode_base62(encoded)
    assert decoded == data


# === base64 ===

def test_base64_encode_decode_roundtrip():
    data = b"hello\x00world"
    encoded = encode_base64(data)
    assert decode_base64(encoded) == data


def test_base64_decode_invalid_raises():
    with pytest.raises(ValueError):
        decode_base64("!!!!")  # 非法 base64 char


# === base85 ===

def test_base85_encode_decode_roundtrip():
    data = b"hello world"
    encoded = encode_base85(data)
    assert decode_base85(encoded) == data


# === base91 ===

def test_base91_encode_decode_roundtrip():
    data = b"hello"
    encoded = encode_base91(data)
    decoded = decode_base91(encoded)
    assert decoded == data


# === try_decode (auto) ===

def test_try_decode_base16():
    result = try_decode("48656c6c6f")  # base16 of "Hello"
    assert result is not None
    assert result[0] == "base16"
    assert result[1] == b"Hello"


def test_try_decode_base64():
    result = try_decode("aGVsbG8=")  # base64 of "hello"
    assert result is not None
    assert result[0] == "base64"
    assert result[1] == b"hello"


def test_try_decode_returns_none_for_invalid():
    assert try_decode("!!!") is None
    assert try_decode("") is None
    assert try_decode("ab") is None  # 太短
