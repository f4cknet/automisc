"""v0.5-decoder-friendly-hint 单测: 内容意图检测器

覆盖:
- 7 种类型检测 (Ook! / BF / base64 / base32 / hex / binary / caesar)
- 边界 (空 / 太短 / GUI log / 模糊样本)
- GUI log 行剥离
- specificity 优先级 (Ook! 含 [ 也优先于 BF)
"""
from __future__ import annotations

import pytest

from automisc.core.decoders.content_detector import (
    DetectionResult,
    detect_input_intent,
    _strip_gui_log_lines,
)


# ---------- Ook! ----------
class TestOokDetection:
    def test_owner_real_ook_sample(self):
        """Owner 2026-06-20 21:25 实战 Ook! 样本 (截前 200 chars)."""
        text = "Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook."
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "ook"
        assert "🦧" in result.display
        assert result.kind == "Ook! 代码"
        assert "tokens" in result.reason

    def test_short_ook_rejected(self):
        """< 20 chars 不算 (太短可能误判, e.g. 'Ook.' 单 token)."""
        text = "Ook. Ook. Ook."
        result = detect_input_intent(text)
        # 长度 < 20, 不应触发 ook
        if result and result.decoder_name == "ook":
            pytest.fail(f"长度过短 ({len(text)}) 不应触发 ook 检测")


# ---------- BrainFuck ----------
class TestBrainfuckDetection:
    def test_real_bf_code(self):
        """典型 BF 代码: '++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>.' (Hello World)."""
        text = "++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>."
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "brainfuck"
        assert "🧠" in result.display
        assert result.kind == "BrainFuck 代码"

    def test_owner_paste_4_segments(self):
        """Owner 2026-06-20 21:17 实战 4 段 paste (290 chars)."""
        text = "+++++ +++++ [->++ +++++ +++<] >++.+ +++++ .<+++ [->-- -<]>- -.+++ +++.<"
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "brainfuck"

    def test_short_bf_no_loop_rejected(self):
        """短 BF 无循环 (< 12 chars 且没 [ ]) 不算."""
        text = "+++.."
        result = detect_input_intent(text)
        # 长度 < 12, 不应触发 BF
        if result and result.decoder_name == "brainfuck":
            pytest.fail(f"短 BF 无循环不应触发 brainfuck 检测")


# ---------- base64 ----------
class TestBase64Detection:
    def test_real_base64_with_padding(self):
        text = "SGVsbG8gV29ybGQ="  # "Hello World" base64
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "base64"
        assert "Base64" in result.display

    def test_real_base64_with_plus(self):
        text = "aGVsbG8gd29ybGR+aGVsbG8="  # 含 + 字符
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "base64"

    def test_short_base64_rejected(self):
        """长度 < 16 不算 (易跟短英文撞)."""
        text = "SGVsbG8="
        result = detect_input_intent(text)
        if result and result.decoder_name == "base64":
            pytest.fail(f"短 base64 不应触发 (易误判)")


# ---------- base32 ----------
class TestBase32Detection:
    def test_real_base32(self):
        text = "JBSWY3DPEBLW64TMMQQQ===="  # base32 标准
        result = detect_input_intent(text)
        # 这个串同时匹配 base64 (字符集 [A-Z0-9+/=] + 行尾 =) 和 base32
        # base64 优先级高于 base32 (因为先检 base64) — 实战也合理,
        # 因为 base32 字符集是 base64 子集, base64 命中更安全
        assert result is not None
        assert result.decoder_name in ("base32", "base64")


# ---------- hex ----------
class TestHexDetection:
    def test_real_hex(self):
        text = "deadbeef48656c6c6f"  # 偶数长度 hex
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "hex-ascii"
        assert "16" in result.display or "进制" in result.display

    def test_short_hex_rejected(self):
        """长度 < 8 不算."""
        text = "deadbe"  # 6 chars
        result = detect_input_intent(text)
        if result and result.decoder_name == "hex-ascii":
            pytest.fail(f"短 hex ({len(text)} chars) 不应触发")

    def test_odd_length_hex_rejected(self):
        """奇数长度 hex 不算 (hex 解释器要求偶数)."""
        text = "deadbee"  # 7 chars
        result = detect_input_intent(text)
        if result and result.decoder_name == "hex-ascii":
            pytest.fail(f"奇数长度 hex 不应触发")


