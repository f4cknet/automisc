"""CoreOrchestrator（per ``Architecture.md`` §3.4）

v0.1.1 范围：
- ``run_tool(tool_name, file_path) -> ToolResult``：单次调用
- 实例化 adapter（懒）
- 错误捕获（超时 / 文件不存在 / subprocess 错误）
- **Journal 集成**：每次 run_tool 自动写 journal (v0.1.1 core 完整性)

v0.5+ 路线：route / template / DAG。
"""
from __future__ import annotations

from automisc.core.exceptions import FileNotAutomiscError
from automisc.core.journal import Journal
from automisc.core.registry import get_tool_class
from automisc.core.result import ToolResult
from automisc.tools.base import ToolAdapter


class CoreOrchestrator:
    """automisc 的 Core 调度层入口.

    Args:
        default_timeout: 工具默认超时（秒）
        journal: 可选 Journal 实例（不传则自动 new 一个）
    """

    def __init__(
        self,
        *,
        default_timeout: float = 30.0,
        journal: Journal | None = None,
    ) -> None:
        self.default_timeout = default_timeout
        self.journal = journal or Journal()

    def run_tool(self, tool_name: str, file_path: str) -> ToolResult:
        """根据名称取 adapter 并执行 + 自动写 journal.

        Args:
            tool_name: 已注册的工具名（见 ``automisc tools list``）
            file_path: 目标文件路径

        Returns:
            ``ToolResult``，含 exit_code / stdout / suspicious_points 等

        注意：本方法**不**捕获 FileNotFoundError — 由调用方决定是否预检查。
        journal 会自动记录（含 error 字段）。
        """
        # 取 adapter（ToolNotFoundError 透传）
        cls = get_tool_class(tool_name)
        adapter: ToolAdapter = cls()

        # 跑 + 错误捕获 + journal
        result = adapter.run(file_path)

        # 写 journal
        self.journal.record(
            tool_name=result.tool_name,
            file_path=file_path,
            exit_code=result.exit_code,
            suspicious_points=result.suspicious_points,
            error=result.error,
        )
        return result