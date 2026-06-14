"""测试 core/decoders/base_rot_decoders.py（per v0.5-base-rot-decoders PR3）

覆盖:
- 18 个 decoder 都正确注册
- 每个 base runner 都能解码
- 每个 rot runner 都能解码
- base64-stego runner 解码
- base64-custom runner 拒绝非法表
- DecodeResult dataclass
"""
from __future__ import annotations

import pytest

from automisc.core.decoders import REGISTRY, base_rot_decoders
from automisc.core.decoders.base_rot_decoders import (
    DecodeResult,
    run_base64_custom,
    run_base64_stego,
)


# === 注册检查 ===

EXPECTED_DECODERS = [
    # Base 系列
    "base16", "base32", "base36", "base58", "base62", "base64",
    "base85", "base91", "base92", "base100", "base32768", "base65536",
    # ROT 系列
    "rot5", "rot13", "rot18", "rot47",
    # 特殊
    "base64-custom", "base64-stego",
]


def test_all_18_decoders_registered():
    """18 个 base_rot decoder 全部注册到 REGISTRY"""
    names = {spec.name for spec in REGISTRY}
    for name in EXPECTED_DECODERS:
        assert name in names, f"{name} not registered"


def test_all_decoders_have_base_rot_category():
    """所有 base_rot decoder 的 category = 'base_rot'"""
    for spec in REGISTRY:
        if spec.name in EXPECTED_DECODERS:
            assert spec.category == "base_rot", f"{spec.name} has category={spec.category}"


def test_all_decoders_have_run_callable():
    """所有 decoder 的 run 字段都是 callable"""
    for spec in REGISTRY:
        if spec.name in EXPECTED_DECODERS:
            assert callable(spec.run), f"{spec.name} run not callable"


# === Base runner ===

def test_base16_runner():
    r = base_rot_decoders._make_base_runner(
        "base16", base_rot_decoders.base_mod.decode_base16
    )(text="68656c6c6f")
    assert r.codec == "base16"
    assert r.output_text == "hello"
    assert r.error is None


def test_base32_runner():
    r = base_rot_decoders._make_base_runner(
        "base32", base_rot_decoders.base_mod.decode_base32
    )(text="NBSWY3DP")
    assert r.codec == "base32"
    assert r.output_text == "hello"
    assert r.error is None


def test_base64_runner():
    r = base_rot_decoders._make_base_runner(
        "base64", base_rot_decoders.base_mod.decode_base64
    )(text="aGVsbG8=")
    assert r.codec == "base64"
    assert r.output_text == "hello"


def test_base64_runner_invalid_returns_error():
    """解码失败不抛异常，返回 result.error"""
    r = base_rot_decoders._make_base_runner(
        "base64", base_rot_decoders.base_mod.decode_base64
    )(text="!!!")
    assert r.error is not None


def test_base_runner_requires_text_or_file():
    """既不传 text 也不传 file_path 抛 ValueError"""
    with pytest.raises(ValueError, match="text 或 file_path"):
        base_rot_decoders._make_base_runner(
            "base16", base_rot_decoders.base_mod.decode_base16
        )()


# === ROT runner ===

def test_rot5_runner():
    r = base_rot_decoders._make_rot_runner("rot5", base_rot_decoders.classical.rot5)(text="12345")
    assert r.codec == "rot5"
    assert r.output_text == "67890"


def test_rot13_runner():
    r = base_rot_decoders._make_rot_runner("rot13", base_rot_decoders.classical.rot13)(text="hello")
    assert r.codec == "rot13"
    assert r.output_text == "uryyb"


def test_rot18_runner():
    r = base_rot_decoders._make_rot_runner("rot18", base_rot_decoders.classical.rot18)(text="abc123")
    assert r.codec == "rot18"
    assert r.output_text == "nop678"


def test_rot47_runner():
    r = base_rot_decoders._make_rot_runner("rot47", base_rot_decoders.classical.rot47)(text="Hello")
    assert r.codec == "rot47"
    # ROT47 自反
    assert base_rot_decoders.classical.rot47(r.output_text) == "Hello"


# === base64-stego runner ===

def test_base64_stego_runner_no_hint():
    """无 hint_bytes 时返回全部提取（含可能末尾垃圾）"""
    r = run_base64_stego(text="RXEDRWFBRWEDRXECRWFBRXFAQUFBQQ==")
    assert r.codec == "base64-stego"
    assert r.output_text.startswith("secret")


def test_base64_stego_runner_with_hint():
    """有 hint_bytes 时精确截断"""
    r = run_base64_stego(text="RXEDRWFBRWEDRXECRWFBRXFAQUFBQQ==", hint_bytes=6)
    assert r.codec == "base64-stego"
    assert r.output_text == "secret"
    assert "截断" in r.hint


def test_base64_stego_runner_invalid():
    r = run_base64_stego(text="!!!")
    assert r.error is not None


# === base64-custom runner ===

def test_base64_custom_runner_with_valid_table():
    """合法 64 字符表能解"""
    std = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    custom = std[13:] + std[:13]  # 右移 13
    # 用 standard base64 编码 "hello"
    import base64
    plain_b64 = base64.b64encode(b"hello").decode("ascii")
    # 转成 custom 表编码
    trans = str.maketrans(std, custom)
    cipher = plain_b64.translate(trans)
    r = run_base64_custom(text=cipher, custom_table=custom)
    assert r.codec == "base64-custom"
    assert r.output_text == "hello"


def test_base64_custom_runner_missing_table_raises():
    """缺 custom_table 抛 ValueError"""
    with pytest.raises(ValueError, match="custom_table"):
        run_base64_custom(text="aGVsbG8=")


def test_base64_custom_runner_wrong_length_raises():
    """表长度错抛 ValueError"""
    with pytest.raises(ValueError, match="64"):
        run_base64_custom(text="aGVsbG8=", custom_table="ABC" * 10)  # 30 chars


# === DecodeResult ===

def test_decode_result_bool():
    """DecodeResult __bool__ = error is None"""
    r_ok = DecodeResult(codec="base16", input="abc", output_text="hello")
    assert bool(r_ok) is True
    r_err = DecodeResult(codec="base16", input="!!!", error="bad char")
    assert bool(r_err) is False
