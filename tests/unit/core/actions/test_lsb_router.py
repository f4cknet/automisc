"""Unit tests for v0.5-LSB-router.

- core/encoding_detector.py
- core/actions/lsb_extract.py (LSBExtractAction)
"""
from __future__ import annotations

import pytest

from automisc.core.actions.lsb_extract import LSBExtractAction
from automisc.core.encoding_detector import (
    has_sensitive_keyword,
    is_base32,
    is_base64,
    is_binary_string,
    is_hex_string,
    score_text_severity,
)


# ---------- encoding_detector: has_sensitive_keyword ----------
class TestHasSensitiveKeyword:
    def test_secret_keyword(self):
        assert has_sensitive_keyword("the secret key is: xyz") is True

    def test_flag_keyword_in_braces(self):
        assert has_sensitive_keyword("flag{test_123}") is True

    def test_ctf_keyword(self):
        assert has_sensitive_keyword("CTF{abc}") is True

    def test_case_insensitive(self):
        assert has_sensitive_keyword("SECRET message") is True
        assert has_sensitive_keyword("Flag is here") is True

    def test_key_substring(self):
        # 'key' 是子串匹配, 但要小心 false positive
        assert has_sensitive_keyword("the key is 1234") is True
        assert has_sensitive_keyword("monkey business") is True  # 'key' substring match - 接受

    def test_no_keyword(self):
        assert has_sensitive_keyword("hello world") is False
        assert has_sensitive_keyword("1234") is False

    def test_password_keyword(self):
        # Owner 后补: password 加入白名单
        assert has_sensitive_keyword("Password is: 1234") is True
        assert has_sensitive_keyword("the PASSWORD here") is True


# ---------- encoding_detector: is_base64 ----------
class TestIsBase64:
    def test_valid_base64_short(self):
        # 12+ chars (threshold)
        assert is_base64("aGVsbG8gd29ybGQ=") is True  # 'hello world' = 15 chars

    def test_valid_base64_long(self):
        assert is_base64("aGVsbG8gd29ybGQgdGVzdA==") is True

    def test_too_short(self):
        # < 12 chars 不算
        assert is_base64("aGVsbG8=") is False  # 8 chars

    def test_invalid_chars(self):
        assert is_base64("hello world!@#") is False  # 含非 base64 字符

    def test_empty(self):
        assert is_base64("") is False

    def test_with_whitespace(self):
        # 含空格不算
        assert is_base64("aGVs bG8=") is False


# ---------- encoding_detector: is_base32 ----------
class TestIsBase32:
    def test_valid_base32(self):
        # 12+ chars, A-Z 2-7
        assert is_base32("JBSWY3DPEB3W64TMMQ======") is True

    def test_too_short(self):
        assert is_base32("JBSWY3DP") is False  # < 12

    def test_lowercase(self):
        # 我们的 regex 限定 uppercase
        assert is_base32("jbswy3dpeb3w64tmmq======") is False


# ---------- encoding_detector: is_binary_string / is_hex_string ----------
class TestBinaryAndHex:
    def test_binary_valid(self):
        # 阈值 ≥ 32 chars (= 4 bytes)
        assert is_binary_string("01010100111011001011010011010101") is True  # 32 chars
        assert is_binary_string("0" * 64) is True  # 64 chars

    def test_binary_too_short(self):
        assert is_binary_string("01010100111") is False  # < 32
        assert is_binary_string("010101001110110010110100") is False  # 24 chars

    def test_binary_with_other_chars(self):
        assert is_binary_string("01010a1100") is False  # 含 a

    def test_hex_valid(self):
        # 阈值 ≥ 32 chars (= 16 bytes)
        assert is_hex_string("deadbeefcafe1234567890abcdefcafe1234") is True  # 36 chars
        assert is_hex_string("0" * 32) is True  # 32 chars

    def test_hex_too_short(self):
        assert is_hex_string("deadbeef") is False  # < 32
        assert is_hex_string("deadbeefcafe1234567890abcdef") is False  # 28 chars


# ---------- encoding_detector: score_text_severity ----------
class TestScoreTextSeverity:
    """Q1 决策树主入口."""

    def test_sensitive_keyword_severity_5(self):
        # secret/key/flag/ctf 命中
        assert score_text_severity("the secret key is: xyz") == 5
        assert score_text_severity("flag{test}") == 5
        assert score_text_severity("CTF{abc}") == 5
        assert score_text_severity("this is a KEY") == 5

    def test_base64_severity_4(self):
        assert score_text_severity("aGVsbG8gd29ybGQ=") == 4
        assert score_text_severity("JBSWY3DPEB3W64TMMQ======") == 4  # base32

    def test_binary_severity_4(self):
        assert score_text_severity("01010100111011001011010011010101") == 4  # 32 chars

    def test_hex_severity_4(self):
        assert score_text_severity("deadbeefcafe1234567890abcdefcafe1234") == 4  # 36 chars

    def test_normal_text_severity_3(self):
        assert score_text_severity("Hey I think we can write safely") == 3
        assert score_text_severity("hello world") == 3
        assert score_text_severity("你好世界") == 3

    def test_short_text_severity_3(self):
        # 短字符串兜底
        assert score_text_severity("hi") == 3
        assert score_text_severity("1234") == 3

    def test_priority_sensitive_over_encoding(self):
        # 敏感关键词优先于编码 (Q1 决策: 严重度最高)
        text_with_both = "secret key aGVsbG8gd29ybGQ="
        assert score_text_severity(text_with_both) == 5

    def test_password_severity_5(self):
        # Owner 后补: password → severity=5
        assert score_text_severity("Password is: hunter2") == 5


# ---------- LSBExtractAction ----------
class TestLSBExtractAction:
    """LSB 抽 text 终止 / 抽 file 二次 router."""

    def test_missing_file_path(self):
        action = LSBExtractAction()
        result = action.run({})
        assert result.success is False
        assert "file_path" in result.message

    def test_nonexistent_file(self, tmp_path):
        action = LSBExtractAction()
        result = action.run({"file_path": str(tmp_path / "no_such.png")})
        assert result.success is False
        assert "not found" in result.message

    def test_max_depth_protection(self, tmp_path):
        # 模拟 depth 已达上限
        png = tmp_path / "x.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        action = LSBExtractAction(max_depth=2)
        result = action.run({"file_path": str(png), "_lsb_depth": 2})
        assert result.success is False
        assert "max_depth" in result.message
        assert result.data.get("max_depth_hit") is True

    def test_zsteg_not_installed_graceful(self, tmp_path, monkeypatch):
        # 模拟 zsteg 不在 PATH
        from automisc.core.actions import lsb_extract

        monkeypatch.setattr(lsb_extract.shutil, "which", lambda x: None)
        png = tmp_path / "x.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        action = LSBExtractAction()
        result = action.run({"file_path": str(png)})
        assert result.success is False
        assert "zsteg" in result.message
