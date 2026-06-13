"""测试 tools/forensics/network/tcpdump.py"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.forensics.network.tcpdump import TcpdumpAdapter


def test_tcpdump_adapter_is_registered():
    a = get_tool("tcpdump")
    assert isinstance(a, TcpdumpAdapter)


def test_tcpdump_adapter_extracts_flag_from_pcap():
    """真实 pcap fixture 含 flag → 应该命中。"""
    import os
    pcap = "tests/fixtures/sample_http_flag.pcap"
    if not os.path.exists(pcap):
        pytest.skip(f"fixture not found: {pcap}")
    a = TcpdumpAdapter()
    result = a.run(pcap)
    assert result.is_success
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr3_smoke_tshark_xyz}" in sp.matched_pattern for sp in flag_sp)


def test_tcpdump_adapter_handles_non_pcap_file(tmp_path):
    """非 pcap 文件 → exit_code 非 0。"""
    bad = tmp_path / "not_pcap.bin"
    bad.write_bytes(b"not a pcap")
    a = TcpdumpAdapter()
    result = a.run(str(bad))
    assert result.exit_code != 0
    assert len(result.stderr) > 0
    assert "file" in result.stderr.lower() or "format" in result.stderr.lower()


def test_tcpdump_adapter_handles_missing_file(tmp_path):
    """不存在的文件 → 错误处理（exit ≠ 0）。"""
    a = TcpdumpAdapter()
    result = a.run(str(tmp_path / "ghost.pcap"))
    assert result.exit_code != 0
