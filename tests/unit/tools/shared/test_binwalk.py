"""测试 tools/shared/binwalk.py (v0.5-binwalk-extract 扩展)

含：
- 原 4 个测试（registered / zip / png / text）
- v0.5-binwalk-extract 新增 (PEM/SSH 关键字 + extract_files)
"""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from automisc.core.registry import get_tool
from automisc.tools.shared.binwalk import (
    BinwalkAdapter,
    _FILE_HEADER_KEYWORDS,
)


# ---------- 原 v0.1 测试（保留） ----------

def test_binwalk_adapter_is_registered():
    a = get_tool("binwalk")
    assert isinstance(a, BinwalkAdapter)


def test_binwalk_detects_zip_in_polyglot(tmp_polyglot_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_polyglot_file))
    assert result.is_success
    file_header_sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("ZIP" in p.matched_pattern for p in file_header_sp)


def test_binwalk_detects_png(tmp_png_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("PNG" in p.matched_pattern for p in sp)


def test_binwalk_plain_text_no_file_header(tmp_text_file):
    a = BinwalkAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success
    file_header_sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert len(file_header_sp) == 0


# ---------- v0.5-binwalk-extract 新增测试 ----------

def test_keyword_whitelist_includes_pem_ssh_rsa():
    """v0.5-binwalk-extract 关键字白名单必须含 PEM/SSH/RSA 三种私钥格式."""
    normalized = [k.lower() for k in _FILE_HEADER_KEYWORDS]
    assert "pem private key" in normalized
    assert "ssh private key" in normalized
    assert "rsa private key" in normalized


def test_keyword_whitelist_preserves_legacy():
    """v0.1 旧关键字（17 项）必须保留，不破坏老 fixture."""
    # 精确检查（避免子串误匹配 "pcap" in "pcapng" 之类）
    normalized = [k.lower() for k in _FILE_HEADER_KEYWORDS]
    legacy_set = {
        "png image", "jpeg image", "gif image", "pdf document",
        "zip archive", "rar archive", "7-zip archive",
        "gzip compressed", "bzip2 compressed", "xz compressed",
        "tar archive", "elf ", "pe32 ", "microsoft office",
        "opendocument", "pcap",
    }
    for required in legacy_set:
        assert required in normalized, f"missing legacy keyword: {required!r}"


SAMPLE_BINWALK_GREATESCAPE = """\
DECIMAL                            HEXADECIMAL                        DESCRIPTION
-----------------------------------------------------------------------------------------------------------------------------
0                                 0x0                                Microsoft Azure packet capture
335200                            0x51D60                            PEM private key
338557                            0x52A7D                            PEM private key
-----------------------------------------------------------------------------------------------------------------------------
"""


def test_adapter_parses_pem_hits_from_greatescape():
    """mock 扫描输出: 2 个 PEM private key 应被识别 (之前会丢)."""
    a = BinwalkAdapter()
    with patch.object(a, "_run_subprocess", return_value=(0, SAMPLE_BINWALK_GREATESCAPE, "", 30)):
        # mock _extract_files 不实际跑 binwalk -e
        with patch.object(a, "_extract_files", return_value=[]):
            result = a.run("/tmp/fake.pcap")

    pem_sps = [sp for sp in result.suspicious_points if "PEM" in sp.matched_pattern]
    assert len(pem_sps) == 2
    for sp in pem_sps:
        assert sp.severity == 4
        assert sp.category == "file_header"
        assert "PEM private key @ offset" in sp.matched_pattern


def test_adapter_includes_extracted_path_in_context():
    """当 _extract_files 返回真文件时, SP context 应含路径."""
    fake_extracted = [
        "/tmp/fake__binwalk_extracted/fake.extracted/51D60/pem.key",
    ]
    a = BinwalkAdapter()
    with patch.object(a, "_run_subprocess", return_value=(0, SAMPLE_BINWALK_GREATESCAPE, "", 30)):
        with patch.object(a, "_extract_files", return_value=fake_extracted):
            result = a.run("/tmp/fake.pcap")

    # 找到 offset 0x51D60 (=335200) 对应的 SP
    pem_335200 = [sp for sp in result.suspicious_points
                  if sp.matched_pattern == "PEM private key @ offset 335200"][0]
    # context 应含 "extracted_files="
    assert "extracted_files=" in pem_335200.context
    assert "51D60/pem.key" in pem_335200.context
    # suggested_action 应含 Wireshark 模板
    assert "Wireshark" in pem_335200.suggested_action
    assert "--ssl.keys" in pem_335200.suggested_action
    assert "已提取" in pem_335200.suggested_action


def test_adapter_no_hits_no_extract_call():
    """0 hits → _extract_files 不被调用 (避免无谓的 binwalk -e 跑)."""
    a = BinwalkAdapter()
    no_hits = "DECIMAL  HEXADECIMAL  DESCRIPTION\n--------------------------------\n0          0x0         (no signatures)\n"
    with patch.object(a, "_run_subprocess", return_value=(0, no_hits, "", 10)):
        with patch.object(a, "_extract_files") as mock_extract:
            result = a.run("/tmp/fake.pcap")

    mock_extract.assert_not_called()
    assert result.suspicious_points == []


def test_adapter_metadata_records_extracted_files():
    """metadata['extracted_files'] 应是真文件路径列表."""
    fake_extracted = [
        "/tmp/fake__binwalk_extracted/fake.extracted/51D60/pem.key",
        "/tmp/fake__binwalk_extracted/fake.extracted/52A7D/pem.key",
    ]
    a = BinwalkAdapter()
    with patch.object(a, "_run_subprocess", return_value=(0, SAMPLE_BINWALK_GREATESCAPE, "", 30)):
        with patch.object(a, "_extract_files", return_value=fake_extracted):
            result = a.run("/tmp/fake.pcap")

    assert "extracted_files" in result.metadata
    assert result.metadata["extracted_files"] == fake_extracted
    assert "extract_dir" in result.metadata
    assert result.metadata["extract_dir"].endswith("__binwalk_extracted")


# ---------- 集成：真 pcap 跑 greatescape（需 binwalk + 真 fixture） ----------

def test_adapter_real_greatescape_pcap():
    """真实 pcap 跑: greatescape 命中 2 个 PEM private key + 提取到 samedir."""
    pcap = "tests/fixtures/challenges/greatescape.pcap"
    if not os.path.exists(pcap):
        pytest.skip(f"fixture not found: {pcap}")
    if subprocess.run(["which", "binwalk"], capture_output=True).returncode != 0:
        pytest.skip("binwalk not installed")

    a = BinwalkAdapter()
    result = a.run(pcap)

    assert result.is_success
    pem_sps = [sp for sp in result.suspicious_points if "PEM" in sp.matched_pattern]
    # greatescape 含 2 个 PEM 私钥
    assert len(pem_sps) >= 2

    # 第一个 SP context 应含 extracted 路径
    assert "extracted_files=" in pem_sps[0].context
    assert "pem.key" in pem_sps[0].context

    # metadata 应含真提取文件
    assert "extracted_files" in result.metadata
    assert len(result.metadata["extracted_files"]) >= 2
