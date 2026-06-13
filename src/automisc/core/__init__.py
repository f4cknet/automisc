"""Core 调度层（per ``Architecture.md`` §3）

子模块：
- ``result``  — ToolResult dataclass
- ``suspicious`` — SuspiciousPoint dataclass + 统一 schema
- ``registry``   — ``@register_tool`` 装饰器
- ``orchestrator`` — CoreOrchestrator 最小实现

注：v0.1.0b-PR1 暂不引入 router.py / journal.py（v0.1.2 / v0.1.4 任务）。
"""

from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint

__all__ = ["ToolResult", "SuspiciousPoint"]