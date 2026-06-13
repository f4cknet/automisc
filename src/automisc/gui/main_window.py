"""Main window — QMainWindow + file drop + 注入 Core.

设计目标（v0.1 简化范围）：
- 拖文件进窗口 → show 推荐工具列表（调 Core.route = v0.5+；v0.1 直接 list_tools）
- 点击菜单项 → 调 Core.run_tool 同步跑（v0.1 不写 QThread，简化）
- 输出区显示 stdout + suspicious_points
- journal 面板累积所有 suspicious_points

macOS only（per AGENTS.md §2.4），需 pip install -e ".[gui]"
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QStatusBar,
)

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import list_tools
from automisc.core.router import FileRouter

from .journal_panel import JournalPanel
from .menu_dock import ToolMenuDock
from .output_view import OutputView
from .runner import ToolRunner


class MainWindow(QMainWindow):
    """automisc 主窗口。

    Args:
        core: 注入的 Core 调度器（不在 GUI 内 new）
        parent: Qt parent
    """

    def __init__(self, core: Optional[CoreOrchestrator] = None, parent=None) -> None:
        super().__init__(parent)
        self.core = core or CoreOrchestrator()
        self.current_file: Optional[Path] = None
        self._runner: Optional[ToolRunner] = None  # 当前 async runner

        self.setWindowTitle("automisc — CTF Misc 半自动化辅助工具箱")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        # 左侧菜单树
        self.menu_dock = ToolMenuDock(list_tools, on_tool_selected=self._run_tool)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.menu_dock)

        # 中央输出区
        self.output_view = OutputView()
        self.setCentralWidget(self.output_view)

        # 底部标签页（output / journal）
        self.journal_panel = JournalPanel()
        self.addDockWidget(Qt.BottomDockWidgetArea, self.journal_panel)

        # 状态栏
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready · 拖入文件或点左侧菜单")

        # 简单菜单栏（File / View）
        self._build_menu_bar()

    # ---------- file drop ----------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        # v0.1 简化：取第一个文件
        first_url = urls[0]
        local_path = first_url.toLocalFile()
        if not local_path:
            return

        self.current_file = Path(local_path)
        self.statusBar().showMessage(f"已选文件: {self.current_file.name}")

        # v0.1.1：FileRouter 智能推荐（per Architecture §3.5）
        try:
            route = FileRouter().route(self.current_file)
            self.output_view.append_text(
                f"[drop] file={self.current_file}\n"
                f"        size={route.file_size} bytes\n"
                f"        magic={route.detected_magic or 'unknown'}\n"
                f"        recommendations:\n"
            )
            for rec in route.recommendations[:5]:
                self.output_view.append_text(
                    f"          {rec.score:3d}  {rec.tool_name:15s}  {rec.reason}\n"
                )
        except Exception as e:  # noqa: BLE001
            # 路由失败（如文件不可读）→ 兜底
            self.output_view.append_text(
                f"[drop] file={self.current_file}\n"
                f"        router error: {e}\n"
            )
        event.acceptProposedAction()

    # ---------- menu actions ----------
    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        open_action = QAction("&Open File…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.menu_dock.toggleViewAction())
        view_menu.addAction(self.journal_panel.toggleViewAction())

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _open_file_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "选择 CTF 题目文件")
        if path:
            self.current_file = Path(path)
            self.statusBar().showMessage(f"已选文件: {self.current_file.name}")
            self.output_view.append_text(f"[open] {self.current_file}\n")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About automisc",
            "automisc v0.1 frozen\n"
            "macOS GUI 半自动化 CTF Misc 工具箱\n"
            "22 adapter + 3 encoders",
        )

    # ---------- tool runner (async) ----------
    def _run_tool(self, tool_name: str) -> None:
        """异步跑工具（QThread 包装，不阻塞 GUI）."""
        if not self.current_file:
            self.statusBar().showMessage("请先拖入或打开文件")
            self.output_view.append_text("[!] no file selected\n")
            return

        # 防止并发跑：检查是否已有 runner 在跑
        if self._runner and self._runner.isRunning():
            self.statusBar().showMessage("前一个工具还在跑，请稍等…")
            return

        self.statusBar().showMessage(f"running {tool_name} on {self.current_file.name} (async)…")
        self.output_view.append_text(f"\n=== {tool_name} ===\n")

        # 起 QThread 跑
        self._runner = ToolRunner(self.core, tool_name, str(self.current_file))
        self._runner.started_run.connect(self._on_runner_started)
        self._runner.finished_with_result.connect(self._on_runner_finished)
        self._runner.failed_with_error.connect(self._on_runner_failed)
        self._runner.start()

    def _on_runner_started(self, tool_name: str, file_path: str) -> None:
        self.statusBar().showMessage(f"running {tool_name} on {Path(file_path).name}…")

    def _on_runner_finished(self, result) -> None:
        """ToolRunner 跑成功 → 写 output + journal."""
        # 输出 stdout（前 2000 字符，避免卡顿）
        stdout = result.stdout or ""
        if len(stdout) > 2000:
            stdout = stdout[:2000] + f"\n... (truncated, total {len(result.stdout)} chars)\n"
        self.output_view.append_text(f"exit_code: {result.exit_code}\n")
        if stdout:
            self.output_view.append_text(stdout)
        if result.stderr:
            self.output_view.append_text(f"[stderr] {result.stderr[:500]}\n")

        # 可疑点高亮
        sp_count = len(result.suspicious_points)
        self.output_view.append_text(f"suspicious_points ({sp_count}):\n")
        for sp in result.suspicious_points:
            self.output_view.append_suspicious(sp)

        # journal 累积
        for sp in result.suspicious_points:
            self.journal_panel.add_suspicious(result.tool_name, self.current_file, sp)

        self.statusBar().showMessage(
            f"done: {result.tool_name} → {sp_count} suspicious point(s)"
        )

    def _on_runner_failed(self, error_msg: str) -> None:
        self.output_view.append_text(f"[!] runner error: {error_msg}\n")
        self.statusBar().showMessage(f"error: {error_msg}")
