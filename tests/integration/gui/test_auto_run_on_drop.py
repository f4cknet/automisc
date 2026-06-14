"""e2e: 拖入文件自动跑 top 5 推荐 (v0.1.1 auto-run)"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.main_window import MainWindow


@pytest.fixture
def sample_png(tmp_path) -> Path:
    """写一个真 PNG 头."""
    p = tmp_path / "test.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\nIHDR" + b"\x00" * 200)
    return p


@pytest.fixture
def sample_text() -> Path:
    return Path("tests/fixtures/sample_text.txt")


class TestAutoRunOnDrop:
    def test_drop_triggers_auto_run(self, qtbot, sample_text):
        """拖入文件 → auto-run 启动 → chain_finished 跑完所有推荐工具."""
        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_text))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)

        # 等 chain_finished 信号 (避免 race: isRunning()=False 时 slot 还没排到事件循环)
        signal_received = {"flag": False}
        # 拿到 _auto_runner 后接信号
        qtbot.waitUntil(lambda: w._auto_runner is not None, timeout=2000)
        w._auto_runner.chain_finished.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=10000)
        QApplication.processEvents()

        # 验证 output 区有 router 推荐 + auto-run 结果
        text = w.output_view.toPlainText()
        assert "[drop]" in text
        assert "recommendations" in text
        assert "[auto-run]" in text
        assert "[auto-run done]" in text
        # flag{smoke_test_pr9_xyz} 应该被 auto-run 跑到（strings 在 top 5）
        assert "flag{smoke_test_pr9_xyz}" in text

    def test_drop_png_recommends_image_tools(self, qtbot, sample_png):
        """拖入 PNG → auto-run 应该跑 zsteg/steghide (image stego 优先)."""
        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_png))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)

        signal_received = {"flag": False}
        qtbot.waitUntil(lambda: w._auto_runner is not None, timeout=2000)
        w._auto_runner.chain_finished.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=10000)
        QApplication.processEvents()

        # 推荐 zsteg/steghide 跑过（无 fixture，zsteg 可能 exit_code != 0 但 tool 应跑过）
        text = w.output_view.toPlainText()
        # 至少看到 zsteg 或 steghide 在 output 区出现
        assert "zsteg" in text or "steghide" in text

    def test_auto_run_disabled_skips_chain(self, qtbot, sample_text):
        """auto-run 关闭 → drop 不启动 AutoRunner."""
        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w._toggle_auto_run(False)  # 关闭

        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_text))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)

        # 不应启动 auto_runner
        time.sleep(0.5)  # 等一会儿确保不会启动
        assert w._auto_runner is None
        text = w.output_view.toPlainText()
        assert "auto-run disabled" in text

    def test_journal_accumulates_from_auto_run(self, qtbot, sample_text):
        """auto-run 跑完 → journal 累积所有 suspicious points."""
        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(sample_text))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)

        signal_received = {"flag": False}
        qtbot.waitUntil(lambda: w._auto_runner is not None, timeout=2000)
        w._auto_runner.chain_finished.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=10000)
        QApplication.processEvents()

        # journal 至少 1 条 (strings 跑出 flag)
        assert w.journal_panel.tree.topLevelItemCount() >= 1
