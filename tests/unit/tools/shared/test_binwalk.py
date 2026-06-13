"""测试 tools/shared/binwalk.py"""
from __future__ import annotations

from automisc.core.registry import get_tool
from automisc.tools.shared.binwalk import BinwalkAdapter


def test_binwalk_adapter_is_registered():
    a = get_tool("binwalk")
    assert isinstance(a, BinwalkAdapter)


def test_binwalk_detects_zip_in_polyglot(tmp_polyglot_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_polyglot_file))
    assert result.is_success
    # polyglot 文件内嵌 ZIP，binwalk 应能识别
    file_header_sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("ZIP" in p.matched_pattern for p in file_header_sp)


def test_binwalk_detects_png(tmp_png_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    # PNG magic bytes 应该被识别
    sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("PNG" in p.matched_pattern for p in sp)


def test_binwalk_plain_text_no_file_header(tmp_text_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success
    # 纯文本无文件头，不应有 file_header 可疑点
    file_header_sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert len(file_header_sp) == 0