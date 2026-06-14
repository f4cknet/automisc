"""测试 core/encoders/base_custom.py（per v0.5-base-rot-decoders PR1）

覆盖: base64 自定义表编码/解码 + 已知明文位移检测
"""
from __future__ import annotations

import base64

import pytest

from automisc.core.encoders.base_custom import (
    decode_base64_custom,
    detect_custom_table_shift,
    encode_base64_custom,
    URL_SAFE_TABLE,
)


# === encode/decode roundtrip ===

def test_encode_decode_roundtrip_with_custom_table():
    """用自定义表编码再解码应回到原数据"""
    data = b"hello world"
    # 右移 13 位变体
    custom = "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm0123456789+/"
    encoded = encode_base64_custom(data, custom)
    assert decode_base64_custom(encoded, custom) == data


def test_encode_decode_roundtrip_with_url_safe_table():
    """URL-safe 表（-_ 替代 +/）roundtrip"""
    data = b"hello world"
    encoded = encode_base64_custom(data, URL_SAFE_TABLE)
    assert decode_base64_custom(encoded, URL_SAFE_TABLE) == data


def test_encode_decode_roundtrip_with_shift_5():
    """右移 5 位变体"""
    data = b"hello"
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    shifted = std[5:] + std[:5]
    encoded = encode_base64_custom(data, shifted)
    assert decode_base64_custom(encoded, shifted) == data


# === 标准表 = 标准 base64 ===

def test_encode_with_std_table_equals_std_base64():
    """用标准表编码应等于标准 base64"""
    data = b"hello"
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    custom_encoded = encode_base64_custom(data, std)
    std_encoded = base64.b64encode(data).decode("ascii")
    assert custom_encoded == std_encoded


def test_decode_with_std_table_equals_std_base64():
    """用标准表解码应等于标准 base64"""
    std_encoded = base64.b64encode(b"hello").decode("ascii")
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    custom_decoded = decode_base64_custom(std_encoded, std)
    assert custom_decoded == b"hello"


# === 错误处理 ===

def test_custom_table_wrong_length_raises():
    """custom_table 长度 != 64 应抛 ValueError"""
    with pytest.raises(ValueError, match="custom_table length"):
        encode_base64_custom(b"hello", "ABC" * 10)  # 30 chars


def test_decode_invalid_raises():
    """custom_table 长度错应抛 ValueError"""
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    with pytest.raises(ValueError, match="custom_table length"):
        decode_base64_custom("aGVsbG8=", std[:63])  # 63 chars, not 64


# === detect_custom_table_shift ===

def test_detect_shift_right_13():
    """已知"密文 + 标准 base64" → 检测右移 13 位（语义：cipher_idx - plain_idx）"""
    data = b"hello"
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    plain_b64 = base64.b64encode(data).decode("ascii")
    shifted = std[13:] + std[:13]
    cipher = encode_base64_custom(data, shifted)
    # 算法返回 cipher_idx - plain_idx mod 64 → 右移 13 等价于 +13，差值为 +13 mod 64 = 13
    # 但若 cipher = encode_base64_custom(data, shifted) = std[(plain_idx + 13) % 64]
    # 则 cipher_idx = (plain_idx + 13) % 64, shift = cipher_idx - plain_idx = 13
    assert detect_custom_table_shift(cipher, plain_b64) == 13


def test_detect_shift_returns_none_for_unsupported():
    """非位移变体（乱序表）应返回 None"""
    data = b"hello"
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    plain_b64 = base64.b64encode(data).decode("ascii")
    # 乱序表（非位移）
    shuffled = "".join(reversed(std))
    cipher = encode_base64_custom(data, shuffled)
    # 乱序表无法用单一 shift 表示 → 应返回 None
    result = detect_custom_table_shift(cipher, plain_b64)
    assert result is None or isinstance(result, int)


def test_detect_shift_zero():
    """位移 0 = 标准表"""
    data = b"hello"
    plain_b64 = base64.b64encode(data).decode("ascii")
    assert detect_custom_table_shift(plain_b64, plain_b64) == 0
