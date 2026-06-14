"""Journal 面板（底 QDockWidget）— 累积所有可疑点 + 工具事件.

设计：
- 1 个 QTreeWidget，列：time / tool / file / severity / kind / value
- 累积所有可疑点（v0.1 不分页 / 不导出）
- v0.5-hex-router-journal: add_event() 通用方法, 记录非可疑点事件
  (e.g. "hex_router 写文件到 /path/foo.bin"), severity=0 表示"信息"无颜色
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QHeaderView, QTreeWidget, QTreeWidgetItem

from automisc.core.suspicious import SuspiciousPoint


class JournalPanel(QDockWidget):
    """累积所有 suspicious_points 的面板."""

    COL_TIME = 0
    COL_TOOL = 1
    COL_FILE = 2
    COL_SEV = 3
    COL_KIND = 4
    COL_VALUE = 5
    COL_COUNT = 6

    def __init__(self, parent=None) -> None:
        super().__init__("Journal (可疑点累积)", parent)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(self.COL_COUNT)
        self.tree.setHeaderLabels(["Time", "Tool", "File", "Sev", "Kind", "Value"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        # 列宽
        header = self.tree.header()
        header.setSectionResizeMode(self.COL_TIME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_TOOL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_FILE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_SEV, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_KIND, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_VALUE, QHeaderView.Stretch)

        self.setWidget(self.tree)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )

    def add_suspicious(
        self, tool_name: str, file_path: Optional[Path], sp: SuspiciousPoint
    ) -> None:
        """追加一条 suspicious point 到 journal."""
        now = datetime.now().strftime("%H:%M:%S")
        file_name = file_path.name if file_path else "?"
        # value 列显示 matched_pattern + context（如有）
        display_value = sp.matched_pattern
        if sp.context:
            display_value += f"  ({sp.context})"
        item = QTreeWidgetItem(
            [now, tool_name, file_name, str(sp.severity), sp.category, display_value]
        )
        # 按 severity 设文字颜色
        if sp.severity >= 5:
            item.setForeground(self.COL_VALUE, Qt.red)
        elif sp.severity >= 4:
            item.setForeground(self.COL_VALUE, Qt.darkYellow)
        self.tree.addTopLevelItem(item)
        # 滚动到最新
        self.tree.scrollToBottom()

    def add_event(
        self,
        tool_name: str,
        kind: str,
        value: str,
        file_path: Optional[Path] = None,
        severity: int = 0,
    ) -> None:
        """追加一条非可疑点事件 (v0.5-hex-router-journal, per Owner 14:43).

        区别于 add_suspicious: 通用 entry, 不需 SuspiciousPoint, severity 默认 0 (信息).

        用例:
        - hex_router 写文件: add_event("hex->file", "hex转文件",
          "文件保存在/Users/.../hex_router_xxx.bin")
        - 未来: 工具完成 / chain 启动 / 错误等

        Args:
            tool_name: 工具名 (e.g. "hex->file", "strings", "zbar")
            kind: 事件类型 (e.g. "hex转文件", "suspicious", "error")
            value: 详情文本
            file_path: 关联文件 (None = 不显示)
            severity: 0=信息 (无颜色), 1-5=按规则着色
        """
        now = datetime.now().strftime("%H:%M:%S")
        file_name = file_path.name if file_path else "-"
        item = QTreeWidgetItem(
            [now, tool_name, file_name, str(severity), kind, value]
        )
        # 颜色
        if severity >= 5:
            item.setForeground(self.COL_VALUE, Qt.red)
        elif severity >= 4:
            item.setForeground(self.COL_VALUE, Qt.darkYellow)
        elif severity == 0:
            # 信息: 灰色, 区别于可疑点
            item.setForeground(self.COL_VALUE, Qt.gray)
        self.tree.addTopLevelItem(item)
        self.tree.scrollToBottom()

    def clear(self) -> None:
        self.tree.clear()
