"""测试 core/encoders/base64_stego.py（per v0.5-base-rot-decoders PR2）

覆盖:
- decode_base64_stego 基本功能
- encode_base64_stego + decode round-trip
- detect_capacity
- extract_hidden_with_size_hint
- 真实样本 (手工构造)
"""
from __future__ import annotations

import base64

import pytest

from automisc.core.encoders.base64_stego import (
    decode_base64_stego,
    encode_base64_stego,
    detect_capacity,
    extract_hidden_with_size_hint,
)


# === decode 基本 ===

def test_decode_empty():
    assert decode_base64_stego("") == b""
    assert decode_base64_stego("===") == b""


def test_decode_too_short():
    """< 4 chars 提取出 0 字节"""
    assert decode_base64_stego("ABC") == b""


def test_decode_extracts_hidden_bits():
    """'YWJj' 标准 base64 = 'abc'
    每个字符末 2 bit: Y=00, W=10, J=01, j=11
    拼成字节: 00100111 = 0x27 = "'"
    """
    # 'YWJj' 末 2 bit: 0 2 1 3 → byte = (0<<6)|(2<<4)|(1<<2)|3 = 0+32+4+3 = 39 = "'"
    assert decode_base64_stego("YWJj") == b"'"


def test_decode_strips_padding():
    """末尾 = 不参与提取"""
    # "YWJj=" 末尾有 '='，但 YWJj 末 2 bit 还是 00 10 01 11 → "'"
    assert decode_base64_stego("YWJj=") == b"'"
    assert decode_base64_stego("YWJj==") == b"'"


def test_decode_invalid_char_raises():
    """非 base64 字符抛 ValueError"""
    with pytest.raises(ValueError, match="invalid char"):
        decode_base64_stego("YWJ!")  # '!' 不在 B64_TABLE


# === encode/decode round-trip ===

def test_encode_decode_roundtrip():
    """encode + decode 回到原始 hidden（用 22 bytes 原文保证 capacity > 0）"""
    # 22 bytes → base64 30 chars stripped → capacity 7 bytes
    plain = "Hello, World! 12345"  # 19 chars not enough, use longer
    plain_bytes = plain.encode() + b"\x00" * (22 - len(plain))  # pad to 22 bytes
    assert len(plain_bytes) == 22
    plain_b64 = base64.b64encode(plain_bytes).decode("ascii")
    capacity = len(plain_b64.rstrip("=")) // 4
    assert capacity == 7
    hidden = b"X" * capacity  # 填满容量
    stego = encode_base64_stego(plain_b64, hidden)
    extracted = decode_base64_stego(stego)
    assert extracted == hidden


def test_encode_partial_capacity():
    """部分填充容量（用 hint_bytes 截断）"""
    plain_b64 = base64.b64encode(b"hello world 12345").decode("ascii")  # 16 bytes → capacity 5
    capacity = detect_capacity(plain_b64)
    assert capacity == 5
    hidden = b"OK"  # 2 bytes
    stego = encode_base64_stego(plain_b64, hidden)
    extracted = extract_hidden_with_size_hint(stego, hint_bytes=len(hidden))
    assert extracted == hidden


def test_encode_too_long_raises():
    """超出容量抛 ValueError"""
    plain_b64 = base64.b64encode(b"hello world 12345").decode("ascii")  # 16 bytes → capacity 5
    with pytest.raises(ValueError, match="too long"):
        encode_base64_stego(plain_b64, b"X" * 8)  # 8 > 5


# === detect_capacity ===

def test_detect_capacity_basic():
    assert detect_capacity("") == 0
    assert detect_capacity("ABCD") == 1  # 4 chars / 4 = 1
    assert detect_capacity("ABCDEFGH") == 2  # 8 chars / 4 = 2


