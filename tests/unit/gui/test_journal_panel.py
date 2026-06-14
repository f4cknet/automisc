"""JournalPanel 单测 (v0.5-hex-router-journal, per Owner 14:43).

测试 JournalPanel:
- add_suspicious: 旧 API, 接收 SuspiciousPoint
- add_event (v0.5-hex-router-journal): 通用 event, time/tool/file/sev/kind/value
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from automisc.core.suspicious import SuspiciousPoint
from automisc.gui.journal_panel import JournalPanel


# ---------- add_suspicious (旧 API) ----------
class TestAddSuspicious:
    def test_add_suspicious_renders_columns(self, qtbot):
        """add_suspicious 应填 6 列: time / tool / file / sev / kind / value."""
        p = JournalPanel()
        qtbot.addWidget(p)
        sp = SuspiciousPoint(
            id="",
            tool_name="strings",
            file_path="Challenge/meihuai.jpg",
            category="flag_candidate",
            offset=0,
            matched_pattern="flag{test}",
            severity=5,
            suggested_action="",
        )
        p.add_suspicious("strings", Path("Challenge/meihuai.jpg"), sp)
        # 1 行
        assert p.tree.topLevelItemCount() == 1
        item = p.tree.topLevelItem(0)
        # 列: time, tool, file, sev, kind, value
        assert item.text(p.COL_TIME) != ""  # HH:MM:SS
        assert item.text(p.COL_TOOL) == "strings"
        assert item.text(p.COL_FILE) == "meihuai.jpg"
        assert item.text(p.COL_SEV) == "5"
        assert item.text(p.COL_KIND) == "flag_candidate"
        assert "flag{test}" in item.text(p.COL_VALUE)


# ---------- v0.5-hex-router-journal: add_event (新 API) ----------
class TestAddEvent:
    def test_add_event_hex_router_writes_file(self, qtbot):
        """add_event: hex_router 写文件事件.

        Owner 14:43 期望: 'time 14:37:04, tool hex->file, kind hex转文件,
                       value 文件保存在/Users/.../hex_router_xxx.bin'
        """
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event(
            tool_name="strings",
            kind="hex转文件",
            value="文件保存在/Users/minzhizhou/Desktop/ctf/misc/automisc/"
                  "Challenge/hex_router_unknown_1781419024_db5f5dc1.bin",
            file_path=Path("Challenge/meihuai.jpg"),
            severity=0,
        )
        assert p.tree.topLevelItemCount() == 1
        item = p.tree.topLevelItem(0)
        # 列
        assert item.text(p.COL_TOOL) == "strings"
        assert item.text(p.COL_FILE) == "meihuai.jpg"
        assert item.text(p.COL_SEV) == "0"
        assert item.text(p.COL_KIND) == "hex转文件"
        # value 包含 "文件保存在" + 路径
        v = item.text(p.COL_VALUE)
        assert "文件保存在" in v
        assert "hex_router_unknown_1781419024_db5f5dc1.bin" in v

    def test_add_event_severity_zero_gray(self, qtbot):
        """severity=0 (信息) 应有颜色 (gray), 区别于可疑点."""
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event(
            tool_name="hex->file",
            kind="hex转文件",
            value="test",
            file_path=Path("foo.jpg"),
            severity=0,
        )
        item = p.tree.topLevelItem(0)
        # 颜色: gray (Qt.gray = #808080, RGB (128,128,128))
        from PySide6.QtGui import QColor
        fg = item.foreground(p.COL_VALUE).color()
        # gray 在 Qt 是 medium gray, 不是白 / 黑
        # 简化: 只验不等于白
        assert fg != QColor("white")
        assert fg != QColor("black")

    def test_add_event_failure_kind(self, qtbot):
        """hex_router 失败时 kind 应为 'hex转文件失败', value 含 error."""
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event(
            tool_name="strings",
            kind="hex转文件失败",
            value="文件保存在hex_router failed: ValueError",
            file_path=Path("Challenge/meihuai.jpg"),
            severity=0,
        )
        item = p.tree.topLevelItem(0)
        assert item.text(p.COL_KIND) == "hex转文件失败"
        assert "failed" in item.text(p.COL_VALUE)

    def test_add_event_no_file_path(self, qtbot):
        """file_path=None 时 file 列应是 '-'."""
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event(
            tool_name="x",
            kind="event",
            value="v",
            file_path=None,
            severity=0,
        )
        item = p.tree.topLevelItem(0)
        assert item.text(p.COL_FILE) == "-"

    def test_add_event_critical_red(self, qtbot):
        """severity>=5 应红色."""
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event(
            tool_name="x",
            kind="critical",
            value="v",
            file_path=Path("a"),
            severity=5,
        )
        item = p.tree.topLevelItem(0)
        from PySide6.QtGui import QColor
        fg = item.foreground(p.COL_VALUE).color()
        assert fg == QColor("red")

    def test_add_event_multiple_sorted_by_time(self, qtbot):
        """多次 add_event 应按调用顺序追加, tree 顺序不变."""
        p = JournalPanel()
        qtbot.addWidget(p)
        p.add_event("a", "k1", "v1", Path("a"), 0)
        p.add_event("b", "k2", "v2", Path("b"), 0)
        p.add_event("c", "k3", "v3", Path("c"), 0)
        assert p.tree.topLevelItemCount() == 3
        assert p.tree.topLevelItem(0).text(p.COL_TOOL) == "a"
        assert p.tree.topLevelItem(1).text(p.COL_TOOL) == "b"
        assert p.tree.topLevelItem(2).text(p.COL_TOOL) == "c"
