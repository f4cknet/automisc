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

    v0.5-fix-find-suspicious-race-condition (per Owner 2026-06-29 22:57 拍板 A):
    - 持有最近一次 adapter 实例 (_last_adapter), 允许外部强 terminate 嵌套 subprocess
    - kill_last_subprocess() 给 main_window 调: 拖新文件时清旧 steghide 30s timeout 段
    """

    def __init__(
        self,
        *,
        default_timeout: float = 30.0,
        journal: Journal | None = None,
    ) -> None:
        self.default_timeout = default_timeout
        self.journal = journal or Journal()
        # v0.5-fix-find-suspicious-race-condition: 持有最近一次 adapter 实例
        # (per v0.1.1 ToolAdapter 单例复用模式, 实际每个 tool_name 多次 run_tool 共享同实例
        # 还是各次新建? 实际: get_tool_class(name)() 每次新建, 所以 _last_adapter 跟当前
        # adapter 引用一致; 但 kill_last_subprocess 设计成"清最近一次"为 owner 拖新文件时
        # 强 terminate 嵌套 subprocess)
        self._last_adapter: ToolAdapter | None = None

    def run_tool(self, tool_name: str, file_path: str) -> ToolResult:
        """根据名称取 adapter 并执行 + 自动写 journal.

        Args:
            tool_name: 已注册的工具名（见 ``automisc tools list``）
            file_path: 目标文件路径

        Returns:
            ``ToolResult``，含 exit_code / stdout / suspicious_points 等

        注意：本方法**不**捕获 FileNotFoundError — 由调用方决定是否预检查。
        journal 会自动记录（含 error 字段）。

        v0.5-fix-find-suspicious-race-condition: 持有 adapter 引用 + 重入保护
        (旧 adapter 实例可能嵌套 subprocess 没清, 先 _terminate_current_proc).
        """
        # 取 adapter（ToolNotFoundError 透传）
        cls = get_tool_class(tool_name)
        adapter: ToolAdapter = cls()
        self._last_adapter = adapter
        # 重入保护: 旧 adapter 嵌套 subprocess 没清, 跑新工具前先 terminate
        # (idempotent, 没 _current_proc 啥也不做)
        adapter._terminate_current_proc()

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

    def kill_last_subprocess(self) -> None:
        """v0.5-fix-find-suspicious-race-condition: 强 kill 最近一次工具的嵌套 subprocess.

        调用场景: MainWindow._on_new_file_selected 拖新文件时, 在 clear output/journal 之前
        调此方法, 避免旧工具 (e.g. steghide 30s timeout) 段在 archive pool 之后写入新
        output 区 (race condition).

        Idempotent: 多次调不抛, 没 _last_adapter / 没 _current_proc 啥也不做.
        """
        if self._last_adapter is None:
            return
        self._last_adapter._terminate_current_proc()
        # 保留 _last_adapter 引用 (下次 run_tool 会覆盖), 不清

    def last_adapter_tool_name(self) -> str:
        """返回最近一次 run_tool 的 tool name (debug + 测试用, main_window 不调)."""
        if self._last_adapter is None:
            return ""
        return self._last_adapter.name