"""Unit tests for v0.5-LSB-router.

- core/encoding_detector.py
- core/actions/lsb_extract.py (LSBExtractAction)
"""
from __future__ import annotations

from pathlib import Path

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

    # ---------- v0.5-train-008: text 通道也写文件 ----------
    def test_text_branch_writes_file_to_samedir(self, tmp_path, monkeypatch):
        """v0.5-train-008 + v0.5-lsb-extract-output-bytes: text 通道 main 也写到 <stem>__lsb.<ext>, 同目录.

        v0.5-lsb-extract-output-bytes 修复:
        - 旧: 写死 .txt + write_text (UTF-8 decode, 二进制乱码)
        - 新: magic 判定后缀 + write_bytes (per Owner "89 50 4E 47 是 PNG" + "用 python wb")
        - text 字节流没 magic → .bin fallback
        """
        from automisc.core.actions import lsb_extract

        # mock zsteg 检测: 返回 1 个 text 行 (b1,rgb,lsb,xy)
        fake_zsteg_stdout = (
            "b1,rgb,lsb,xy         .. text: \"Hey I think we can write safely\"\n"
        )

        def fake_detect(file_path):
            return fake_zsteg_stdout

        def fake_extract(file_path, channel):
            return b"Hey I think we can write safely in this file."

        monkeypatch.setattr(lsb_extract, "_run_zsteg_detect", fake_detect)
        monkeypatch.setattr(lsb_extract, "_run_zsteg_extract", fake_extract)

        png = tmp_path / "challenge.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        action = LSBExtractAction()
        result = action.run({"file_path": str(png)})

        assert result.success is True
        # main extracted_path 应该存在
        extracted_path = result.data["lsb_text"]["extracted_path"]
        assert Path(extracted_path).exists()
        # 路径在 input.parent (同目录)
        assert Path(extracted_path).parent == png.parent
        # v0.5-lsb-extract-output-bytes 修复: text 字节流没 magic, fallback .bin
        assert Path(extracted_path).name == "challenge__lsb.bin", (
            f"expected .bin fallback (text bytes have no magic), got: {Path(extracted_path).name}"
        )
        # 写真二进制 (per v0.5-lsb-extract-output-bytes: write_bytes 替代 write_text)
        written_bytes = Path(extracted_path).read_bytes()
        assert written_bytes == b"Hey I think we can write safely in this file.", (
            "written bytes should match raw (no UTF-8 decode loss)"
        )
        # text 字段 decode 后内容正确 (GUI 展示用)
        assert result.data["lsb_text"]["text"].startswith("Hey I think we can write safely")
        # extracted_files schema 跟 file 分支一致
        assert result.data["extracted_files"] == [extracted_path]

    def test_text_branch_sensitive_keyword_still_writes_file(self, tmp_path, monkeypatch):
        """v0.5-train-008: severity=5 命中敏感词时 main 也写文件 (不会因为 break 跳过)."""
        from automisc.core.actions import lsb_extract

        fake_zsteg_stdout = (
            "b1,rgb,lsb,xy         .. text: \"secret key is: st3g0_saurus_wr3cks\"\n"
            "b1,r,lsb,xy           .. text: \"random garbage\"\n"
        )

        def fake_detect(file_path):
            return fake_zsteg_stdout

        def fake_extract(file_path, channel):
            if "rgb" in channel:
                return b"the secret key is: st3g0_saurus_wr3cks"
            return b"random garbage"

        monkeypatch.setattr(lsb_extract, "_run_zsteg_detect", fake_detect)
        monkeypatch.setattr(lsb_extract, "_run_zsteg_extract", fake_extract)

        png = tmp_path / "steg.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        action = LSBExtractAction()
        result = action.run({"file_path": str(png)})

        assert result.success is True
        # main 是 severity=5 (敏感词)
        assert result.data["lsb_text"]["sensitive_keyword"] is True
        assert result.data["lsb_text"]["severity"] == 5
        assert result.data["flag_candidate"] is not None
        # 仍然写文件 (v0.5-lsb-extract-output-bytes 修复: write_bytes + magic 后缀)
        extracted_path = Path(result.data["lsb_text"]["extracted_path"])
        assert extracted_path.exists()
        # v0.5-lsb-extract-output-bytes 修复: text 字节流没 magic → .bin fallback (不是 .txt)
        assert extracted_path.name == "steg__lsb.bin", (
            f"expected .bin fallback (text bytes have no magic), got: {extracted_path.name}"
        )
        # 写真二进制
        written_bytes = extracted_path.read_bytes()
        assert b"st3g0_saurus_wr3cks" in written_bytes, (
            "written bytes should contain secret key (no UTF-8 decode loss)"
        )
        assert result.data["extracted_files"] == [str(extracted_path)]
        # severity=5 立即停 → 只扫了 1 个通道
        assert len(result.data["lsb_texts_scanned"]) == 1

    def test_text_branch_overwrite_on_rerun(self, tmp_path, monkeypatch):
        """v0.5-train-008: 同 stem + purpose + suffix 重名, 二次跑覆盖前次结果 (per output_path_for 规则)."""
        from automisc.core.actions import lsb_extract

        def fake_detect(file_path):
            return "b1,rgb,lsb,xy         .. text: \"first run\"\n"

        def fake_extract_first(file_path, channel):
            return b"first run content"

        def fake_extract_second(file_path, channel):
            return b"second run content"

        png = tmp_path / "x.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        # 第 1 次跑
        monkeypatch.setattr(lsb_extract, "_run_zsteg_detect", fake_detect)
        monkeypatch.setattr(lsb_extract, "_run_zsteg_extract", fake_extract_first)
        action = LSBExtractAction()
        r1 = action.run({"file_path": str(png)})
        assert r1.success is True
        out_path = Path(r1.data["lsb_text"]["extracted_path"])
        assert out_path.read_text(encoding="utf-8") == "first run content"

        # 第 2 次跑 (内容变了) → 覆盖
        monkeypatch.setattr(lsb_extract, "_run_zsteg_extract", fake_extract_second)
        r2 = action.run({"file_path": str(png)})
        assert r2.success is True
        assert out_path.read_text(encoding="utf-8") == "second run content"
