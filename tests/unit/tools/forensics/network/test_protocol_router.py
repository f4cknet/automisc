"""测试 tools/forensics/network/protocol_router.py

包含：单元测试（mock tshark）+ 1 个真实 pcap 集成测试（greatescape.pcap 跳过的真实运行）。
"""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from automisc.core.registry import get_tool
from automisc.tools.forensics.network.protocol_router import (
    PcapProtocolRouterAdapter,
    build_wireshark_hint,
)


# ---------- 单元：build_wireshark_hint ----------

def test_build_wireshark_hint_includes_pcap_path():
    """生成的命令模板含原 pcap 路径."""
    hint = build_wireshark_hint("Challenge/greatescape.pcap", "ssc.key")
    assert "Challenge/greatescape.pcap" in hint
    assert "ssc.key" in hint


def test_build_wireshark_hint_mentions_tshark_rsa_keys():
    """模板含 tshark --ssl.keys / RSA keys 关键字."""
    hint = build_wireshark_hint("x.pcap", "y.key")
    assert "tls.keys_list" in hint
    assert "RSA Keys" in hint or "rsa" in hint.lower()


def test_build_wireshark_hint_includes_3_steps():
    """模板 3 步：1. 提取 key / 2. tshark 解密 / 3. Wireshark GUI."""
    hint = build_wireshark_hint("x.pcap", "y.key")
    assert "1." in hint
    assert "2." in hint
    assert "3." in hint


# ---------- 单元：adapter 注册 + 工具名 ----------

def test_pcap_protocol_router_is_registered():
    """adapter 注册到工具表."""
    a = get_tool("pcap_protocol_router")
    assert isinstance(a, PcapProtocolRouterAdapter)


def test_pcap_protocol_router_metadata():
    """adapter 元数据 (name / category)."""
    a = PcapProtocolRouterAdapter()
    assert a.name == "pcap_protocol_router"
    assert a.category == "forensics_network"


# ---------- 单元：mock tshark 输出，跑全流程 ----------

SAMPLE_IO_PHS_GREATESCAPE = """\
frame                                    frames:2756 bytes:935469
  sll                                    frames:2756 bytes:935469
    ip                                   frames:2756 bytes:935469
      tcp                                frames:2756 bytes:935469
        http                             frames:46 bytes:30901
        tls                              frames:913 bytes:621804
        ftp                              frames:16 bytes:1828
        ftp-data                         frames:1 bytes:3341
        smtp                             frames:33 bytes:6375
"""

SAMPLE_FTP_GREATESCAPE = """\
    1   0.0 FTP Request: USER bob
    2   0.0 FTP Request: PASS toto123
    3   0.0 FTP Request: STOR ssc.key
    4   0.0 FTP Response: 226-File successfully transferred
"""


def _mock_subprocess_for_greatescape(stdout_per_argv_match):
    """构造 _run_subprocess 的 mock：根据 cmd 前几个 token 返回对应 stdout."""
    def _runner(cmd, *args, **kwargs):
        # cmd 是 list[str]; 看是不是 io,phs / ftp / http
        if "io,phs" in cmd:
            return 0, SAMPLE_IO_PHS_GREATESCAPE, "", 100
        if "ftp" in cmd and "ftp-data" not in cmd:
            return 0, SAMPLE_FTP_GREATESCAPE, "", 50
        if "http" in cmd:
            return 0, "", "", 30
        return 1, "", "unknown cmd", 10
    return _runner


