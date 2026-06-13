"""Journal 面板（底 QDockWidget）— 累积所有 suspicious_points.

设计：
- 1 个 QTreeWidget，列：time / tool / file / severity / kind / value
- 累积所有可疑点（v0.1 不分页 / 不导出）
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

    def clear(self) -> None:
        self.tree.clear()
