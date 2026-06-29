"""v0.5-journal-clear-on-new-file 单测 (per Owner 2026-06-29 21:53 拍板)

触发背景: Owner 拖入 zip 文件看到 `=== steghide (auto FAIL) ===`, 误以为是这次
auto-run 跑了 steghide. 实际根因是 journal_panel 累积了上次拖 jpg 跑过的 steghide
SP 残留, 拖新文件时未清空, Owner 看 journal 误读.

修: MainWindow._on_new_file_selected 调 self.output_view.clear() 之后加
    self.journal_panel.clear(), output 区文案 "已清空旧 output" 改 "+ journal".

测试覆盖:
- 拖文件后 journal_panel.tree 0 item
- File→Open 也走同一清空路径 (复用 _on_new_file_selected)
- 旧 journal SP (模拟 steghide FAIL 残留) 拖新文件后全清
- 跟 output_view.clear() 行为对齐 (一个文件一份干净视图)
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from automisc.core.suspicious import SuspiciousPoint
from automisc.gui.main_window import MainWindow
from automisc.gui.journal_panel import JournalPanel


# ---------- helper: 模拟"上一次的 journal 残留" ----------

def _seed_journal_with_old_sp(journal: JournalPanel, file_name: str) -> None:
    """往 journal 灌 3 条旧 SP, 模拟 Owner 之前拖图跑过的累积."""
    # 模拟之前拖 jpg 时 steghide FAIL 留下的 SP (v0.5-train-015 实战模式)
    journal.add_event(
        tool_name="steghide",
        kind="auto FAIL",
        value="subprocess timeout after 30.0s",
        file_path=Path(file_name),
        severity=1,
    )
    # 模拟之前拖 jpg 时 strings 命中
    journal.add_suspicious(
        "strings",
        Path(file_name),
        SuspiciousPoint(
            id="",
            tool_name="strings",
            file_path=file_name,
            category="flag_candidate",
            offset=0,
            matched_pattern="flag{old_file}",
            severity=5,
            suggested_action="",
        ),
    )
    # 模拟之前拖 jpg 时 exiftool 命中
    journal.add_event(
        tool_name="exiftool",
        kind="metadata",
        value="Camera: Canon EOS R5",
        file_path=Path(file_name),
        severity=0,
    )


# ---------- 1. dropEvent 后 journal 清空 ----------

class TestDropClearsJournal:
    def test_drop_event_clears_old_journal(self, qtbot, tmp_path):
        """拖新文件时同步清 journal_panel (跟 output_view 行为对齐)."""
        # 准备文件
        first_file = tmp_path / "first.jpg"
        first_file.write_bytes(b"\xff\xd8\xff\xe0fake jpg for journal seed\n")
        second_file = tmp_path / "second.zip"
        second_file.write_bytes(b"PK\x03\x04fake zip\n")

        w = MainWindow()
        qtbot.addWidget(w)

        # 1. 模拟"上一次的 journal 残留" (Owner 之前拖 jpg 跑过 steghide)
        _seed_journal_with_old_sp(w.journal_panel, "first.jpg")
        assert w.journal_panel.tree.topLevelItemCount() == 3, \
            "seed 应灌 3 条 SP 到 journal"
        QApplication.processEvents()

        # 2. 拖入新文件 (zip)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(second_file))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)
        QApplication.processEvents()

        # 3. 验证: journal 已清空 (跟 output_view.clear() 行为对齐)
        assert w.journal_panel.tree.topLevelItemCount() == 0, \
            f"拖新文件后 journal 应清空, 实际残留 {w.journal_panel.tree.topLevelItemCount()} 条 SP"

    def test_drop_marker_mentions_journal_cleared(self, qtbot, tmp_path):
        """[新文件] 标记文案应包含 'journal' (用户线索: 不止 output 清了, journal 也清了)."""
        target = tmp_path / "test.zip"
        target.write_bytes(b"PK\x03\x04fake\n")

        w = MainWindow()
        qtbot.addWidget(w)
        w._on_new_file_selected(target, source="drop")

        out = w.output_view.toPlainText()
        assert "已清空旧 output + journal" in out, \
            f"[新文件] 标记应提及 journal 已清: {out[:200]}"


# ---------- 2. File→Open 也走同一清空路径 ----------

class TestOpenDialogClearsJournal:
    def test_open_file_dialog_clears_journal(self, qtbot, tmp_path, monkeypatch):
        """File→Open File... 同样清空旧 journal (复用 _on_new_file_selected)."""
        second_file = tmp_path / "second.zip"
        second_file.write_bytes(b"PK\x03\x04hello\n")

        w = MainWindow()
        qtbot.addWidget(w)

        # 1. 模拟 journal 残留
        _seed_journal_with_old_sp(w.journal_panel, "first.jpg")
        assert w.journal_panel.tree.topLevelItemCount() == 3

        # 2. monkeypatch QFileDialog 返回 second_file 路径
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *args, **kwargs: (str(second_file), "")),
        )
        w._open_file_dialog()
        QApplication.processEvents()

        # 3. journal 应清空
        assert w.journal_panel.tree.topLevelItemCount() == 0, \
            f"File→Open 后 journal 应清空, 实际残留 {w.journal_panel.tree.topLevelItemCount()} 条 SP"


# ---------- 3. 实战回归: steghide FAIL 残留不应在第二次拖文件后看到 ----------

class TestSteghideFailureNotResidual:
    def test_old_steghide_failure_not_visible_after_new_drop(self, qtbot, tmp_path):
        """实战回归 (per Owner 2026-06-29 21:47 BUG): 上次拖 jpg 的 steghide (auto FAIL)
        残留 SP, 拖新文件后不应在 journal 里看到, 避免做题人误以为是当前文件线索."""
        old_jpg = tmp_path / "old.jpg"
        old_jpg.write_bytes(b"\xff\xd8\xff\xe0old jpg with steghide\n")
        new_zip = tmp_path / "new.zip"
        new_zip.write_bytes(b"PK\x03\x04new zip without steghide\n")

        w = MainWindow()
        qtbot.addWidget(w)

        # 1. 模拟"上次拖 jpg 的 steghide FAIL" 残留
        #    (per v0.5-train-015: steghide 30s timeout, exit_code 124)
        w.journal_panel.add_event(
            tool_name="steghide",
            kind="auto FAIL",
            value="=== steghide (auto FAIL) ===\n[stderr] subprocess timeout after 30.0s\nexit_code: 124 | suspicious_points (0):",
            file_path=old_jpg,
            severity=1,
        )
        # 也加一条 steghide extracted 之类的 SP (如果有的话)
        w.journal_panel.add_suspicious(
            "steghide",
            old_jpg,
            SuspiciousPoint(
                id="",
                tool_name="steghide",
                file_path=str(old_jpg),
                category="steghide_embedded",
                offset=0,
                matched_pattern="could not get terminal attributes",
                severity=5,
                suggested_action="GUI 工具栏 Steghide 子菜单手工提取",
            ),
        )
        assert w.journal_panel.tree.topLevelItemCount() == 2

        # 2. 拖入新文件 (zip)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(new_zip))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)
        QApplication.processEvents()

        # 3. 验证: steghide 残留 0 条
        assert w.journal_panel.tree.topLevelItemCount() == 0, \
            f"上次拖 jpg 的 steghide 残留应为 0, 实际 {w.journal_panel.tree.topLevelItemCount()} 条"

        # 4. 拖入新文件后, auto-run 跑 archive pool 不应跑 steghide
        #    (per v0.5-philosophy-rethink archive pool 不含 steghide, 跟本 spec 独立)
        #    这里只验 journal 已清; auto-run 行为由 test_find_suspicious_runner 覆盖
