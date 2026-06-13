"""测试 tools/forensics/network/tshark.py"""
from __future__ import annotations

from automisc.core.registry import get_tool
from automisc.tools.forensics.network.tshark import TsharkAdapter


def test_tshark_adapter_is_registered():
    a = get_tool("tshark")
    assert isinstance(a, TsharkAdapter)


def test_tshark_adapter_extracts_flag_from_pcap():
    """真实 pcap fixture 含 flag{...} → 应该命中 flag suspicious point。"""
    import os
    pcap = "tests/fixtures/sample_http_flag.pcap"
    if not os.path.exists(pcap):
        pytest.skip(f"fixture not found: {pcap}")
    a = TsharkAdapter()
    result = a.run(pcap)
    assert result.is_success
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr3_smoke_tshark_xyz}" in sp.matched_pattern for sp in flag_sp)


def test_tshark_adapter_extracts_webshell_keyword_from_pcap():
    """fixture 中 POST /shell.php → 应该命中 webshell_family。"""
    import os
    pcap = "tests/fixtures/sample_http_flag.pcap"
    if not os.path.exists(pcap):
        pytest.skip(f"fixture not found: {pcap}")
    a = TsharkAdapter()
    result = a.run(pcap)
    shell_sp = [sp for sp in result.suspicious_points if sp.category == "webshell_family"]
    assert any("shell.php" in sp.matched_pattern for sp in shell_sp)


def test_tshark_adapter_handles_corrupt_file(tmp_path):
    """非 pcap 文件 → exit_code 非 0 + 无 panic。"""
    bad = tmp_path / "not_a_pcap.bin"
    bad.write_bytes(b"this is not a pcap file at all\n" * 5)
    a = TsharkAdapter()
    result = a.run(str(bad))
    # tshark 应该报错（非 0 exit），但不挂
    assert result.exit_code != 0
    # 错误应捕获到 stderr
    assert "tshark" in result.stderr.lower() or "file" in result.stderr.lower() or len(result.stderr) > 0
    # 关键：result 仍可序列化（不抛异常）
    assert result.tool_name == "tshark"


def test_tshark_adapter_handles_missing_file(tmp_path):
    """不存在的文件 → FileNotFoundError 被 _run_subprocess 捕获。"""
    a = TsharkAdapter()
    result = a.run(str(tmp_path / "definitely_does_not_exist.pcap"))
    # exit 127 (executable not found) 或 2 (tshark "couldn't open file")
    # 都算"被错误处理捕获"，不 panic
    assert result.exit_code != 0
    assert len(result.stderr) > 0


def test_tshark_adapter_webshell_regex_matches_eval_base64():
    """单元级：webshell 正则应命中 eval(base64_decode...)。"""
    from automisc.tools.forensics.network.tshark import _WEBSHELL_RE
    assert _WEBSHELL_RE.search("eval(base64_decode($_POST[cmd]))")
    assert _WEBSHELL_RE.search("/shell.php")
    assert _WEBSHELL_RE.search("behinder")
    assert not _WEBSHELL_RE.search("normal GET request")


# pytest import (for skip decorator)
import pytest
