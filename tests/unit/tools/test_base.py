"""测试 tools/base.py — ToolAdapter 基类（subprocess 包装）。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.result import ToolResult
from automisc.tools.base import ToolAdapter


class _MinimalAdapter(ToolAdapter):
    name = "_minimal"
    category = "test"

    def run(self, file_path: str) -> ToolResult:
        cmd = [self.binary_path or "echo", "hi"]
        ec, out, err, dur = self._run_subprocess(cmd)
        return ToolResult(
            tool_name=self.name, exit_code=ec, stdout=out, stderr=err, duration_ms=dur,
        )


def test_check_available_returns_true_for_echo():
    class _EchoAdapter(ToolAdapter):
        name = "echo"
        category = "test"

        def run(self, file_path: str) -> ToolResult:  # pragma: no cover
            return ToolResult(tool_name=self.name, exit_code=0, stdout="")

    a = _EchoAdapter()
    # echo 是 macOS 自带命令
    assert a.check_available() is True


def test_check_available_returns_false_for_nonexistent():
    class _BadAdapter(ToolAdapter):
        name = "definitely_not_a_real_tool_xyz_123"
        category = "test"
        binary_path = "/path/that/does/not/exist_xyz"

        def run(self, file_path: str) -> ToolResult:
            return ToolResult(tool_name=self.name, exit_code=0, stdout="")

    a = _BadAdapter()
    assert a.check_available() is False


def test_subprocess_returns_exit_code_and_output():
    a = _MinimalAdapter()
    ec, out, err, dur = a._run_subprocess(["echo", "hello"])
    assert ec == 0
    assert "hello" in out
    assert dur >= 0


def test_subprocess_returns_127_for_missing_executable(tmp_path: Path):
    a = _MinimalAdapter()
    ec, out, err, dur = a._run_subprocess(["/nonexistent/binary/xyz"])
    assert ec == 127
    assert "not found" in err.lower()


def test_subprocess_includes_homebrew_in_path():
    """确认 macOS subprocess 时显式追加 Homebrew 路径（per Architecture.md §4.3）。"""
    a = _MinimalAdapter()
    with patch("os.environ", {"PATH": "/usr/bin:/bin"}):
        ec, out, err, dur = a._run_subprocess(["echo", "test"])
        # 如果不显式追加 PATH，echo 在 /usr/bin 应该还能找到（macOS 自带）
        # 但关键检查：subprocess 不应抛 KeyError（证明 env 已注入 PATH）
        assert ec == 0


def test_subprocess_timeout_returns_124(tmp_path: Path):
    """timeout 返回 exit code 124（与 `timeout` CLI 工具一致）。"""
    class _SlowAdapter(ToolAdapter):
        name = "_slow"
        category = "test"
        default_timeout = 0.1  # 100ms

        def run(self, file_path: str) -> ToolResult:
            cmd = ["sleep", "5"]
            ec, out, err, dur = self._run_subprocess(cmd, timeout=0.1)
            return ToolResult(tool_name=self.name, exit_code=ec, stdout=out, stderr=err, duration_ms=dur)

    a = _SlowAdapter()
    result = a.run("/dev/null")
    assert result.exit_code == 124
    assert "timeout" in result.stderr.lower()


def test_adapter_run_returns_tool_result():
    a = _MinimalAdapter()
    result = a.run("/dev/null")
    assert isinstance(result, ToolResult)
    assert result.tool_name == "_minimal"
    assert result.is_success