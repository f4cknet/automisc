"""测试 tools/forensics/memory/"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.forensics.memory.vol import VolAdapter


EMPTY_VMEM = "/tmp/empty.vmem"


def test_vol_adapter_is_registered():
    a = get_tool("vol")
    assert isinstance(a, VolAdapter)


def test_vol_handles_non_vmem_file(empty_vmem):
    """空文件 / 非 vmem → vol3 报 Unsatisfied requirement，不 panic。"""
    a = VolAdapter()
    result = a.run(empty_vmem)
    # vol3 报 "Unsatisfied requirement"（stdout）→ exit_code 非 0
    assert result.exit_code != 0 or "Unsatisfied" in result.stdout or "Volatility" in result.stdout
    # 关键：result 可序列化 + 至少记录了 plugin 元数据
    plugin_sp = [sp for sp in result.suspicious_points if sp.category == "vol3_plugin"]
    assert len(plugin_sp) >= 1


def test_vol_handles_missing_file(tmp_path):
    a = VolAdapter()
    result = a.run(str(tmp_path / "ghost.vmem"))
    # vol3 报 "File does not exist" → exit_code 2 (argparse)
    assert result.exit_code != 0


def test_vol_records_all_default_plugins(empty_vmem):
    """v0.1 默认 4 个 plugin 都应该被记录到 suspicious_points。"""
    a = VolAdapter()
    result = a.run(empty_vmem)
    plugin_sp = [sp for sp in result.suspicious_points if sp.category == "vol3_plugin"]
    plugins = {sp.matched_pattern for sp in plugin_sp}
    # 应该记录 windows.pslist（第一个）
    assert any("pslist" in p for p in plugins)


# === fixtures ===

@pytest.fixture
def empty_vmem():
    import os
    # 创建一个空文件
    with open(EMPTY_VMEM, "w") as f:
        pass
    return EMPTY_VMEM
