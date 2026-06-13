"""automisc Journal（v0.1.1 core 完整性补齐）

Session 级可疑点记录：把 ``CoreOrchestrator.run_tool()`` 调用的所有
``SuspiciousPoint`` 自动累积 + 可查询 + 可导出。

设计原则（per ``Architecture.md`` §3.4）：
- 内存版 ``Journal`` 即可（v0.1 范围）
- 文件版 ``flush_to_jsonl()`` 可选（v0.1 不做磁盘持久化）
- 与 GUI 的 ``journal_panel.py`` 职责分离：
    - ``core/journal.py`` = Core 层逻辑（记录 / 查询 / 统计）
    - ``gui/journal_panel.py`` = GUI 展示（已落地）
- 多 session 支持：每次 ``CoreOrchestrator()`` 创建一个新 Journal

v0.5+ 路线：
- 文件持久化（JSONL append-only）
- 跨 session 搜索（grep journal）
- journal 完整性校验
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from automisc.core.suspicious import SuspiciousPoint


@dataclass
class JournalEntry:
    """Journal 一条记录 = 一次 run_tool 的所有 suspicious_points 聚合."""

    tool_name: str
    file_path: str
    exit_code: int
    timestamp: datetime
    suspicious_points: list[SuspiciousPoint]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


class Journal:
    """Session 级可疑点记录器.

    用法::

        journal = Journal()
        # ... orchestrator.run_tool() 自动写 journal (v0.1.x 集成) ...
        for entry in journal.entries():
            print(entry.tool_name, len(entry.suspicious_points))
        journal.flush_to_jsonl(Path("/tmp/journal.jsonl"))
    """

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []

    def record(
        self,
        tool_name: str,
        file_path: str,
        exit_code: int,
        suspicious_points: list[SuspiciousPoint],
        error: str | None = None,
        timestamp: datetime | None = None,
    ) -> JournalEntry:
        """记录一次 tool run 的结果.

        Args:
            tool_name: 工具名
            file_path: 目标文件路径
            exit_code: 工具退出码
            suspicious_points: 可疑点列表
            error: 进程级错误（None 表示无错）
            timestamp: 记录时间（默认 now）

        Returns:
            写入的 JournalEntry
        """
        entry = JournalEntry(
            tool_name=tool_name,
            file_path=file_path,
            exit_code=exit_code,
            timestamp=timestamp or datetime.now(),
            suspicious_points=list(suspicious_points),
            error=error,
        )
        self._entries.append(entry)
        return entry

    # ---------- 查询 ----------
    def entries(self) -> list[JournalEntry]:
        """返回所有 entries（按写入顺序）."""
        return list(self._entries)

    def filter_by_tool(self, tool_name: str) -> list[JournalEntry]:
        return [e for e in self._entries if e.tool_name == tool_name]

    def filter_by_severity(self, min_severity: int) -> list[JournalEntry]:
        return [
            e
            for e in self._entries
            if any(sp.severity >= min_severity for sp in e.suspicious_points)
        ]

    def suspicious_points(self) -> list[SuspiciousPoint]:
        """所有 entry 的所有可疑点（扁平化）."""
        return [sp for e in self._entries for sp in e.suspicious_points]

    def count_by_category(self) -> dict[str, int]:
        """按 category 统计可疑点数量."""
        return dict(
            Counter(sp.category for sp in self.suspicious_points())
        )

    def count_by_tool(self) -> dict[str, int]:
        """按 tool 统计 entry 数量."""
        return dict(Counter(e.tool_name for e in self._entries))

    # ---------- 持久化 ----------
    def flush_to_jsonl(self, path: Path) -> None:
        """把所有 entries 写到 JSONL 文件（append 模式? v0.1 简化: 覆盖）.

        Args:
            path: 输出文件路径
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                d = entry.to_dict()
                # 嵌套 suspicious_points 也需序列化
                d["suspicious_points"] = [
                    {**asdict(sp), "timestamp": sp.timestamp.isoformat()}
                    for sp in entry.suspicious_points
                ]
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # ---------- 测试辅助 ----------
    def clear(self) -> None:
        self._entries.clear()


__all__ = ["Journal", "JournalEntry"]