def test_adapter_runs_protocol_classify_and_key_finder():
    """mock tshark: 应输出 protocol_breakdown + tls_key_candidate 两个 SP."""
    a = PcapProtocolRouterAdapter()
    with patch.object(a, "_run_subprocess", side_effect=_mock_subprocess_for_greatescape(None)):
        result = a.run("Challenge/greatescape.pcap")

    assert result.is_success
    assert len(result.suspicious_points) == 2

    # SP 1: protocol_breakdown (severity=1)
    bd_sp = [sp for sp in result.suspicious_points if sp.category == "protocol_breakdown"][0]
    assert bd_sp.severity == 1
    assert "tls" in bd_sp.matched_pattern.lower() or "TLS" in bd_sp.matched_pattern

    # SP 2: tls_key_candidate (severity=4)
    key_sp = [sp for sp in result.suspicious_points if sp.category == "tls_key_candidate"][0]
    assert key_sp.severity == 4
    assert "ssc.key" in key_sp.matched_pattern
    # suggested_action 含 Wireshark 模板
    assert "tls.keys_list" in key_sp.suggested_action
    assert "RSA" in key_sp.suggested_action.upper() or "rsa" in key_sp.suggested_action


def test_adapter_skips_key_finder_when_no_cipher():
    """全明文（无 TLS）→ 不找 key 候选."""
    plaintext_only = """\
frame                                    frames:100 bytes:50000
  ip                                   frames:100 bytes:50000
    tcp                                frames:100 bytes:50000
      http                             frames:50 bytes:25000
      ftp                              frames:30 bytes:15000
"""
    a = PcapProtocolRouterAdapter()
    with patch.object(a, "_run_subprocess", side_effect=lambda cmd, *a, **kw:
                      (0, plaintext_only, "", 50) if "io,phs" in cmd else (0, "", "", 10)):
        result = a.run("x.pcap")

    assert result.is_success
    # 只有 protocol_breakdown SP，没有 tls_key_candidate
    categories = [sp.category for sp in result.suspicious_points]
    assert "protocol_breakdown" in categories
    assert "tls_key_candidate" not in categories


def test_adapter_skips_key_finder_when_no_plaintext_aux():
    """全 TLS（无明文辅助）→ 不找 key 候选."""
    cipher_only = """\
frame                                    frames:500 bytes:300000
  ip                                   frames:500 bytes:300000
    tcp                                frames:500 bytes:300000
      tls                              frames:500 bytes:300000
"""
    a = PcapProtocolRouterAdapter()
    with patch.object(a, "_run_subprocess", side_effect=lambda cmd, *a, **kw:
                      (0, cipher_only, "", 50) if "io,phs" in cmd else (0, "", "", 10)):
        result = a.run("x.pcap")

    assert result.is_success
    categories = [sp.category for sp in result.suspicious_points]
    assert "protocol_breakdown" in categories
    assert "tls_key_candidate" not in categories


def test_adapter_handles_tshark_failure():
    """tshark 跑失败（exit_code != 0）→ result.exit_code 非 0 + 无 SP."""
    a = PcapProtocolRouterAdapter()
    with patch.object(a, "_run_subprocess", return_value=(1, "", "tshark not found", 5)):
        result = a.run("x.pcap")

    assert not result.is_success
    assert result.suspicious_points == []


# ---------- 集成：真 pcap 跑 greatescape（需要 tshark + 真实 fixture） ----------

def test_adapter_real_greatescape_pcap():
    """真实 pcap 跑：greatescape 应该命中 tls_key_candidate 候选.

    需要：
    - tshark 已装
    - tests/fixtures/challenges/greatescape.pcap 存在
    """
    pcap = "tests/fixtures/challenges/greatescape.pcap"
    if not os.path.exists(pcap):
        pytest.skip(f"fixture not found: {pcap}")
    if subprocess.run(["which", "tshark"], capture_output=True).returncode != 0:
        pytest.skip("tshark not installed")

    a = PcapProtocolRouterAdapter()
    result = a.run(pcap)

    # 真实运行 tshark 应当 exit 0
    assert result.is_success

    categories = [sp.category for sp in result.suspicious_points]
    # 一定有 protocol_breakdown
    assert "protocol_breakdown" in categories
    # 应当命中 tls_key_candidate
    assert "tls_key_candidate" in categories

    # 候选 SP 含 ssc.key + Wireshark 模板
    key_sp = [sp for sp in result.suspicious_points if sp.category == "tls_key_candidate"][0]
    assert "ssc.key" in key_sp.matched_pattern
    assert key_sp.severity == 4
    assert "tls.keys_list" in key_sp.suggested_action
