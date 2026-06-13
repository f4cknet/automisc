"""测试 tools/forensics/log/"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.forensics.log.evtx_dump import EvtxDumpAdapter
from automisc.tools.forensics.log.grep import GrepAdapter


AUTH_LOG = "tests/fixtures/sample_auth.log"


# === grep ===

def test_grep_adapter_is_registered():
    a = get_tool("grep")
    assert isinstance(a, GrepAdapter)


def test_grep_extracts_password_keyword(auth_log):
    a = GrepAdapter()
    result = a.run(auth_log)
    assert result.is_success
    kw = [sp for sp in result.suspicious_points if sp.category == "log_keyword" and "password" in sp.matched_pattern.lower()]
    assert len(kw) >= 1
    # password 是强信号 → severity=4
    assert all(sp.severity >= 4 for sp in kw)


def test_grep_extracts_sudo_keyword(auth_log):
    """sudo: 关键字命中 → severity=2。"""
    a = GrepAdapter()
    result = a.run(auth_log)
    sudo = [sp for sp in result.suspicious_points if sp.category == "log_keyword" and "sudo" in sp.matched_pattern]
    assert len(sudo) >= 1


def test_grep_extracts_secret_keyword(auth_log):
    """secret 关键字 → severity=4 (强信号)。"""
    a = GrepAdapter()
    result = a.run(auth_log)
    sec = [sp for sp in result.suspicious_points if sp.category == "log_keyword" and "secret" in sp.matched_pattern]
    assert len(sec) >= 1
    assert all(sp.severity >= 4 for sp in sec)


def test_grep_handles_empty_file(tmp_path):
    a = GrepAdapter()
    empty = tmp_path / "empty.log"
    empty.write_bytes(b"")
    result = a.run(str(empty))
    # grep 无命中时 exit=1
    assert result.exit_code != 0 or len(result.suspicious_points) == 0


def test_grep_handles_missing_file(tmp_path):
    a = GrepAdapter()
    result = a.run(str(tmp_path / "ghost.log"))
    # exit 2 (file not found) 或 1 (no match)
    assert result.exit_code != 0


# === evtx_dump ===

def test_evtx_dump_adapter_is_registered():
    a = get_tool("evtx_dump")
    assert isinstance(a, EvtxDumpAdapter)


def test_evtx_dump_handles_empty_file(tmp_path):
    """空文件 → 报 EVTX parse error，不 panic。"""
    a = EvtxDumpAdapter()
    empty = tmp_path / "empty.evtx"
    empty.write_bytes(b"")
    result = a.run(str(empty))
    # exit_code 非 0（python-evtx 报 cannot mmap empty file）
    assert result.exit_code != 0
    assert "empty" in result.stderr.lower() or "parse" in result.stderr.lower() or "evtx" in result.stderr.lower()
    # 关键：不 panic + result 可序列化
    assert isinstance(result.suspicious_points, list)


def test_evtx_dump_handles_missing_file(tmp_path):
    a = EvtxDumpAdapter()
    result = a.run(str(tmp_path / "ghost.evtx"))
    assert result.exit_code != 0


def test_evtx_dump_handles_corrupt_file(tmp_path):
    """非 EVTX 格式文件（普通文本）→ 不 panic。"""
    a = EvtxDumpAdapter()
    bad = tmp_path / "not_evtx.evtx"
    bad.write_bytes(b"this is not an evtx file\n" * 5)
    result = a.run(str(bad))
    # 可能 python-evtx 报错或解析出 0 records；都该不 panic
    assert result.exit_code in (0, 1)


# === fixtures ===

@pytest.fixture
def auth_log():
    import os
    if not os.path.exists(AUTH_LOG):
        pytest.skip(f"fixture not found: {AUTH_LOG}")
    return AUTH_LOG
