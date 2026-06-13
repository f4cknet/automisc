"""测试 tools/shared/strings.py"""
from __future__ import annotations

from automisc.core.registry import get_tool
from automisc.tools.shared.strings import StringsAdapter


def test_strings_adapter_is_registered():
    a = get_tool("strings")
    assert isinstance(a, StringsAdapter)


def test_strings_adapter_extracts_flag(tmp_text_file):
    a = StringsAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success
    # flag 应该在 suspicious_points 里
    flag_sp = [p for p in result.suspicious_points if p.category == "flag"]
    assert any("flag{test_fixture_flag_12345}" in p.matched_pattern for p in flag_sp)


def test_strings_adapter_extracts_keywords(tmp_text_file):
    a = StringsAdapter()
    result = a.run(str(tmp_text_file))
    kw_sp = [p for p in result.suspicious_points if p.category == "keyword"]
    # password 关键字命中
    assert any("password" in p.matched_pattern.lower() for p in kw_sp)


def test_strings_adapter_extracts_base64(tmp_text_file):
    a = StringsAdapter()
    result = a.run(str(tmp_text_file))
    # "aGVsbG8gd29ybGQgdGVzdA==" 是合法 base64
    b64_sp = [p for p in result.suspicious_points if p.category == "base64_candidate"]
    assert any("aGVsbG8" in p.matched_pattern for p in b64_sp)


def test_strings_adapter_handles_binary_file(tmp_png_file):
    a = StringsAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    # PNG 二进制应该跑通（可能提取到一些字节）