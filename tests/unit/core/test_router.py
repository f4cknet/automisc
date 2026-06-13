"""FileRouter 单测（v0.1.1 core/router.py）"""
from __future__ import annotations

from pathlib import Path

import pytest

from automisc.core.exceptions import FileNotAutomiscError
from automisc.core.router import (
    EXTENSION_ROUTES,
    FileRouter,
    MAGIC_SIGNATURES,
    detect_magic,
)


# ---------- detect_magic ----------
class TestDetectMagic:
    def test_png(self):
        assert detect_magic(b"\x89PNG\r\n\x1a\nIHDR") == "PNG image"

    def test_jpeg(self):
        assert detect_magic(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "JPEG image"

    def test_zip(self):
        assert detect_magic(b"PK\x03\x04\x14\x00") == "ZIP archive"

    def test_pcap_le(self):
        assert detect_magic(b"\xd4\xc3\xb2\xa1\x02\x00") == "PCAP little-endian"

    def test_pcap_be(self):
        assert detect_magic(b"\xa1\xb2\xc3\xd4\x02\x00") == "PCAP big-endian"

    def test_unknown(self):
        assert detect_magic(b"random data here") is None

    def test_empty(self):
        assert detect_magic(b"") is None


# ---------- FileRouter ----------
class TestFileRouter:
    def test_route_png(self, tmp_path):
        # 写一个真 PNG 头
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\nIHDR" + b"\x00" * 100)
        router = FileRouter()
        r = router.route(png)
        assert r.detected_extension == ".png"
        assert r.detected_magic == "PNG image"
        assert any(rec.tool_name == "zsteg" for rec in r.recommendations)
        assert any(rec.tool_name == "steghide" for rec in r.recommendations)

    def test_route_pcap(self, tmp_path):
        pcap = tmp_path / "test.pcap"
        pcap.write_bytes(b"\xd4\xc3\xb2\xa1" + b"\x00" * 50)
        r = FileRouter().route(pcap)
        assert r.detected_extension == ".pcap"
        assert r.detected_magic == "PCAP little-endian"
        assert any(rec.tool_name == "tshark" for rec in r.recommendations)

    def test_route_zip(self, tmp_path):
        z = tmp_path / "test.zip"
        z.write_bytes(b"PK\x03\x04" + b"\x00" * 30)
        r = FileRouter().route(z)
        assert r.detected_magic == "ZIP archive"
        assert any(rec.tool_name == "sevenz" for rec in r.recommendations)

    def test_route_unknown_extension_fallback(self, tmp_path):
        """未知扩展名 → 通用 FALLBACK_TOOLS."""
        f = tmp_path / "test.unknownext"
        f.write_bytes(b"random binary data \x00\x01\x02")
        r = FileRouter().route(f)
        assert r.detected_extension == ".unknownext"
        tool_names = [rec.tool_name for rec in r.recommendations]
        assert "file" in tool_names
        assert "strings" in tool_names
        assert "binwalk" in tool_names

    def test_route_text_small_file(self, tmp_path):
        """小文本 + 无扩展名 → TEXT_FALLBACK."""
        f = tmp_path / "smalltext"
        f.write_text("hello world\nthis is plain text\n")
        r = FileRouter().route(f)
        tool_names = [rec.tool_name for rec in r.recommendations]
        assert "strings" in tool_names

    def test_route_ranks_by_score(self, tmp_path):
        """recommendations 按 score 降序."""
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        r = FileRouter().route(png)
        scores = [rec.score for rec in r.recommendations]
        assert scores == sorted(scores, reverse=True)

    def test_route_file_size_in_result(self, tmp_path):
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
        r = FileRouter().route(png)
        # \x89PNG\r\n\x1a\n = 8 bytes magic + 200 zero = 208 total
        assert r.file_size == 208

    def test_route_file_not_found_raises(self, tmp_path):
        """文件不存在 → FileNotAutomiscError.not_found."""
        with pytest.raises(FileNotAutomiscError) as excinfo:
            FileRouter().route(tmp_path / "nonexistent.bin")
        assert "not found" in str(excinfo.value)


# ---------- EXTENSION_ROUTES 完整性 ----------
class TestExtensionRoutes:
    def test_common_categories_covered(self):
        """常见 CTF 文件类型都有 routes."""
        for ext in [".png", ".jpg", ".wav", ".mp4", ".pcap", ".zip", ".log", ".vmem"]:
            assert ext in EXTENSION_ROUTES, f"{ext} missing from EXTENSION_ROUTES"

    def test_each_route_has_tools(self):
        for ext, routes in EXTENSION_ROUTES.items():
            assert len(routes) >= 1, f"{ext} has no routes"
            for tool, reason, score in routes:
                assert isinstance(tool, str)
                assert isinstance(reason, str)
                assert isinstance(score, int)
                assert score > 0


# ---------- MAGIC_SIGNATURES 完整性 ----------
class TestMagicSignatures:
    def test_magic_signatures_format(self):
        for sig, desc in MAGIC_SIGNATURES:
            assert isinstance(sig, bytes)
            assert isinstance(desc, str)
            assert len(sig) >= 2
