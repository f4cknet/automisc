"""ToolRunner (v0.1.1 GUI 完整性)

异步跑工具的 QThread，避免 GUI 主线程卡死。

设计：
- ``ToolRunner(QThread)`` 持有 tool_name / file_path / core
- 通过 ``finished_with_result`` signal 把 ToolResult 传回主线程
- 通过 ``failed_with_error`` signal 报告错误
- 主线程只需 connect signals + runner.start()，不阻塞 UI

v0.1.1 范围：单工具单次执行（v0.1 简化）
v0.5+ 范围：批量并发（多工具 + QThreadPool）
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.result import ToolResult


class ToolRunner(QThread):
    """QThread 异步跑单个工具.

    用法::

        runner = ToolRunner(core, tool_name="strings", file_path="/tmp/x")
        runner.finished_with_result.connect(self._on_result)
        runner.failed_with_error.connect(self._on_error)
        runner.start()
    """

    # Signal：跑成功（带 ToolResult）
    finished_with_result = Signal(object)  # object = ToolResult
    # Signal：跑失败（带异常）
    failed_with_error = Signal(str)
    # Signal：进度（v0.1 不细分进度，仅启动/完成两个）
    started_run = Signal(str, str)  # tool_name, file_path

    def __init__(
        self,
        core: CoreOrchestrator,
        tool_name: str,
        file_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.tool_name = tool_name
        self.file_path = file_path
        self._result: Optional[ToolResult] = None
        self._error: Optional[str] = None

    def run(self) -> None:
        """QThread 入口：在子线程跑 tool + emit signals."""
        self.started_run.emit(self.tool_name, self.file_path)
        try:
            result = self.core.run_tool(self.tool_name, self.file_path)
            self._result = result
            self.finished_with_result.emit(result)
        except Exception as e:  # noqa: BLE001
            self._error = str(e)
            self.failed_with_error.emit(f"{type(e).__name__}: {e}")

    @property
    def result(self) -> Optional[ToolResult]:
        return self._result

    @property
    def error(self) -> Optional[str]:
        return self._error


__all__ = ["ToolRunner"]
