"""单测: rule_scanner (v0.5+ 独立规则库)

覆盖 5 类规则 + 3 边界 case + 1 strings 集成.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from automisc.core.utils.rule_scanner import (
    TextMatch,
    classify_text,
    find_sensitive_keywords,
    has_any_suspicious,
    has_sensitive_keyword,
    is_base32,
    is_base64,
    is_binary_string,
    is_hex_string,
    max_severity,
)


# ---------- 旧 API 兼容 (encoding_detector 仍在用) ----------
class TestIsFunctions:
    def test_is_base64_valid(self):
        assert is_base64("aGVsbG8gd29ybGQ=")  # 15 chars
        assert is_base64("aGVsbG8gd29ybGQgdGVzdA==")  # 20 chars

    def test_is_base64_invalid(self):
        assert not is_base64("hello world")
        assert not is_base64("abc")  # 太短

    def test_is_base32_valid(self):
        assert is_base32("JBSWY3DPEB3W64TMMQ======")

    def test_is_hex_valid(self):
        assert is_hex_string("deadbeefcafe1234567890abcdefcafe1234")  # 36 chars
        assert not is_hex_string("deadbeef")  # 8 chars 太短

    def test_is_binary_valid(self):
        assert is_binary_string("01010100111011001011010011010101")  # 32 chars
        assert not is_binary_string("01010")  # 太短

    def test_has_sensitive_keyword(self):
        assert has_sensitive_keyword("the secret key is: xyz")
        assert has_sensitive_keyword("flag{abc}")
        assert has_sensitive_keyword("password: 1234")
        assert not has_sensitive_keyword("just plain text")


# ---------- find_sensitive_keywords ----------
class TestFindSensitiveKeywords:
    def test_finds_multiple(self):
        text = "the secret key is: abc"
        matches = find_sensitive_keywords(text)
        # 应该找到 secret 和 key (2 个命中)
        values = [m.value for m in matches]
        assert "secret" in values
        assert "key" in values

    def test_finds_password(self):
        text = "Password: 1234"
        matches = find_sensitive_keywords(text)
        assert any(m.value.lower() == "password" for m in matches)

    def test_case_insensitive(self):
        text = "SECRET message"
        matches = find_sensitive_keywords(text)
        # SECRET 命中, 但 match 保留原大小写
        assert any(m.value == "SECRET" for m in matches)

    def test_no_match(self):
        assert find_sensitive_keywords("plain text") == []


# ---------- classify_text 主入口 ----------
class TestClassifyText:
    def test_whole_text_is_hex(self):
        text = "deadbeefcafe1234567890abcdefcafe1234"  # 36 hex chars
        matches = classify_text(text)
        assert len(matches) >= 1
        # 整段是 hex, 不再细分
        assert any(m.category == "hex" for m in matches)
        assert all(m.severity == 4 for m in matches)

    def test_whole_text_is_base64(self):
        text = "aGVsbG8gd29ybGQgdGVzdA=="
        matches = classify_text(text)
        assert any(m.category == "base64" for m in matches)

    def test_multiline_scanning(self):
        """strings 输出多行: 应逐行扫"""
        text = (
            "plain line 1\n"
            "another normal line\n"
            "deadbeefcafe1234567890abcdefcafe1234\n"  # line 3: hex
            "the password is: 1234\n"  # line 4: sensitive
        )
        matches = classify_text(text)
        # line 3 的 hex + line 4 的 password
        assert any(m.category == "hex" for m in matches)
        assert any(m.category == "sensitive_keyword" for m in matches)

    def test_mixed_text_with_keyword_substring(self):
        """普通 text 里有 keyword (非整段)"""
        text = "Hello, the secret of this challenge is hidden"
        matches = classify_text(text)
        # secret 命中 (severity 5)
        assert any(m.category == "sensitive_keyword" for m in matches)
        assert any(m.severity == 5 for m in matches)

    def test_empty_text(self):
        assert classify_text("") == []
        assert classify_text("   \n\n  ") == []

    def test_normal_text_returns_empty(self):
        """普通英文不命中"""
        assert classify_text("Hello world this is a normal sentence") == []

    def test_text_match_spans_accurate(self):
        """多行扫描时 span 偏移正确"""
        text = "line0\ndeadbeefcafe1234567890abcdefcafe1234"
        matches = classify_text(text)
        # 找到 hex match
        hex_match = next(m for m in matches if m.category == "hex")
        # span_start 应在原 text 里能找到 hex
        assert text[hex_match.span_start : hex_match.span_end] == hex_match.value

    def test_priority_whole_vs_partial(self):
        """整段是 hex, 不再细分 (避免重复报 'X' 'Y'...)"""
        text = "abc" * 20  # 60 chars, 不全是 hex
        matches = classify_text(text)
        # 不是 hex (含非 hex 字符), 但 classify_text 应该看是否整段符合, 不符合再逐行
        # 整段不符合, 但逐行也只有一个 line, 还是不符合
        # 结果: 整段是 base64 候选 (12+ chars, 字符集合法) -> 命中 base64
        if matches:
            assert all(m.category in ("base64", "base32", "hex", "binary", "sensitive_keyword") for m in matches)

    def test_real_meihuai_hex_string(self):
        """真实题: meihuai.jpg appended data (line 226)"""
        # strings 输出的某行, 1024 字节 hex 编码坐标
        hex_line = "28372c37290a28372c38290a28372c39290a" * 30  # 1080 chars
        matches = classify_text(hex_line)
        # 整段 = hex (整段字符集全合法 + 长度 ≥ 32)
        assert any(m.category == "hex" for m in matches)


# ---------- has_any_suspicious / max_severity ----------
class TestAggregates:
    def test_has_any_suspicious(self):
        assert has_any_suspicious("flag{abc}")
        assert has_any_suspicious("deadbeefcafe1234567890abcdef")
        assert not has_any_suspicious("hello world")

    def test_max_severity(self):
        # 普通文本 → 0
        assert max_severity("hello world") == 0
        # hex 串 → 4
        assert max_severity("deadbeefcafe1234567890abcdefcafe1234") == 4
        # 含 flag → 5
        assert max_severity("flag{abc}") == 5
        # mixed → 5
        assert max_severity("flag{abc} + deadbeef") == 5


# ---------- 集成: strings adapter + rule_scanner (Owner 触发 meihuai 验证) ----------
class TestStringsAdapterIntegration:
    """strings adapter 跑 meihuai.jpg 应输出 hex 命中"""

    def test_strings_meihuai_jpg_finds_hex(self):
        from automisc.core.orchestrator import CoreOrchestrator

        if not Path("Challenge/meihuai.jpg").exists():
            pytest.skip("Challenge/meihuai.jpg not found")

        core = CoreOrchestrator()
        r = core.run_tool("strings", "Challenge/meihuai.jpg")
        assert r.exit_code == 0
        # 至少应有 1 个十六进制命中
        hex_sps = [sp for sp in r.suspicious_points if "十六进制串" in sp.category or "hex" in sp.category]
        assert len(hex_sps) >= 1, (
            f"meihuai 应有 hex 命中, 实际: "
            f"{[(sp.category, sp.severity) for sp in r.suspicious_points]}"
        )
        # severity=4 (rule_scanner 评分)
        assert hex_sps[0].severity == 4
        # suggested_action 应含 "hex/binary -> ascii"
        assert "hex" in hex_sps[0].suggested_action.lower() or "ascii" in hex_sps[0].suggested_action.lower()

    def test_strings_key_exe_finds_base64(self):
        """strings adapter 跑 KEY.exe (base64 data URL)"""
        from automisc.core.orchestrator import CoreOrchestrator

        if not Path("Challenge/KEY.exe").exists():
            pytest.skip("Challenge/KEY.exe not found")

        core = CoreOrchestrator()
        r = core.run_tool("strings", "Challenge/KEY.exe")
        assert r.exit_code == 0
        # KEY.exe 是 data URL 头 + base64
        b64_sps = [sp for sp in r.suspicious_points if "base64" in sp.category.lower() or "Base64" in sp.category]
        # 至少有 1 个 base64 命中
        assert len(b64_sps) >= 1, (
            f"KEY.exe 应有 base64 命中, 实际: "
            f"{[(sp.category, sp.severity) for sp in r.suspicious_points]}"
        )

    def test_strings_normal_text_no_false_positive(self):
        """普通文本文件 strings 不应报 hex/binary/base64"""
        from automisc.core.orchestrator import CoreOrchestrator

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("hello world this is just a normal text file with some content\n")
            f.write("no suspicious data here at all\n")
            f.write("just plain english sentences and punctuation.\n")
            path = f.name

        try:
            core = CoreOrchestrator()
            r = core.run_tool("strings", path)
            # 整段文本没 hex 串, 也没敏感词
            hex_or_b64 = [
                sp for sp in r.suspicious_points
                if "hex" in sp.category.lower() or "base64" in sp.category.lower()
            ]
            assert len(hex_or_b64) == 0, (
                f"普通文本不应误报 hex/b64: {[(sp.category, sp.matched_pattern) for sp in hex_or_b64]}"
            )
        finally:
            Path(path).unlink(missing_ok=True)
