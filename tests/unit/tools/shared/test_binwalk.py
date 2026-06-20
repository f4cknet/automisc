"""测试 tools/shared/binwalk.py (v0.5-philosophy-rethink)

含：
- 原 4 个测试 (registered / zip / png / text)
- v0.5-binwalk-extract 历史 (PEM/SSH 关键字白名单保留)
- v0.5-philosophy-rethink 新增: 验证 adapter 不雕文件
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


# ---------- 关键字白名单测试 (v0.5-binwalk-extract 保留) ----------

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
    """mock 扫描输出: 2 个 PEM private key 应被识别 (v0.5-binwalk-extract 历史行为)."""
    a = BinwalkAdapter()
    with patch.object(a, "_run_subprocess", return_value=(0, SAMPLE_BINWALK_GREATESCAPE, "", 30)):
        result = a.run("/tmp/fake.pcap")

    pem_sps = [sp for sp in result.suspicious_points if "PEM" in sp.matched_pattern]
    assert len(pem_sps) == 2
    for sp in pem_sps:
        assert sp.severity == 4
        assert sp.category == "file_header"
        assert "PEM private key @ offset" in sp.matched_pattern


# ---------- v0.5-philosophy-rethink 新增: 验证不雕文件 ----------

def test_adapter_does_not_extract_on_run():
    """v0.5-philosophy-rethink: binwalk adapter 跑完不雕文件.

    之前 v0.5-binwalk-extract 会在 run() 里调 _extract_files (binwalk -e),
    违背 owner 决策 1 "auto_run 不抢 flag". 现在:
    - 命中 file header keyword → SP 里 suggested_action 提示用户手工触发
    - 不会调 _extract_files (该方法已删)
    - metadata 不再有 extracted_files / extract_dir
    """
    a = BinwalkAdapter()
    with patch.object(a, "_run_subprocess", return_value=(0, SAMPLE_BINWALK_GREATESCAPE, "", 30)):
        result = a.run("/tmp/fake.pcap")

    # 1. SP 正常产生 (检测 OK)
    pem_sps = [sp for sp in result.suspicious_points if "PEM" in sp.matched_pattern]
    assert len(pem_sps) == 2

    # 2. suggested_action 提示手工触发 (而不是已自动提取)
    for sp in pem_sps:
        assert "建议 foremost / binwalk -e 分离" in sp.suggested_action
        assert "工具栏 foremost" in sp.suggested_action or "Chain 菜单 binwalk" in sp.suggested_action

    # 3. metadata 不再有 extracted_files / extract_dir (v0.5-philosophy-rethink)
    assert "extracted_files" not in result.metadata
    assert "extract_dir" not in result.metadata

    # 4. SP context 不再有 "extracted_files=" 前缀
    for sp in pem_sps:
        assert "extracted_files=" not in sp.context


def test_adapter_extract_files_method_removed():
    """v0.5-philosophy-rethink: _extract_files method 已删 (BinwalkExtractAction 独立实现)."""
    a = BinwalkAdapter()
    assert not hasattr(a, "_extract_files"), (
        "BinwalkAdapter._extract_files 已删 (per v0.5-philosophy-rethink); "
        "分离逻辑独立到 core/actions/binwalk_extract.py::BinwalkExtractAction"
    )


# ---------- 集成：真 pcap 跑 greatescape（需 binwalk + 真 fixture） ----------

def test_adapter_real_greatescape_pcap():
    """真实 pcap 跑: greatescape 命中 2 个 PEM private key (纯探测, 不雕文件).

    v0.5-philosophy-rethink: 删 v0.5-extract 的自动 binwalk -e 提取,
    集成测试也只验证检测 + suggested_action 提示, 不验证 extracted 路径.
    """
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

    # v0.5-philosophy-rethink: context 不再含 extracted 路径
    for sp in pem_sps:
        assert "extracted_files=" not in sp.context

    # metadata 也不再有 extracted_files
    assert "extracted_files" not in result.metadata
    assert "extract_dir" not in result.metadata
