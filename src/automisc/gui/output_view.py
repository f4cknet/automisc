"""输出区（中央 QPlainTextEdit）— 工具 stdout + suspicious_points 高亮."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint


# severity 颜色
SEVERITY_COLORS: dict[int, QColor] = {
    5: QColor(255, 64, 64),    # 致命 (flag) - 红
    4: QColor(255, 165, 0),    # 高 (webshell/加密 zip) - 橙
    3: QColor(255, 215, 0),    # 中 (隐藏文件) - 黄
    2: QColor(100, 200, 100),  # 低 - 绿
    1: QColor(150, 150, 150),  # 信息 - 灰
}


class OutputView(QPlainTextEdit):
    """automisc 输出区（中央）。

    支持：
    - append_text  普通文本
    - append_suspicious  按 severity 高亮
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Menlo", 11))
        # 深色背景便于看高亮
        self.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        self.setMaximumBlockCount(5000)  # 限制最大行数

    def append_text(self, text: str) -> None:
        """追加普通文本."""
        self.appendPlainText(text.rstrip("\n"))

    def append_suspicious(self, sp: SuspiciousPoint) -> None:
        """追加 suspicious point（按 severity 高亮）."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        color = SEVERITY_COLORS.get(sp.severity, QColor("white"))
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFontWeight(QFont.Bold)

        # 实际 schema：category + matched_pattern + context
        text = f"  [{sp.severity}] {sp.category}: {sp.matched_pattern}"
        if sp.context:
            text += f"  ({sp.context})"
        cursor.insertText(text, fmt)
        cursor.insertText("\n")

    def append_result(self, result: ToolResult) -> None:
        """完整结果输出（stdout + suspicious_points）."""
        self.append_text(f"exit_code: {result.exit_code}")
        if result.stdout:
            self.append_text(result.stdout.rstrip("\n"))
        if result.stderr:
            self.append_text(f"[stderr] {result.stderr}")
        sp_count = len(result.suspicious_points)
        self.append_text(f"suspicious_points ({sp_count}):")
        for sp in result.suspicious_points:
            self.append_suspicious(sp)
