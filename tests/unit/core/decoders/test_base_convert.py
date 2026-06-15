"""单测: base_convert decoder (v0.5-bug-fix-2: 工具栏 16 进制转 ascii)

覆盖:
- detect_and_decode 4 种格式 + binary 优先级 + 错误路径
- v0.5-more-converts (per Owner 22:17): 6 个新转换工具各 happy/edge case
- 6 个新工具的 registry 注册 + text_only=True
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest

from automisc.core.decoders import REGISTRY
from automisc.core.decoders.base_convert import (
    BaseConvertError,
    BaseConvertResult,
    convert_text_to_ascii,
    convert_bin_to_ascii,
    convert_dec_to_bin,
    convert_bin_to_dec,
    convert_dec_to_hex,
    convert_hex_to_dec,
    convert_ascii_to_bin,
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


# === v0.5-more-converts: 6 个新转换工具 (per Owner 22:17) ===

class TestMoreConverts:
    """v0.5-more-converts 6 个新工具: bin-ascii / dec-bin / bin-dec / dec-hex / hex-dec / ascii-bin."""

    # ----- bin-ascii -----
    def test_bin_ascii_basic(self):
        """bin-ascii: \"0100100001100101\" → \"He\""""
        r = convert_bin_to_ascii("0100100001100101")
        assert r.errors is None
        assert r.detected_format == "binary"
        assert r.output_text == "He"

    def test_bin_ascii_with_spaces(self):
        """bin-ascii: 8-bit 块用空格分隔 → \"Hi\""""
        r = convert_bin_to_ascii("01001000 01101001")
        assert r.errors is None
        assert r.output_text == "Hi"

    def test_bin_ascii_not_multiple_of_8(self):
        """bin-ascii: 长度非 8 倍数 → error"""
        r = convert_bin_to_ascii("01001000011001")
        assert r.errors is not None
        assert "multiple of 8" in r.errors

    def test_bin_ascii_invalid_chars(self):
        """bin-ascii: 含非 0/1 字符 → error"""
        r = convert_bin_to_ascii("0100100a")
        assert r.errors is not None
        assert "not binary" in r.errors

    def test_bin_ascii_empty(self):
        """bin-ascii: 空 → error"""
        r = convert_bin_to_ascii("")
        assert r.errors is not None
        assert "empty" in r.errors

    # ----- dec-bin -----
    def test_dec_bin_basic(self):
        """dec-bin: 65 → 1000001"""
        r = convert_dec_to_bin("65")
        assert r.errors is None
        assert r.output_text == "1000001"

    def test_dec_bin_255(self):
        """dec-bin: 255 → 11111111"""
        r = convert_dec_to_bin("255")
        assert r.errors is None
        assert r.output_text == "11111111"

    def test_dec_bin_multiple(self):
        """dec-bin: 多空格分隔 → 1000001 1000010"""
        r = convert_dec_to_bin("65 66")
        assert r.errors is None
        assert r.output_text == "1000001 1000010"

    def test_dec_bin_negative(self):
        """dec-bin: 负数 → error"""
        r = convert_dec_to_bin("-1")
        assert r.errors is not None
        assert "negative" in r.errors

    def test_dec_bin_not_int(self):
        """dec-bin: 非整数 → error"""
        r = convert_dec_to_bin("abc")
        assert r.errors is not None

    # ----- bin-dec -----
    def test_bin_dec_basic(self):
        """bin-dec: 1000001 → 65"""
        r = convert_bin_to_dec("1000001")
        assert r.errors is None
        assert r.output_text == "65"

    def test_bin_dec_11111111(self):
        """bin-dec: 11111111 → 255"""
        r = convert_bin_to_dec("11111111")
        assert r.errors is None
        assert r.output_text == "255"

    def test_bin_dec_multiple(self):
        """bin-dec: 多空格分隔 → 65 66"""
        r = convert_bin_to_dec("1000001 1000010")
        assert r.errors is None
        assert r.output_text == "65 66"

    def test_bin_dec_invalid(self):
        """bin-dec: 含非 0/1 → error"""
        r = convert_bin_to_dec("1000002")
        assert r.errors is not None
        assert "not binary" in r.errors

    # ----- dec-hex -----
    def test_dec_hex_basic(self):
        """dec-hex: 255 → ff"""
        r = convert_dec_to_hex("255")
        assert r.errors is None
        assert r.output_text == "ff"

    def test_dec_hex_deadbeef(self):
        """dec-hex: 3735928559 → deadbeef"""
        r = convert_dec_to_hex("3735928559")
        assert r.errors is None
        assert r.output_text == "deadbeef"

    def test_dec_hex_zero(self):
        """dec-hex: 0 → 0"""
        r = convert_dec_to_hex("0")
        assert r.errors is None
        assert r.output_text == "0"

    # ----- hex-dec -----
    def test_hex_dec_basic(self):
        """hex-dec: ff → 255"""
        r = convert_hex_to_dec("ff")
        assert r.errors is None
        assert r.output_text == "255"

    def test_hex_dec_uppercase(self):
        """hex-dec: DEADBEEF → 3735928559"""
        r = convert_hex_to_dec("DEADBEEF")
        assert r.errors is None
        assert r.output_text == "3735928559"

    def test_hex_dec_strips_0x(self):
        """hex-dec: 0xff → 255 (自动剥前缀)"""
        r = convert_hex_to_dec("0xff")
        assert r.errors is None
        assert r.output_text == "255"

    def test_hex_dec_invalid(self):
        """hex-dec: 非 hex 字符 → error"""
        r = convert_hex_to_dec("xyz")
        assert r.errors is not None

    # ----- ascii-bin -----
    def test_ascii_bin_basic(self):
        """ascii-bin: He → 01001000 01100101"""
        r = convert_ascii_to_bin("He")
        assert r.errors is None
        assert r.output_text == "01001000 01100101"

    def test_ascii_bin_single(self):
        """ascii-bin: A → 01000001"""
        r = convert_ascii_to_bin("A")
        assert r.errors is None
        assert r.output_text == "01000001"

    # ----- 互转 round-trip -----
    def test_round_trip_dec_bin_dec(self):
        """dec→bin→dec: 65 往返一致"""
        r1 = convert_dec_to_bin("65")
        assert r1.errors is None
        r2 = convert_bin_to_dec(r1.output_text)
        assert r2.output_text == "65"

    def test_round_trip_dec_hex_dec(self):
        """dec→hex→dec: 255 往返一致"""
        r1 = convert_dec_to_hex("255")
        r2 = convert_hex_to_dec(r1.output_text)
        assert r2.output_text == "255"

    def test_round_trip_ascii_bin_ascii(self):
        """ascii→bin→ascii: Hi 往返一致"""
        r1 = convert_ascii_to_bin("Hi")
        # 去掉空格
        bin_stripped = r1.output_text.replace(" ", "")
        r2 = convert_bin_to_ascii(bin_stripped)
        assert r2.output_text == "Hi"


