"""单测: base_convert decoder (v0.5-bug-fix-2: 工具栏 16 进制转 ascii)

覆盖: detect_and_decode 4 种格式 + binary 优先级 + 错误路径
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from automisc.core.decoders.base_convert import (
    BaseConvertError,
    BaseConvertResult,
    convert_text_to_ascii,
    detect_and_decode,
)


# ---------- 4 种格式 ----------
class TestDetectAndDecode:
    def test_hex(self):
        # "Hello" = 48 65 6c 6c 6f
        fmt, decoded = detect_and_decode("48656c6c6f")
        assert fmt == "hex"
        assert decoded == "Hello"

    def test_binary(self):
        # "Hello" 5 字符 = 40 bits = 01001000 01100101 01101100 01101100 01101111
        fmt, decoded = detect_and_decode("0100100001100101011011000110110001101111")
        assert fmt == "binary"
        assert decoded == "Hello"

    def test_base64(self):
        fmt, decoded = detect_and_decode("aGVsbG8=")
        assert fmt == "base64"
        assert decoded == "hello"

    def test_base32(self):
        fmt, decoded = detect_and_decode("JBSWY3DPEB3W64TMMQ======")
        assert fmt == "base32"
        assert decoded == "Hello world"

    def test_binary_priority_over_hex(self):
        """binary 字符集 (0/1) 是 hex 子集, 必须先检 binary 避免 0101.. 串被判 hex"""
        # 纯 binary 串 (40 bits) - 长度是偶数也能过 hex 规则
        fmt, decoded = detect_and_decode("0100100001100101011011000110110001101111")
        assert fmt == "binary", f"应先判 binary, 实际: {fmt}"
        assert decoded == "Hello"

    def test_hex_priority_over_base64(self):
        """hex 字符集 (0-9a-f) 是 base64 子集, 必须先检 hex"""
        # 纯 hex 串
        fmt, decoded = detect_and_decode("deadbeefcafe1234567890abcdef")
        assert fmt == "hex"
        assert "Hi" in decoded or len(decoded) > 0

    def test_garbage_fails(self):
        with pytest.raises(BaseConvertError) as exc_info:
            detect_and_decode("not a base anything!!")
        assert "无法识别格式" in str(exc_info.value)

    def test_empty_fails(self):
        with pytest.raises(BaseConvertError) as exc_info:
            detect_and_decode("")
        assert "empty" in str(exc_info.value).lower()

    def test_strip_prefix(self):
        """常见前缀 0x / 0b / 0X 应被剥."""
        fmt, decoded = detect_and_decode("0x48656c6c6f")
        assert fmt == "hex"
        assert decoded == "Hello"

        fmt, decoded = detect_and_decode("0Xdeadbeef")
        assert fmt == "hex"

    def test_strip_whitespace_and_newlines(self):
        """跨行的 hex 串应被剥换行后能解."""
        fmt, decoded = detect_and_decode("48656c6c\n6f20576f726c64")
        assert fmt == "hex"
        assert "Hello" in decoded


# ---------- convert_text_to_ascii (主入口) ----------
class TestConvertTextToAscii:
    def test_success(self):
        r = convert_text_to_ascii("48656c6c6f")
        assert isinstance(r, BaseConvertResult)
        assert r.detected_format == "hex"
        assert r.output_text == "Hello"
        assert r.errors is None

    def test_garbage_returns_error_result(self):
        r = convert_text_to_ascii("not anything")
        assert r.detected_format == "unknown"
        assert r.output_text == ""
        assert r.errors is not None

    def test_meihuai_real_hex(self):
        """真实题 meihuai.jpg appended hex 前 12 chars (per owner 2026-06-14)."""
        # "(7,7)\n" 在 hex 0x28372c37290a 中
        fmt, decoded = detect_and_decode("28372c37290a")
        assert fmt == "hex"
        assert "(7,7)" in decoded


# ---------- 文件入口 (CLI 用的 runner) ----------
class TestRunner:
    def test_runner_with_file(self, tmp_path):
        """通过文件路径读 text 并转换."""
        from automisc.core.decoders.base_convert import _register  # 触发注册
        from automisc.core.decoders.registry import get_decoder

        spec = get_decoder("hex-ascii")
        assert spec is not None
        assert spec.name == "hex-ascii"
        assert spec.category == "convert"

        f = tmp_path / "hex.txt"
        f.write_text("48656c6c6f20576f726c64")
        r = spec.run(file_path=str(f))
        assert r.detected_format == "hex"
        assert r.output_text == "Hello World"
