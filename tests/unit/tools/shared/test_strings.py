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
    # v0.5+: rule_scanner 路径, category = "敏感关键词_lineN"
    flag_sp = [p for p in result.suspicious_points if "敏感关键词" in p.category]
    assert any("flag{test_fixture_flag_12345}" in p.matched_pattern for p in flag_sp)


def test_strings_adapter_extracts_keywords(tmp_text_file):
    a = StringsAdapter()
    result = a.run(str(tmp_text_file))
    # v0.5+: rule_scanner 路径, 敏感关键词走 "敏感关键词" 类目
    kw_sp = [p for p in result.suspicious_points if "敏感关键词" in p.category]
    # password 关键字命中
    assert any("password" in p.matched_pattern.lower() for p in kw_sp)


def test_strings_adapter_extracts_base64(tmp_text_file):
    a = StringsAdapter()
    result = a.run(str(tmp_text_file))
    # v0.5+: rule_scanner 路径, category = "Base64 串_lineN"
    b64_sp = [p for p in result.suspicious_points if "Base64" in p.category or "base64" in p.category.lower()]
    assert any("aGVsbG8" in p.matched_pattern for p in b64_sp)


def test_strings_adapter_handles_binary_file(tmp_png_file):
    a = StringsAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    # PNG 二进制应该跑通（可能提取到一些字节）