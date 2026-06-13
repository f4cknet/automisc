"""CoreOrchestrator 最小实现（per ``Architecture.md`` §3.4）

v0.1.0b-PR1 范围：
- ``run_tool(tool_name, file_path) -> ToolResult``：单次调用
- 实例化 adapter（懒）
- 错误捕获（超时 / 文件不存在 / subprocess 错误）

v0.1 后续 PR 才引入：journal / route / template / DAG。
"""
from __future__ import annotations

from automisc.core.registry import get_tool_class
from automisc.core.result import ToolResult
from automisc.tools.base import ToolAdapter


class CoreOrchestrator:
    """automisc 的 Core 调度层入口（v0.1 最小可用）。"""

    def __init__(self, *, default_timeout: float = 30.0) -> None:
        self.default_timeout = default_timeout

    def run_tool(self, tool_name: str, file_path: str) -> ToolResult:
        """根据名称取 adapter 并执行。

        Args:
            tool_name: 已注册的工具名（见 ``automisc tools list``）
            file_path: 目标文件路径

        Returns:
            ``ToolResult``，含 exit_code / stdout / suspicious_points 等

        注意：本方法**不**捕获 FileNotFoundError — 由调用方决定是否预检查。
        """
        cls = get_tool_class(tool_name)
        adapter: ToolAdapter = cls()
        return adapter.run(file_path)