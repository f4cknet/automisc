"""Tests for auto_runner._maybe_suggest (per v0.5-auto-run-suggest).

auto_run 跑 lsb_tool / binwalk / strings 命中后, 加 suggest SP severity=4
告诉 Owner "可以手工跑 X chain 进一步分析"。

覆盖:
- lsb_tool 命中 lsb_text → suggest lsb-bytes chain (per v0.5-lsb-tool-bitplane-preview-matrix: 之前 zsteg 改 lsb_tool)
- binwalk 命中 ZIP / 7z / RAR / pyc → 对应 suggest
- strings 命中敏感关键词 → suggest bruteforce
- file / exiftool 命中 file_type → **不**加 suggest (无下一步)
- dedup: 多个相同 SP 只加 1 条 suggest
- _maybe_suggest 纯函数, 不依赖 core.run_tool
"""
from __future__ import annotations

import pytest

from automisc.core.suspicious import SuspiciousPoint
from automisc.gui.auto_runner import _maybe_suggest


# ---------- helper ----------
def _make_sp(category: str, matched_pattern: str, offset: int = 0) -> SuspiciousPoint:
    """构造 SuspiciousPoint for test."""
    return SuspiciousPoint(
        id="",
        tool_name="test",
        file_path="/tmp/x.png",
        category=category,
        offset=offset,
        matched_pattern=matched_pattern,
        severity=5,
        suggested_action="",
    )


