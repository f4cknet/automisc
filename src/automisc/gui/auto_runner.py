"""AutoRunner 链式调度（v0.1.1 GUI 增强）

按 FileRouter 推荐顺序 **串行** 跑工具，每个跑完自动起下一个。
跑完整个 list 后 emit ``finished`` signal。

设计：
- 持有 tool_names 列表 + file_path + core
- 跟 ToolRunner 同样基于 QThread（**但循环跑多个**）
- 串行原因：GUI 显示空间有限 + 顺序可读 + 避免并发时 adapter 抢资源
- 用单个 QThread 内部循环（vs 起多个 QThread 池）
- 每个工具跑完 emit ``tool_finished(tool_name, result)`` 增量更新 UI
- 整个链跑完 emit ``chain_finished(summaries)`` 总结

v0.1.1 范围：串行（v0.5+ 范围：并发池 QThreadPool）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QThread, Signal

from automisc.core.exceptions import AutomiscError
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.result import ToolResult
from automisc.core.router import RouteRecommendation


@dataclass
class AutoRunSummary:
    """链中一个工具的跑完总结."""

    tool_name: str
    success: bool
    exit_code: int
    suspicious_count: int
    error: Optional[str] = None


class AutoRunner(QThread):
    """按顺序跑多个工具的 QThread.

    用法::

        runner = AutoRunner(core, recommendations, file_path)
        runner.tool_started.connect(lambda t, i, n: ...)
        runner.tool_finished.connect(lambda t, summary: ...)
        runner.chain_finished.connect(lambda summaries: ...)
        runner.chain_failed.connect(lambda tool, err: ...)
        runner.start()
    """

    # Signal: 单个工具开始 (tool_name, index, total)
    tool_started = Signal(str, int, int)
    # Signal: 单个工具跑完 (tool_name, AutoRunSummary, ToolResult)
    tool_finished = Signal(str, object, object)
    # Signal: 整个链跑完 (list[AutoRunSummary])
    chain_finished = Signal(list)
    # Signal: 链中某个工具 fatal error (ToolNotFoundError / FileNotAutomiscError)
    chain_failed = Signal(str, str)
    # Signal: 整体进度 (current_index, total)
    progress = Signal(int, int)

    def __init__(
        self,
        core: CoreOrchestrator,
        recommendations: list[RouteRecommendation],
        file_path: str,
        max_tools: int = 5,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.file_path = file_path
        # 取 score > 0 的前 max_tools 个
        self.tool_names: list[str] = [
            rec.tool_name
            for rec in recommendations[:max_tools]
            if rec.score > 0
        ]
        self._summaries: list[AutoRunSummary] = []
        self._stopped = False

    def stop(self) -> None:
        """请求停止（下一个工具开始前检查）."""
        self._stopped = True

    def run(self) -> None:
        """QThread 入口：串行跑 self.tool_names."""
        total = len(self.tool_names)
        for i, tool_name in enumerate(self.tool_names):
            if self._stopped:
                break

            self.tool_started.emit(tool_name, i, total)
            self.progress.emit(i, total)

            try:
                result = self.core.run_tool(tool_name, self.file_path)
            except AutomiscError as e:
                # 致命错误（ToolNotFoundError 等）→ 链失败
                self.chain_failed.emit(tool_name, str(e))
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=str(e),
                    )
                )
                break  # 终止链
            except Exception as e:  # noqa: BLE001
                # 未知错误
                self.chain_failed.emit(tool_name, f"{type(e).__name__}: {e}")
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
                break

            # 单个工具跑完
            summary = AutoRunSummary(
                tool_name=tool_name,
                success=result.exit_code == 0 and result.error is None,
                exit_code=result.exit_code,
                suspicious_count=len(result.suspicious_points),
                error=result.error,
            )
            self._summaries.append(summary)
            # 传完整 ToolResult 给 GUI（避免重复执行）
            self.tool_finished.emit(tool_name, summary, result)

        # 链结束
        self.progress.emit(total, total)
        self.chain_finished.emit(self._summaries)

    def summaries(self) -> list[AutoRunSummary]:
        return list(self._summaries)


__all__ = ["AutoRunner", "AutoRunSummary"]
