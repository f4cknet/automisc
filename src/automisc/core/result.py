"""ToolResult dataclass（per ``prd.md`` §7 + ``Architecture.md`` §3.1）

工具 adapter 的统一返回类型。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from automisc.core.suspicious import SuspiciousPoint


@dataclass
class ToolResult:
    """工具执行结果（v0.1 最小可用字段集）。"""

    tool_name: str
    exit_code: int
    stdout: str
    stderr: str = ""
    suspicious_points: list[SuspiciousPoint] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None  # 进程级错误（超时 / 未找到 / PermissionError）

    @property
    def is_success(self) -> bool:
        """工具自身是否成功执行（exit_code == 0）。"""
        return self.exit_code == 0 and self.error is None

    def has_suspicious_points(self) -> bool:
        return len(self.suspicious_points) > 0