# ---------- lsb_tool suggest (per v0.5-lsb-tool-bitplane-preview-matrix: 之前 zsteg 改 lsb_tool) ----------
class TestLsbToolSuggest:
    """lsb_tool 命中 lsb_text → suggest lsb-bytes chain."""

    def test_lsb_tool_lsb_text_suggests_lsb_bytes_chain(self):
        """lsb_tool 命中 lsb_text → suggest SP 含 'lsb-bytes chain'."""
        sp = _make_sp("lsb_text", "b1,bgr,lsb,xy: AfKg^pL :")
        suggests = _maybe_suggest("lsb_tool", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        s = suggests[0]
        assert s.tool_name == "auto_run_suggest"
        assert s.category == "auto_run_suggest"
        assert s.severity == 4
        assert "lsb-bytes chain" in s.matched_pattern
        assert "Run→Chain→lsb-bytes" in s.matched_pattern

    def test_lsb_tool_other_category_no_suggest(self):
        """lsb_tool 命中其他 category → 不加 suggest (MVP 只覆盖 lsb_text)."""
        sp = _make_sp("other_category", "something")
        suggests = _maybe_suggest("lsb_tool", [sp], "/tmp/x.png")
        assert suggests == []


# ---------- binwalk suggest ----------
class TestBinwalkSuggest:
    """binwalk file_header 细分 ZIP / 7z / RAR / pyc."""

    def test_binwalk_zip_suggests_zip_chain(self):
        """binwalk 命中 ZIP → suggest 'zip chain'."""
        sp = _make_sp("file_header", "ZIP archive @ offset 0x109B3")
        suggests = _maybe_suggest("binwalk", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        assert "zip chain" in suggests[0].matched_pattern

    def test_binwalk_7z_suggests_sevenz_extract(self):
        """binwalk 命中 7z → suggest 'sevenz_extract'."""
        sp = _make_sp("file_header", "7z archive @ offset 0x500")
        suggests = _maybe_suggest("binwalk", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        assert "sevenz_extract" in suggests[0].matched_pattern

    def test_binwalk_rar_suggests_bruteforce(self):
        """binwalk 命中 RAR → suggest 'unzip' / 'bruteforce_rar'."""
        sp = _make_sp("file_header", "RAR archive @ offset 0x200")
        suggests = _maybe_suggest("binwalk", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        assert "bruteforce_rar" in suggests[0].matched_pattern

    def test_binwalk_pyc_suggests_pyc_decompiler(self):
        """binwalk 命中 pyc → suggest 'pyc_decompiler'."""
        sp = _make_sp("file_header", "Python 2.7 pyc (magic 62211)")
        suggests = _maybe_suggest("binwalk", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        assert "pyc_decompiler" in suggests[0].matched_pattern

    def test_binwalk_other_file_header_no_suggest(self):
        """binwalk 命中 PNG/JPEG/ELF 等 file_header → 不加 suggest (MVP 不覆盖)."""
        sp_png = _make_sp("file_header", "PNG image @ offset 0")
        sp_elf = _make_sp("file_header", "ELF binary @ offset 0x1000")
        suggests = _maybe_suggest("binwalk", [sp_png, sp_elf], "/tmp/x.png")
        assert suggests == []


# ---------- strings suggest ----------
class TestStringsSuggest:
    """strings 命中敏感关键词 → suggest bruteforce."""

    def test_strings_sensitive_keyword_suggests_bruteforce(self):
        """strings 命中 '敏感关键词_line' → suggest 'bruteforce'."""
        sp = _make_sp("敏感关键词_line", "line14785: FkEY")
        suggests = _maybe_suggest("strings", [sp], "/tmp/x.png")

        assert len(suggests) == 1
        assert "bruteforce" in suggests[0].matched_pattern


# ---------- 其他工具 / category 无 suggest ----------
class TestNoSuggestForOtherTools:
    """file / exiftool 等命中 file_type / EXIF metadata → 不加 suggest (无下一步)."""

    def test_file_file_type_no_suggest(self):
        """file 命中 file_type (元数据) → 不加 suggest."""
        sp = _make_sp("file_type", "PNG image data, 1253 x 834, 8-bit/color RGBA")
        suggests = _maybe_suggest("file", [sp], "/tmp/x.png")
        assert suggests == []

    def test_exiftool_metadata_no_suggest(self):
        """exiftool 命中 EXIF (元数据) → 不加 suggest (MVP 不覆盖)."""
        sp = _make_sp("metadata", "ExifTool Version Number: 13.55")
        suggests = _maybe_suggest("exiftool", [sp], "/tmp/x.png")
        assert suggests == []


# ---------- dedup ----------
class TestDedup:
    """每个 tool + 每个 sub-category 只加 1 条 suggest (噪声控制)."""

    def test_dedup_lsb_tool_multiple_lsb_text(self):
        """lsb_tool 命中 3 条 lsb_text → 只加 1 条 suggest."""
        sps = [
            _make_sp("lsb_text", "b1,bgr,lsb,xy: AfKg^pL :"),
            _make_sp("lsb_text", "b3,rgba,lsb,xy: \"u?3tG^q"),
            _make_sp("lsb_text", "b4,rgba,lsb,xy: v_h_4/8O8O"),
        ]
        suggests = _maybe_suggest("lsb_tool", sps, "/tmp/x.png")
        assert len(suggests) == 1  # dedup

    def test_dedup_binwalk_multiple_zips(self):
        """binwalk 命中 2 个 ZIP → 只加 1 条 suggest."""
        sps = [
            _make_sp("file_header", "ZIP archive @ offset 0x100"),
            _make_sp("file_header", "ZIP archive @ offset 0x500"),
        ]
        suggests = _maybe_suggest("binwalk", sps, "/tmp/x.png")
        assert len(suggests) == 1  # dedup


# ---------- 边界 ----------
class TestEdgeCases:
    """边界场景."""

    def test_empty_suspicious_points_returns_empty(self):
        """空 SP 列表 → 空 suggest."""
        assert _maybe_suggest("lsb_tool", [], "/tmp/x.png") == []

    def test_no_suggest_for_unknown_tool(self):
        """未知工具名 → 空 suggest (不抛异常)."""
        sp = _make_sp("lsb_text", "anything")
        suggests = _maybe_suggest("unknown_tool", [sp], "/tmp/x.png")
        assert suggests == []

    def test_suggest_offset_inherits_from_original_sp(self):
        """suggest SP 的 offset 跟原 SP 一致 (e.g. binwalk ZIP offset)."""
        sp = _make_sp("file_header", "ZIP archive @ offset 0x109B3", offset=0x109B3)
        suggests = _maybe_suggest("binwalk", [sp], "/tmp/x.png")
        assert suggests[0].offset == 0x109B3

    def test_suggest_severity_is_4(self):
        """所有 suggest SP severity=4 (info, 不是真正可疑)."""
        sp = _make_sp("lsb_text", "b1,bgr,lsb,xy: AfKg^pL :")
        suggests = _maybe_suggest("lsb_tool", [sp], "/tmp/x.png")
        assert all(s.severity == 4 for s in suggests)