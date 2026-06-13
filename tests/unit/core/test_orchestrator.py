"""测试 core/orchestrator.py。"""
from __future__ import annotations

import pytest

from automisc.core import registry as reg_mod
from automisc.core.exceptions import ToolNotFoundError
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


_EXPECTED_RESULT = ToolResult(
    tool_name="stub_tool",
    exit_code=0,
    stdout="ok",
    suspicious_points=[
        SuspiciousPoint(
            id="", tool_name="stub_tool", file_path="/dev/null",
            category="flag", matched_pattern="flag{x}", severity=5, suggested_action="submit",
        )
    ],
)


class _StubAdapter(ToolAdapter):
    """测试用 stub adapter（无参构造，固定返回 _EXPECTED_RESULT）。"""

    name = "stub_tool"
    category = "test"

    def run(self, file_path: str) -> ToolResult:
        return _EXPECTED_RESULT


@pytest.fixture(autouse=True)
def _cleanup_stub():
    """清理 stub_tool。"""
    reg_mod._TOOL_REGISTRY.pop("stub_tool", None)
    yield
    reg_mod._TOOL_REGISTRY.pop("stub_tool", None)


def test_run_tool_returns_adapter_result():
    register_tool(_StubAdapter)
    core = CoreOrchestrator()
    result = core.run_tool("stub_tool", "/dev/null")
    assert result.tool_name == "stub_tool"
    assert result.is_success
    assert len(result.suspicious_points) == 1
    assert result.suspicious_points[0].matched_pattern == "flag{x}"


def test_run_tool_unknown_tool_raises():
    core = CoreOrchestrator()
    with pytest.raises(ToolNotFoundError, match="tool not registered"):
        core.run_tool("does_not_exist_xyz", "/dev/null")