def test_detect_capacity_with_padding():
    """末尾 = 不算容量"""
    # "ABCD=" stripped = "ABCD" → capacity 1
    assert detect_capacity("ABCD=") == 1
    # "AB==" stripped = "AB" → capacity 0
    assert detect_capacity("AB==") == 0


# === extract_hidden_with_size_hint ===

def test_extract_with_size_hint_truncates():
    """hint_bytes 截断结果"""
    plain_b64 = base64.b64encode(b"hello world 12345").decode("ascii")  # 16 bytes → capacity 5
    hidden = b"FLAG"  # 4 bytes
    stego = encode_base64_stego(plain_b64, hidden)
    # 取前 2 bytes
    extracted = extract_hidden_with_size_hint(stego, hint_bytes=2)
    assert extracted == b"FL"


def test_extract_no_hint_returns_all():
    """hint_bytes=None 时返回全部提取（含末尾垃圾）"""
    plain_b64 = base64.b64encode(b"hello world 12345").decode("ascii")
    hidden = b"FLAG"
    stego = encode_base64_stego(plain_b64, hidden)
    extracted = extract_hidden_with_size_hint(stego, hint_bytes=None)
    # 提取可能含末尾垃圾（last byte），所以 startswith 检查
    assert extracted.startswith(b"FLAG")


# === 真实样本：手工构造 flag 隐写 ===

def test_real_sample_flag_stego():
    """构造: 原文 22 bytes (= 7×3 + 1, 末尾 group 有冗余位) 隐藏 "secret"
    期望: decode 提取出 b"secret"

    ⚠️ 简化算法: 22 bytes → 30 chars stripped → capacity 7 bytes
       encode 时把 6 bytes hidden 拆 24 个 2-bit 塞到前 24 chars（前 7 group 末 2 bit 是真实数据位被改）
       decode 时取全部 30 chars → 7.5 bytes，前 6 bytes 是 hidden，第 7 bytes 是原数据末 2 bit 拼的垃圾
       准确提取需要 hint_bytes=6 截断
    """
    # 22 bytes (非 3 倍数) → b64encode 30 chars + "==" → stripped 30 → capacity 7
    original = b"AAAAAAAAAAAAAAAAAAAAAA"  # 22 a's
    assert len(original) == 22
    plain_b64 = base64.b64encode(original).decode("ascii")
    capacity = detect_capacity(plain_b64)
    assert capacity == 7

    hidden = b"secret"  # 6 bytes < 7 capacity
    stego = encode_base64_stego(plain_b64, hidden)
    # 提取前 6 bytes（hint_bytes 截断）
    extracted = extract_hidden_with_size_hint(stego, hint_bytes=len(hidden))
    assert extracted == hidden


def test_real_sample_base64_stego_fixture():
    """从 fixtures/sample_base64_stego.txt 读取手工构造的 stego base64，验证隐藏数据提取"""
    import pathlib
    # tests/unit/core/encoders/test_*.py → ../../../../fixtures/ (4 层向上)
    fixture_path = pathlib.Path(__file__).parent.parent.parent.parent / "fixtures" / "sample_base64_stego.txt"
    assert fixture_path.exists(), f"fixture missing: {fixture_path}"
    content = fixture_path.read_text().strip()
    # 文件最后一行是 stego base64 字符串
    stego_line = content.splitlines()[-1].strip()
    # 验证能从 fixture 提取出 b"secret"
    extracted = decode_base64_stego(stego_line)
    assert extracted.startswith(b"secret"), f"expected b'secret', got {extracted!r}"


def test_real_sample_base64_stego_extract_with_hint():
    """用 hint_bytes 截断到 6 bytes 准确提取"""
    import pathlib
    fixture_path = pathlib.Path(__file__).parent.parent.parent.parent / "fixtures" / "sample_base64_stego.txt"
    stego_line = fixture_path.read_text().strip().splitlines()[-1].strip()
    extracted = extract_hidden_with_size_hint(stego_line, hint_bytes=6)
    assert extracted == b"secret"
