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

from automisc.core.chains import (
    build_zip_chain_dag,
    find_embedded_archives,
)
from automisc.core.dag import DAG
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import list_tools
from automisc.core.router import FileRouter, RouteRecommendation

from .auto_runner import AutoRunner
from .chain_runner import ChainRunner
from .journal_panel import JournalPanel
from .menu_dock import ToolMenuDock
from .output_view import OutputView
from .runner import ToolRunner


# Chain 菜单项 (v0.5 chain 系列, 与 CLI 一致)
_CHAIN_NAMES = ("zip", "zip-full", "binwalk", "foremost", "lsb")


class MainWindow(QMainWindow):
    """automisc 主窗口.

    Args:
        core: 注入的 Core 调度器（不在 GUI 内 new）
        parent: Qt parent
    """

    def __init__(self, core: Optional[CoreOrchestrator] = None, parent=None) -> None:
        super().__init__(parent)
        self.core = core or CoreOrchestrator()
        self.current_file: Optional[Path] = None
        self._runner: Optional[ToolRunner] = None  # 单工具 async runner
        self._chain_runner: Optional[ChainRunner] = None  # chain async runner (v0.5)
        self._auto_runner: Optional[AutoRunner] = None  # 链式 auto-runner
        self._current_recommendations: list[RouteRecommendation] = []  # 当前文件的 router 推荐
        self._auto_run_enabled: bool = True  # 默认开启 auto-run

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
        self.statusBar().showMessage(
            "Ready · 拖入文件自动跑 top 5 推荐 · 点左侧菜单手动跑"
        )

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

        # 停止之前的 auto_runner（如果还在跑）
        if self._auto_runner and self._auto_runner.isRunning():
            self._auto_runner.stop()
            self._auto_runner.wait(2000)

        self.current_file = Path(local_path)
        self.statusBar().showMessage(f"已选文件: {self.current_file.name}")

        # v0.1.1：FileRouter 智能推荐（per Architecture §3.5）
        try:
            route = FileRouter().route(self.current_file)
            self._current_recommendations = route.recommendations
            self.output_view.append_text(
                f"[drop] file={self.current_file}\n"
                f"        size={route.file_size} bytes\n"
                f"        magic={route.detected_magic or 'unknown'}\n"
                f"        recommendations ({len(route.recommendations)}):\n"
            )
            for rec in route.recommendations[:5]:
                self.output_view.append_text(
                    f"          {rec.score:3d}  {rec.tool_name:15s}  {rec.reason}\n"
                )
        except Exception as e:  # noqa: BLE001
            # 路由失败（如文件不可读）→ 兜底
            self._current_recommendations = []
            self.output_view.append_text(
                f"[drop] file={self.current_file}\n"
                f"        router error: {e}\n"
            )

        # v0.1.1-auto-run: auto-run 开启则自动启动 AutoRunner 跑 top 5
        if self._auto_run_enabled and self._current_recommendations:
            self.output_view.append_text(
                f"\n[auto-run] 启动串行跑 top 5 推荐工具...\n"
            )
            self._start_auto_run(self._current_recommendations)
        elif not self._auto_run_enabled:
            self.output_view.append_text(
                f"\n[auto-run disabled] 点左侧菜单手动选工具跑\n"
            )

        event.acceptProposedAction()

    # ---------- auto-run (v0.1.1 增强) ----------
    def _start_auto_run(self, recommendations: list[RouteRecommendation]) -> None:
        """启动 AutoRunner 串行跑推荐工具."""
        if self._auto_runner and self._auto_runner.isRunning():
            return  # 已有在跑
        self._auto_runner = AutoRunner(
            self.core, recommendations, str(self.current_file), max_tools=5
        )
        self._auto_runner.tool_started.connect(self._on_auto_tool_started)
        self._auto_runner.tool_finished.connect(self._on_auto_tool_finished)
        self._auto_runner.chain_finished.connect(self._on_auto_chain_finished)
        self._auto_runner.chain_failed.connect(self._on_auto_chain_failed)
        self._auto_runner.start()

    def _on_auto_tool_started(self, tool_name: str, index: int, total: int) -> None:
        self.statusBar().showMessage(
            f"[auto {index+1}/{total}] running {tool_name} on {self.current_file.name}…"
        )

    def _on_auto_tool_finished(self, tool_name: str, summary, result) -> None:
        """单个工具跑完 → 写 output + journal.

        AutoRunner 已把完整 ToolResult 传过来（避免重复跑工具）。
        """
        self.output_view.append_text(
            f"\n=== {tool_name} (auto {summary.success and 'OK' or 'FAIL'}) ===\n"
        )
        if result.stderr:
            self.output_view.append_text(f"[stderr] {result.stderr[:500]}\n")

        # 写 stdout 详情
        stdout = result.stdout or ""
        if len(stdout) > 2000:
            stdout = stdout[:2000] + f"\n... (truncated)\n"
        if stdout:
            self.output_view.append_text(stdout)

        # suspicious points
        self.output_view.append_text(
            f"exit_code: {result.exit_code} | "
            f"suspicious_points ({len(result.suspicious_points)}):\n"
        )
        for sp in result.suspicious_points:
            self.output_view.append_suspicious(sp)

        # journal 累积
        for sp in result.suspicious_points:
            self.journal_panel.add_suspicious(tool_name, self.current_file, sp)

    def _on_auto_chain_finished(self, summaries) -> None:
        """整链跑完 → 输出总结 + 检测 binwalk 输出含 archive → 触发 zip_chain."""
        total = len(summaries)
        ok = sum(1 for s in summaries if s.success)
        sps = sum(s.suspicious_count for s in summaries)
        self.output_view.append_text(
            f"\n[auto-run done] {ok}/{total} OK · {sps} suspicious points found\n"
        )
        self.statusBar().showMessage(
            f"auto-run done: {ok}/{total} OK · {sps} suspicious points"
        )

        # v0.5-DAG: 检查 binwalk 输出里是否含 embedded archive → 触发 zip_chain
        if self._current_recommendations:
            binwalk_summary = next(
                (s for s in summaries if s.tool_name == "binwalk"),
                None,
            )
            if binwalk_summary and binwalk_summary.success:
                # 从 core.journal 取 binwalk stdout
                binwalk_entries = self.core.journal.filter_by_tool("binwalk")
                if binwalk_entries:
                    last_binwalk = binwalk_entries[-1]
                    # journal 不存 stdout, 改用 ad-hoc 拿
                    self._maybe_trigger_zip_chain_from_binwalk()

    def _maybe_trigger_zip_chain_from_binwalk(self) -> None:
        """跑一次 binwalk 拿 stdout, 检测 archive, 触发 zip_chain."""
        if not self.current_file:
            return
        try:
            result = self.core.run_tool("binwalk", str(self.current_file))
        except Exception:  # noqa: BLE001
            return

        if not result.stdout:
            return

        archives = find_embedded_archives(result.stdout)
        if not archives:
            return

        # binwalk 报有 archive → 提取 + 触发 zip_chain
        self.output_view.append_text(
            f"\n[DAG trigger] binwalk 检测到 {len(archives)} 个 embedded archive:\n"
        )
        for arch in archives[:5]:
            self.output_view.append_text(f"  {arch}\n")

        # 跑提取
        extract_dir = Path("/tmp/automisc_extract")
        extract_dir.mkdir(parents=True, exist_ok=True)
        binwalk_result = result  # 已跑过
        if "extracted_files" in result.suspicious_points[0].__dict__ if result.suspicious_points else False:
            pass  # binwalk 没暴露 extracted files via sps; 用 tool 直接抽取

        # 跑 binwalk_extract
        from automisc.core.actions.binwalk_extract import BinwalkExtractAction

        binwalk_extract = BinwalkExtractAction()
        extract_result = binwalk_extract.run(
            {"file_path": str(self.current_file), "extract_dir": str(extract_dir)}
        )
        if not extract_result.success:
            self.output_view.append_text(
                f"[!] binwalk extract failed: {extract_result.message}\n"
            )
            return

        extracted_files = extract_result.data.get("extracted_files", [])
        zip_files = [
            f for f in extracted_files
            if f.lower().endswith((".zip",))
        ]
        if not zip_files:
            self.output_view.append_text(
                f"[!] no .zip file among {len(extracted_files)} extracted files\n"
            )
            return

        # 对每个 zip 跑 chain
        for zip_path in zip_files[:3]:  # 限制 3 个
            self.output_view.append_text(
                f"\n[DAG] running zip_chain on {Path(zip_path).name}...\n"
            )
            dag: DAG = build_zip_chain_dag()
            ctx = dag.execute({"file_path": zip_path})
            log = ctx.get("__log__", [])
            for step in log:
                self.output_view.append_text(
                    f"  [{step['step']}] {step['node']}: {step['message']}\n"
                )

    def _on_auto_chain_failed(self, tool_name: str, error_msg: str) -> None:
        self.output_view.append_text(
            f"[!] auto-run chain failed at {tool_name}: {error_msg}\n"
        )

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

        # Run menu (v0.1.1 auto-run 切换)
        run_menu = menubar.addMenu("&Run")
        self.auto_run_action = QAction("&Auto-run on drop", self)
        self.auto_run_action.setCheckable(True)
        self.auto_run_action.setChecked(self._auto_run_enabled)
        self.auto_run_action.toggled.connect(self._toggle_auto_run)
        run_menu.addAction(self.auto_run_action)

        # Chain menu (v0.5 chain 系列, 同步 CLI)
        # 5 个入口: zip / zip-full / binwalk / foremost / lsb
        chain_menu = menubar.addMenu("&Chain")
        for chain_name in _CHAIN_NAMES:
            action = QAction(f"Run &{chain_name} chain", self)
            action.triggered.connect(
                lambda checked=False, name=chain_name: self._run_chain(name)
            )
            chain_menu.addAction(action)
        chain_menu.addSeparator()
        # bruteforce 限制 (testing)
        bf_action = QAction("Run &zip-full (limit=5000)…", self)
        bf_action.triggered.connect(
            lambda checked=False: self._run_chain("zip-full", bruteforce_limit=5000)
        )
        chain_menu.addAction(bf_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _toggle_auto_run(self, checked: bool) -> None:
        self._auto_run_enabled = checked
        status = "ON" if checked else "OFF"
        self.statusBar().showMessage(f"auto-run: {status} (拖文件{'自动跑' if checked else '手动选'})")

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

    # ---------- chain runner (v0.5 GUI 同步 CLI) ----------
    def _run_chain(self, chain_name: str, bruteforce_limit: int | None = None) -> None:
        """异步跑 chain (QThread 包装 DAG, 跟 CLI 一致).

        Args:
            chain_name: zip / zip-full / binwalk / foremost / lsb
            bruteforce_limit: bruteforce 测试用 (e.g. 5000), 加速 CI/开发
        """
        if not self.current_file:
            self.statusBar().showMessage("请先拖入或打开文件")
            self.output_view.append_text("[!] no file selected\n")
            return

        # 防止并发跑: 检查是否已有 runner 在跑
        if self._chain_runner and self._chain_runner.isRunning():
            self.statusBar().showMessage("前一个 chain 还在跑，请稍等…")
            return
        if self._runner and self._runner.isRunning():
            self.statusBar().showMessage("前一个 tool 还在跑，请稍等…")
            return

        self.statusBar().showMessage(
            f"running chain={chain_name} on {self.current_file.name} (async)…"
        )
        self.output_view.append_text(
            f"\n=== Chain: {chain_name} ===\n"
        )
        self.output_view.append_text(f"=== File:  {self.current_file}\n")

        # 起 QThread 跑
        self._chain_runner = ChainRunner(
            chain_name=chain_name,
            file_path=str(self.current_file),
            bruteforce_limit=bruteforce_limit,
        )
        self._chain_runner.started_run.connect(self._on_chain_started)
        self._chain_runner.finished_with_context.connect(self._on_chain_finished)
        self._chain_runner.failed_with_error.connect(self._on_chain_failed)
        self._chain_runner.start()

    def _on_chain_started(self, chain_name: str, file_path: str) -> None:
        self.statusBar().showMessage(
            f"running chain={chain_name} on {Path(file_path).name}…"
        )

    def _on_chain_finished(self, chain_name: str, file_path: str, context: dict) -> None:
        """ChainRunner 跑成功 → 渲染 log + summary + flag_candidate."""
        log = context.get("__log__", [])
        self.output_view.append_text(f"\n--- chain log ({len(log)} steps) ---")
        self.output_view.append_chain_log(log)
        self.output_view.append_chain_summary(context)

        # journal 累积 (suspicious points from all steps)
        for step in log:
            step_name = step["node"]
            step_data = context.get(f"__step_{step['step']}_{step_name}__", {})
            # 把 step 视为工具结果
            if step_data:
                # 当前 step 没存 suspicious_points, 但 last_result.data 里有 flag_candidate
                # 给 journal 加一条 chain summary 记录
                last_result = context.get("__last_result__")
                if last_result and last_result.data:
                    flag_candidate = last_result.data.get("flag_candidate")
                    if flag_candidate and step_name == "lsb_extract":
                        from automisc.core.suspicious import SuspiciousPoint
                        sp = SuspiciousPoint(
                            id="",
                            tool_name=f"chain/{chain_name}/{step_name}",
                            file_path=file_path,
                            category="lsb_text",
                            offset=None,
                            matched_pattern=flag_candidate[:120],
                            severity=5,
                            suggested_action="LSB text 含敏感关键词 (key/flag/secret/ctf/password)",
                        )
                        self.journal_panel.add_suspicious(
                            f"chain/{chain_name}", Path(file_path), sp
                        )

        # 状态
        total = len(log)
        ok = sum(1 for s in log if s.get("success"))
        self.statusBar().showMessage(
            f"chain={chain_name} done: {ok}/{total} OK"
        )

    def _on_chain_failed(self, chain_name: str, error_msg: str) -> None:
        self.output_view.append_text(
            f"[!] chain {chain_name} failed: {error_msg}\n"
        )
        self.statusBar().showMessage(f"chain {chain_name} error: {error_msg}")
