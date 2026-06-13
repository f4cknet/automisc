"""测试 core/suspicious.py。"""
from __future__ import annotations

from automisc.core.suspicious import (
    SEVERITY_MAP,
    SUSPICIOUS_PATTERNS,
    SuspiciousPoint,
    scan_output_for_suspicious,
)


def test_suspicious_point_default_id_is_uuid():
    sp = SuspiciousPoint(
        id="",
        tool_name="t",
        file_path="/x",
        category="c",
        matched_pattern="p",
        severity=1,
        suggested_action="a",
    )
    assert sp.id  # 自动生成
    assert len(sp.id) == 36  # UUID 格式


def test_suspicious_point_keeps_given_id():
    sp = SuspiciousPoint(
        id="custom-id",
        tool_name="t",
        file_path="/x",
        category="c",
        matched_pattern="p",
        severity=1,
        suggested_action="a",
    )
    assert sp.id == "custom-id"


def test_scan_detects_flag():
    stdout = "blah blah flag{this_is_the_flag}\nmore text"
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    flag_points = [p for p in points if p.category == "flag"]
    assert len(flag_points) == 1
    assert "flag{this_is_the_flag}" in flag_points[0].matched_pattern
    assert flag_points[0].severity == 5  # flag 是最高级


def test_scan_detects_ctf_and_key_flags():
    stdout = "ctf{my_ctf_flag} and key{another_one}"
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    flag_points = [p for p in points if p.category == "flag"]
    assert len(flag_points) == 2


def test_scan_detects_keyword_password():
    stdout = "config: password=hunter2"
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    kw_points = [p for p in points if p.category == "keyword"]
    assert any(p.matched_pattern.lower() == "password" for p in kw_points)


def test_scan_detects_base64_candidate():
    # 长度 ≥ 16 且字符集合法
    stdout = "aGVsbG8gd29ybGQgdGVzdA==\n"
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    b64 = [p for p in points if p.category == "base64_candidate"]
    assert len(b64) == 1


def test_scan_detects_hex_string():
    stdout = "deadbeefcafebabe1234567890abcdef\n"
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    hex_pts = [p for p in points if p.category == "hex_string"]
    assert len(hex_pts) == 1


def test_scan_caps_base64_candidates_at_5():
    # 6 个 base64 候选，但只应取前 5
    stdout = "\n".join([f"aGVsbG8gd29ybGQgdGVzdA==" for _ in range(6)])
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=stdout)
    b64 = [p for p in points if p.category == "base64_candidate"]
    assert len(b64) == 5


def test_scan_empty_stdout_returns_empty():
    points = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout="")
    assert points == []


def test_scan_preserves_tool_name_and_file_path():
    points = scan_output_for_suspicious(
        tool_name="my_tool",
        file_path="/path/to/file",
        stdout="flag{abc}",
    )
    assert all(p.tool_name == "my_tool" for p in points)
    assert all(p.file_path == "/path/to/file" for p in points)


def test_severity_map_has_flag_at_5():
    assert SEVERITY_MAP["flag"][0] == 5


def test_patterns_compile():
    # 确认所有正则预编译（不应抛错）
    for cat, pat in SUSPICIOUS_PATTERNS.items():
        assert hasattr(pat, "search"), f"{cat} 不是预编译的正则"