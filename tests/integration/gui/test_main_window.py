"""GUI 集成测试 — main window + file drop + tool selection + output + journal.

pytest-qt 必须在 conftest 或这里设置 QT_QPA_PLATFORM=offscreen。
"""

from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.suspicious import SuspiciousPoint
from automisc.gui.journal_panel import JournalPanel
from automisc.gui.main_window import MainWindow
from automisc.gui.menu_dock import TOOL_CATEGORIES, ToolMenuDock
from automisc.gui.output_view import OutputView


# ---------- fixture ----------
@pytest.fixture
def qt_app(qtbot):
    """提供 QApplication 实例 + qtbot."""
    return qtbot


@pytest.fixture
def sample_text() -> Path:
    """真实样本 fixture（PR9 创建的 sample_text.txt）."""
    return Path("tests/fixtures/sample_text.txt")


# ---------- 1. MainWindow import + instantiate ----------
class TestMainWindow:
    def test_main_window_construct(self, qtbot):
        """QMainWindow 构造无异常（PySide6 widget tree init OK）."""
        w = MainWindow()
        qtbot.addWidget(w)
        assert w.windowTitle().startswith("automisc")
        assert w.menu_dock is not None
        assert w.output_view is not None
        assert w.journal_panel is not None

    def test_main_window_accept_drops(self, qtbot):
        """拖拽 enabled."""
        w = MainWindow()
        qtbot.addWidget(w)
        assert w.acceptDrops() is True

    def test_main_window_default_status(self, qtbot):
        """默认状态栏有 Ready 文案."""
        w = MainWindow()
        qtbot.addWidget(w)
        assert "Ready" in w.statusBar().currentMessage()


# ---------- 2. Menu dock ----------
class TestToolMenuDock:
    def test_menu_categories(self, qtbot):
        """8 adapter + 1 快捷 + 2 decoder = 12 分类 (v0.5-coords-qr 新增)"""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)
        assert dock.tree.topLevelItemCount() == 12

    def test_menu_total_tools(self, qtbot):
        """22 adapter + 4 快捷 + 3 decoder = 29 (v0.5-coords-qr)."""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)
        count = 0
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            count += cat.childCount()
        assert count == 29  # 6 + 2 + 2 + 5 + 3 + 2 + 1 + 1 + 4 + 1 + 1 + 1 (coords-qr)

    def test_menu_callback(self, qtbot):
        """点击工具项触发 callback (新 signature: name, kind)."""
        selected = []
        dock = ToolMenuDock(on_tool_selected=lambda n, k: selected.append((n, k)))
        qtbot.addWidget(dock)
        # 找第一个可点击的子项
        cat = dock.tree.topLevelItem(0)
        first_child = cat.child(0)
        dock._on_item_clicked(first_child, 0)
        # 第一个 adapter = "file", kind="adapter"
        assert selected == [("file", "adapter")]

    def test_menu_tool_categories_constant(self):
        """TOOL_CATEGORIES 字典含 12 分类 29 工具 (22+4+3)."""
        assert len(TOOL_CATEGORIES) == 12
        total = sum(len(tools) for tools in TOOL_CATEGORIES.values())
        assert total == 29

    def test_menu_v5_shortcut_actions(self, qtbot):
        """v0.5 快捷工具 4 个: lsb_extract / fix_pseudo_zip / bruteforce_zip / bruteforce_rar."""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)

        # 找 "快捷工具 (v0.5 Actions)" 分类
        shortcut_cat = None
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            if "快捷工具" in cat.text(0):
                shortcut_cat = cat
                break
        assert shortcut_cat is not None, "快捷工具分类未找到"

        # 4 个 action
        action_names = []
        for i in range(shortcut_cat.childCount()):
            child = shortcut_cat.child(i)
            action_names.append(child.data(0, Qt.UserRole))

        for expected in ("lsb_extract", "fix_pseudo_zip", "bruteforce_zip", "bruteforce_rar"):
            assert expected in action_names, f"快捷工具缺 {expected}; 实际: {action_names}"

    def test_menu_v5_decoders(self, qtbot):
        """v0.5+ 解码器 2 个: base64-image / hex-ascii."""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)

        # 找 "🔓 解码工具" + "🔢 进制转换" 分类
        decoder_names = []
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            if "解码工具" in cat.text(0) or "进制转换" in cat.text(0):
                for j in range(cat.childCount()):
                    decoder_names.append(cat.child(j).data(0, Qt.UserRole))

        # base64-image 走 prefix "decoder:"
        for expected in ("decoder:base64-image", "decoder:hex-ascii"):
            assert expected in decoder_names, f"decoder 缺 {expected}; 实际: {decoder_names}"

    def test_menu_callback_kind_dispatch(self, qtbot):
        """callback kind 正确区分: adapter / action / decoder."""
        selected = []
        dock = ToolMenuDock(on_tool_selected=lambda n, k: selected.append((n, k)))
        qtbot.addWidget(dock)

        # 找 decoder:base64-image 模拟点击
        from PySide6.QtCore import QPoint
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                child = cat.child(j)
                if child.data(0, Qt.UserRole) == "decoder:base64-image":
                    dock._on_item_clicked(child, 0)
                    assert selected == [("base64-image", "decoder")]
                    return
        assert False, "decoder:base64-image 未找到"