# === v0.5-more-converts: registry 注册验证 ===

class TestMoreConvertsRegistry:
    def test_all_6_new_decoders_registered(self):
        """6 个新 convert decoder 全部注册."""
        names = {s.name for s in REGISTRY}
        for name in [
            "bin-ascii", "dec-bin", "bin-dec",
            "dec-hex", "hex-dec", "ascii-bin",
        ]:
            assert name in names, f"{name} not registered"

    def test_all_6_have_category_convert(self):
        """6 个新 decoder 都在 category=convert."""
        from automisc.core.decoders.registry import get_decoder
        for name in [
            "bin-ascii", "dec-bin", "bin-dec",
            "dec-hex", "hex-dec", "ascii-bin",
        ]:
            spec = get_decoder(name)
            assert spec is not None
            assert spec.category == "convert", f"{name} has category={spec.category}"

    def test_all_6_have_text_only_true(self):
        """6 个新 decoder text_only=True (走 input 区)."""
        from automisc.core.decoders.registry import get_decoder
        for name in [
            "bin-ascii", "dec-bin", "bin-dec",
            "dec-hex", "hex-dec", "ascii-bin",
        ]:
            spec = get_decoder(name)
            assert spec is not None
            assert spec.text_only is True, f"{name} text_only={spec.text_only}"