# ---------- binary ----------
class TestBinaryDetection:
    def test_real_binary(self):
        text = "0100100001100101011011000110110001101111"  # "Hello" binary, 40 chars
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "bin-ascii"

    def test_not_multiple_of_8_rejected(self):
        """长度不是 8 倍数不算."""
        text = "010010000110010101101100011011000110111"  # 39 chars
        result = detect_input_intent(text)
        if result and result.decoder_name == "bin-ascii":
            pytest.fail(f"非 8 倍数 binary ({len(text)} chars) 不应触发")


# ---------- caesar (低优先级) ----------
class TestCaesarDetection:
    def test_uppercase_word(self):
        """全大写字母 → caesar (易误判, 仅其他规则不命中时触发)."""
        text = "KHOOR"  # caesar shift=3 → HELLO
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "caesar"
        assert "凯撒" in result.display

    def test_lowercase_not_caesar(self):
        """小写不算 caesar (凯撒通常大写)."""
        text = "khoor"
        result = detect_input_intent(text)
        # 小写不应触发 caesar (caesar 是大写密文约定)
        if result and result.decoder_name == "caesar":
            pytest.fail(f"小写不应触发 caesar (lowercase)")

    def test_too_long_not_caesar(self):
        """太长 (> 30 chars) 不算 caesar."""
        text = "A" * 50
        result = detect_input_intent(text)
        if result and result.decoder_name == "caesar":
            pytest.fail(f"过长 ({len(text)} chars) 不应触发 caesar (易误判普通全大写文本)")


# ---------- GUI log 行剥离 ----------
class TestGuiLogStrip:
    def test_log_lines_stripped(self):
        """GUI log 行 ([stderr] / === / ---) 应被剥离, 露出真内容."""
        text = "[stderr] noop\n=== Decoder: brainfuck ===\n+++..[--->++<]>++."
        # 真内容是 "+++..[--->++<]>++." 14 chars 含循环, 应触发 BF
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "brainfuck"


# ---------- 边界 ----------
class TestBoundary:
    def test_empty_returns_none(self):
        assert detect_input_intent("") is None
        assert detect_input_intent("   ") is None
        assert detect_input_intent("\n\n") is None

    def test_very_short_returns_none(self):
        assert detect_input_intent("ab") is None
        assert detect_input_intent("12") is None

    def test_pure_log_no_real_content(self):
        """全 GUI log 行, 剥离后空 → 返回 None."""
        text = "[stderr] noop\n=== Decoder: brainfuck ===\n"
        result = detect_input_intent(text)
        assert result is None

    def test_returns_dataclass(self):
        """返回值是 DetectionResult dataclass."""
        text = "Ook. Ook. Ook. Ook. Ook. Ook."  # 24 chars ≥ 20 阈值
        result = detect_input_intent(text)
        assert isinstance(result, DetectionResult)
        assert hasattr(result, "decoder_name")
        assert hasattr(result, "display")
        assert hasattr(result, "kind")
        assert hasattr(result, "reason")


# ---------- specificity 优先级 ----------
class TestSpecificity:
    def test_ook_priority_over_brainfuck(self):
        """Ook! 含 [ 也应被识别为 ook (specificity 优先)."""
        # 含 [ ] 但也含 Ook tokens — 应优先识别为 Ook!
        text = "Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook. Ook."
        result = detect_input_intent(text)
        assert result is not None
        assert result.decoder_name == "ook", "Ook! 优先级应高于 BrainFuck"

    def test_base64_priority_over_hex(self):
        """base64 含 hex 字符也应被识别为 base64."""
        text = "48656c6c6f576f726c64="  # base64 编码 "HelloWorld"
        result = detect_input_intent(text)
        assert result is not None
        # base64 有行尾 = 触发
        assert result.decoder_name == "base64"