# ---------- 3. Output view ----------
class TestOutputView:
    def test_append_text(self, qtbot):
        view = OutputView()
        qtbot.addWidget(view)
        view.append_text("hello\nworld")
        assert "hello" in view.toPlainText()
        assert "world" in view.toPlainText()

    def test_append_suspicious_severity_color(self, qtbot):
        """severity=5 应显示红色."""
        view = OutputView()
        qtbot.addWidget(view)
        sp = SuspiciousPoint(
            id="",
            tool_name="strings",
            file_path="/tmp/test.txt",
            category="flag",
            matched_pattern="flag{test}",
            severity=5,
            suggested_action="submit",
        )
        view.append_suspicious(sp)
        text = view.toPlainText()
        assert "[5]" in text
        assert "flag" in text
        assert "flag{test}" in text


# ---------- 4. Journal panel ----------
class TestJournalPanel:
    def test_add_suspicious(self, qtbot):
        panel = JournalPanel()
        qtbot.addWidget(panel)
        sp = SuspiciousPoint(
            id="",
            tool_name="strings",
            file_path="/tmp/test.txt",
            category="flag",
            matched_pattern="flag{abc}",
            severity=5,
            suggested_action="submit",
        )
        panel.add_suspicious("strings", Path("/tmp/test.txt"), sp)
        assert panel.tree.topLevelItemCount() == 1
        item = panel.tree.topLevelItem(0)
        assert item.text(panel.COL_TOOL) == "strings"
        assert item.text(panel.COL_VALUE) == "flag{abc}"
        assert item.text(panel.COL_SEV) == "5"

    def test_journal_accumulates(self, qtbot):
        """journal 累积多条."""
        panel = JournalPanel()
        qtbot.addWidget(panel)
        for i in range(5):
            sp = SuspiciousPoint(
                id="",
                tool_name="t",
                file_path="/x",
                category="test",
                matched_pattern=f"v{i}",
                severity=3,
                suggested_action="",
            )
            panel.add_suspicious("t", Path("/x"), sp)
        assert panel.tree.topLevelItemCount() == 5

    def test_journal_clear(self, qtbot):
        panel = JournalPanel()
        qtbot.addWidget(panel)
        sp = SuspiciousPoint(
            id="",
            tool_name="t",
            file_path="",
            category="x",
            matched_pattern="y",
            severity=1,
            suggested_action="",
        )
        panel.add_suspicious("t", None, sp)
        assert panel.tree.topLevelItemCount() == 1
        panel.clear()
        assert panel.tree.topLevelItemCount() == 0


# ---------- 5. End-to-end: drag file + run tool ----------
class TestEndToEnd:
    def test_drop_file_sets_current_file(self, qtbot, sample_text, tmp_path):
        """拖入文件 → current_file 设置 + output 显示."""
        w = MainWindow()
        qtbot.addWidget(w)
        # 模拟 dropEvent
        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_text))])
        event = QDropEvent(
            QPoint(0, 0),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        w.dropEvent(event)
        assert w.current_file == sample_text
        assert "drop" in w.output_view.toPlainText()
        assert str(sample_text) in w.output_view.toPlainText()

    def test_run_tool_against_sample(self, qtbot, sample_text):
        """拖入 sample + 选 strings → output 显示 flag{smoke_test_pr9_xyz}."""
        # 关键: 关 auto-run 避免 auto-run 也写 journal
        w = MainWindow(core=CoreOrchestrator())
        w._auto_run_enabled = False
        qtbot.addWidget(w)

        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_text))])
        event = QDropEvent(
            QPoint(0, 0),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        w.dropEvent(event)

        # 选 strings（PR1）→ 走 ToolRunner QThread 异步
        w._run_tool("strings")
        # 等 finished_with_result signal（runner 写 output + journal）
        qtbot.waitUntil(lambda: w.journal_panel.tree.topLevelItemCount() >= 1, timeout=5000)
        text = w.output_view.toPlainText()
        assert "strings" in text
        assert "flag{smoke_test_pr9_xyz}" in text
        # journal 也应有记录
        assert w.journal_panel.tree.topLevelItemCount() == 1
        sp_item = w.journal_panel.tree.topLevelItem(0)
        # value 列：matched_pattern + (context)；context 含原行文本
        assert "flag{smoke_test_pr9_xyz}" in sp_item.text(w.journal_panel.COL_VALUE)

    def test_run_tool_no_file(self, qtbot):
        """没选文件时点工具 → 状态栏提示."""
        w = MainWindow()
        qtbot.addWidget(w)
        w._run_tool("strings")
        assert "请先拖入" in w.statusBar().currentMessage()
        assert "[!]" in w.output_view.toPlainText()
