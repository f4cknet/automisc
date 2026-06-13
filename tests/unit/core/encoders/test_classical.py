"""测试 core/encoders/classical.py"""
from __future__ import annotations

import pytest

from automisc.core.encoders.classical import (
    affine_decrypt,
    affine_encrypt,
    atbash,
    auto_try_caesar,
    caesar_decrypt,
    caesar_encrypt,
    pigpen_decrypt,
    pigpen_encrypt,
    rail_fence_decrypt,
    rail_fence_encrypt,
    rot13,
    rot_n,
    vigenere_decrypt,
    vigenere_encrypt,
)


# === ROT13 ===

def test_rot13_basic():
    assert rot13("Hello") == "Uryyb"


def test_rot13_roundtrip():
    """ROT13 两次回到原文"""
    s = "Hello, World!"
    assert rot13(rot13(s)) == s


def test_rot13_preserves_non_alpha():
    assert rot13("Hello 123!") == "Uryyb 123!"


# === ROT-N ===

def test_rot_n():
    assert rot_n("ABC", 1) == "BCD"
    assert rot_n("ABC", 25) == "ZAB"


# === Caesar ===

def test_caesar_decrypt():
    """shift=3: D→A, E→B, F→C"""
    assert caesar_decrypt("DEF", 3) == "ABC"


def test_caesar_encrypt_decrypt_roundtrip():
    s = "Hello, World!"
    encrypted = caesar_encrypt(s, 7)
    assert caesar_decrypt(encrypted, 7) == s


# === Vigenère ===

def test_vigenere_decrypt_basic():
    """key="KEY" 解密 'RIJVS' → 'HELLO'"""
    assert vigenere_decrypt("RIJVS", "KEY") == "HELLO"


def test_vigenere_encrypt_decrypt_roundtrip():
    s = "Attack at dawn"
    key = "LEMON"
    encrypted = vigenere_encrypt(s, key)
    assert vigenere_decrypt(encrypted, key) == s


def test_vigenere_empty_key_raises():
    with pytest.raises(ValueError, match="empty"):
        vigenere_decrypt("HELLO", "")


# === Atbash ===

def test_atbash():
    """A↔Z, B↔Y"""
    assert atbash("ABC") == "ZYX"
    assert atbash("HELLO") == "SVOOL"


# === Affine ===

def test_affine_roundtrip():
    s = "HELLO"
    encrypted = affine_encrypt(s, 5, 8)
    assert affine_decrypt(encrypted, 5, 8) == s


def test_affine_non_coprime_raises():
    with pytest.raises(ValueError, match="coprime"):
        affine_decrypt("HELLO", 13, 5)  # 13 和 26 不互质


# === Pigpen ===

def test_pigpen_encrypt_decrypt_roundtrip():
    s = "hello"
    encoded = pigpen_encrypt(s)
    assert pigpen_decrypt(encoded) == s


# === Rail Fence ===

def test_rail_fence_encrypt_basic():
    """3 rails: 'WEAREDISCOVEREDFLEEATONCE' → 'WECRLTEERDSOEEFEAOCAIVDEN'"""
    s = "WEAREDISCOVEREDFLEEATONCE"
    encrypted = rail_fence_encrypt(s, 3)
    assert encrypted == "WECRLTEERDSOEEFEAOCAIVDEN"


def test_rail_fence_decrypt_basic():
    s = "WEAREDISCOVEREDFLEEATONCE"
    encrypted = rail_fence_encrypt(s, 3)
    assert rail_fence_decrypt(encrypted, 3) == s


def test_rail_fence_too_few_rails_raises():
    with pytest.raises(ValueError):
        rail_fence_encrypt("abc", 1)


# === auto_try_caesar ===

def test_auto_try_caesar_finds_shift():
    """'WKH TXLFN EUXW LV QRPRFWHG' 应识别为 shift=3 Caesar"""
    s = "WKH TXLFN EUXW LV QRPRFWHG"  # "THE QUICK BROWN IS PROTECTED" with shift=3
    result = auto_try_caesar(s)
    assert result is not None
    shift, decoded = result
    assert shift == 3


def test_auto_try_caesar_returns_none_for_random():
    assert auto_try_caesar("XQFZP JMVD") is None
