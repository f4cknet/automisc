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
    build_zip_chain_with_bruteforce,
    find_embedded_archives,
)
from automisc.core.dag import DAG
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import list_tools
from automisc.core.router import FileRouter, RouteRecommendation

from .auto_runner import AutoRunner
from .chain_runner import ChainRunner
from .decode_runner import DecodeRunner
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
        self._decode_runner: Optional[DecodeRunner] = None  # decoder async runner (v0.5-decoder-menu)
        self._auto_runner: Optional[AutoRunner] = None  # 链式 auto-runner
        self._current_recommendations: list[RouteRecommendation] = []  # 当前文件的 router 推荐
        self._auto_run_enabled: bool = True  # 默认开启 auto-run

        self.setWindowTitle("automisc — CTF Misc 半自动化辅助工具箱")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        # 左侧菜单树
        # callback 签名 (name, kind) - kind: adapter | action | decoder
        self.menu_dock = ToolMenuDock(list_tools, on_tool_selected=self._on_dock_item_selected)
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

        # v0.5-clear-on-new-file: 拖入新文件时先清空 output, 避免旧文件的信息残留
        self._on_new_file_selected(Path(local_path), source="drop")

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

        # 跑提取 (v0.5-output-samedir: extract_dir = input 同目录)
        from automisc.core.utils.output_path import extract_dir_for
        extract_dir = extract_dir_for(self.current_file, purpose="extract")
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
                f"\n[DAG] running zip-full chain on {Path(zip_path).name} (含 bruteforce)...\n"
            )
            # v0.5-GUI-fix: 用 zip-full (含 bruteforce) 而非 zip (无 bruteforce)
            # 之前用 build_zip_chain_dag 遇到真加密 zip 永远 fail
            dag: DAG = build_zip_chain_with_bruteforce()
            ctx = dag.execute({"file_path": zip_path})
            log = ctx.get("__log__", [])
            for step in log:
                self.output_view.append_text(
                    f"  [{step['step']}] {step['node']}: {step['message']}\n"
                )
            # 渲染 flag_candidate (如果 lsb chain 抽到) - 但 zip chain 没这字段
            last_result = ctx.get("__last_result__")
            if last_result and last_result.data:
                extracted_to = last_result.data.get("extracted_to")
                if extracted_to:
                    self.output_view.append_text(
                        f"  → 解出到: {extracted_to}\n"
                    )
                    # 检查解出的目录里有没有 flag{}
                    extracted_path = Path(extracted_to)
                    if extracted_path.is_dir():
                        for f in extracted_path.rglob("*"):
                            if f.is_file():
                                try:
                                    content = f.read_text(errors="replace")
                                    if "flag{" in content or "CTF{" in content:
                                        self.output_view.append_flag_candidate(
                                            content.strip()[:200],
                                            channel=f"zip_chain/{f.name}",
                                        )
                                except Exception:
                                    pass

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
        # 5 链 + 4 快捷 action = 9 入口
        chain_menu = menubar.addMenu("&Chain")
        for chain_name in _CHAIN_NAMES:
            action = QAction(f"Run &{chain_name} chain", self)
            action.triggered.connect(
                lambda checked=False, name=chain_name: self._run_chain(name)
            )
            chain_menu.addAction(action)
        chain_menu.addSeparator()
        # v0.5 快捷 action (Owner GUI 工具栏需求)
        for action_name, display in (
            ("fix_pseudo_zip", "Fix Zip 伪加密"),
            ("bruteforce_zip", "Zip 暴力破解 (4-6 位)"),
            ("lsb_extract", "PNG LSB 智能提取"),
            ("bruteforce_rar", "RAR 暴力破解 (4-6 位)"),
        ):
            act = QAction(f"Run {display}", self)
            act.triggered.connect(
                lambda checked=False, name=action_name: self._run_chain(name)
            )
            chain_menu.addAction(act)
        chain_menu.addSeparator()
        # bruteforce 限制 (testing)
        bf_action = QAction("Run &zip-full (limit=5000)…", self)
        bf_action.triggered.connect(
            lambda checked=False: self._run_chain("zip-full", bruteforce_limit=5000)
        )
        chain_menu.addAction(bf_action)

        # Tools menu (v0.5-decoder-menu): 解码器/转换器/提取器 (CLI -> GUI 同步)
        # 从 core.decoders.registry 动态生成菜单项
        self._build_tools_menu(menubar)

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
            # v0.5-clear-on-new-file: 同 drop, 走统一入口
            self._on_new_file_selected(Path(path), source="open")

    def _on_new_file_selected(self, file_path: Path, source: str = "drop") -> None:
        """新文件拖入 / 打开时统一入口 (v0.5-clear-on-new-file).

        行为:
        1. 停止之前还在跑的 runner (auto_run / tool / chain / decoder)
        2. **清空 output 区** (避免旧文件信息残留)
        3. 设 current_file
        4. 跑 FileRouter 拿推荐
        5. auto-run 开启则启动 AutoRunner
        """
        # 1. 停所有 runner
        for runner in (self._auto_runner, self._runner, self._chain_runner, self._decode_runner):
            if runner and runner.isRunning():
                try:
                    runner.stop()
                except Exception:
                    pass
                runner.wait(2000)

        # 2. 清空 output (核心: per Owner 2026-06-14 "每次有新的 input 就要清空原来的 output")
        self.output_view.clear()
        # 清完留下 [cleared] 标记, 但 read-only 模式不便用户编辑 — 同时切到可编辑
        # 实际上用户拖入新文件后通常不会马上编辑, 保持 read-only 即可
        # 仍打 [cleared] 标记保留线索
        self.output_view.append_text(
            f"[新文件] {file_path.name}  (v0.5-clear-on-new-file 已清空旧 output)"
        )

        self.current_file = file_path
        self.statusBar().showMessage(f"已选文件: {self.current_file.name}")

        # 3. FileRouter 智能推荐
        try:
            route = FileRouter().route(self.current_file)
            self._current_recommendations = route.recommendations
            self.output_view.append_text(
                f"\n[{source}] file={self.current_file}\n"
                f"        size={route.file_size} bytes\n"
                f"        magic={route.detected_magic or 'unknown'}\n"
                f"        recommendations ({len(route.recommendations)}):\n"
            )
            for rec in route.recommendations[:5]:
                self.output_view.append_text(
                    f"          {rec.score:3d}  {rec.tool_name:15s}  {rec.reason}\n"
                )
        except Exception as e:  # noqa: BLE001
            self._current_recommendations = []
            self.output_view.append_text(
                f"\n[{source}] file={self.current_file}\n"
                f"        router error: {e}\n"
            )

        # 4. auto-run 开启则启动 AutoRunner
        if self._auto_run_enabled and self._current_recommendations:
            self.output_view.append_text(
                f"\n[auto-run] 启动串行跑 top 5 推荐工具...\n"
            )
            self._start_auto_run(self._current_recommendations)
        elif not self._auto_run_enabled:
            self.output_view.append_text(
                f"\n[auto-run disabled] 点左侧菜单手动选工具跑\n"
            )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About automisc",
            "automisc v0.1 frozen\n"
            "macOS GUI 半自动化 CTF Misc 工具箱\n"
            "22 adapter + 3 encoders",
        )

    # ---------- tool runner (async) ----------
    def _on_dock_item_selected(self, name: str, kind: str) -> None:
        """左侧工具栏点击 -> dispatch 到对应 runner.

        kind:
        - "adapter": 22 个 core.adapter 工具 (subprocess + parse)
        - "action": v0.5+ 4 快捷 action (fix_pseudo_zip / bruteforce_zip / lsb_extract / bruteforce_rar)
        - "decoder": v0.5+ decoder (base64-image / hex-ascii)
        """
        if kind == "decoder":
            self._run_decoder(name)
        else:
            # adapter + action 都走 _run_tool (action 名是 action 名, 已在 ACTION_REGISTRY)
            self._run_tool(name)

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

        # v0.5-bug-fix-3: LSB 抽到的整段 text 高亮 (整段深黄底 + 敏感词红底黄字)
        last_result = context.get("__last_result__")
        if last_result and last_result.data:
            lsb_text = last_result.data.get("lsb_text", {})
            if lsb_text and lsb_text.get("text"):
                self.output_view.append_lsb_text(
                    lsb_text["text"], channel=lsb_text.get("channel", "")
                )

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

    # ---------- decoder menu (v0.5-decoder-menu, GUI 同步 CLI) ----------
    def _build_tools_menu(self, menubar) -> None:
        """从 core.decoders.registry 动态构建 Tools 菜单.

        菜单按 category 分组 (decode / convert / extract).
        每个 decoder 一个 QAction, 触发 _run_decoder(name).
        """
        from automisc.core.decoders.registry import list_decoders_by_category

        tools_menu = menubar.addMenu("&Tools")
        grouped = list_decoders_by_category()
        for category, specs in grouped.items():
            sub_menu = tools_menu.addMenu(f"&{category.title()}")
            for spec in specs:
                act = QAction(spec.display, self)
                act.setToolTip(spec.description)
                act.triggered.connect(
                    lambda checked=False, name=spec.name: self._run_decoder(name)
                )
                sub_menu.addAction(act)
        # 兜底: 如果 registry 是空, 加 "no decoders registered" 提示
        if not grouped:
            noop = QAction("(no decoders registered)", self)
            noop.setEnabled(False)
            tools_menu.addAction(noop)

    def _run_decoder(self, decoder_name: str) -> None:
        """异步跑 decoder (v0.5-decoder-menu).

        跟 _run_chain/_run_tool 同样的并发保护:
        - 不能同时跑多个 decoder
        - 不能在 tool 跑着时跑 decoder

        v0.5-hex-ascii-fix (2026-06-14):
        - 对 hex-ascii 类 decoder: 从 input 区读 selection/最后 base 行 (text 模式)
        - 其他 decoder (e.g. base64-image): 仍走 current_file (file 模式)
        - 之前 menu 触发 hex-ascii 把 current_file (e.g. 233KB meihuai.jpg) 当 hex 解
          触发卡死 + 乱码, 因为 hex-ascii 是给"短 hex 串"设计的
        """
        if self._decode_runner and self._decode_runner.isRunning():
            self.statusBar().showMessage("前一个 decoder 还在跑，请稍等…")
            return
        if self._chain_runner and self._chain_runner.isRunning():
            self.statusBar().showMessage("前一个 chain 还在跑，请稍等…")
            return
        if self._runner and self._runner.isRunning():
            self.statusBar().showMessage("前一个 tool 还在跑，请稍等…")
            return

        # v0.5-hex-ascii-fix: text-based decoders 走 input 区, 不需要 current_file
        text_based_decoders = {"hex-ascii"}
        is_text_based = decoder_name in text_based_decoders

        if is_text_based:
            # 从 input 区抽 candidate
            candidate = self._extract_input_candidate()
            if not candidate:
                self.statusBar().showMessage(
                    "input 区为空; 请先粘贴 hex/binary/base64/base32 文本"
                )
                self.output_view.append_text(
                    f"\n=== Decoder: {decoder_name} ===\n"
                    f"[!] input 区为空, 没东西可解.\n"
                    f"  提示: 在 input 区粘贴 hex 串 (e.g. '28372c37290a') 然后再点菜单 {decoder_name}\n"
                )
                return

            self.statusBar().showMessage(
                f"running decoder={decoder_name} (text mode, len={len(candidate)})…"
            )
            self.output_view.append_text(
                f"\n=== Decoder: {decoder_name} (text mode) ===\n"
                f"  input_len: {len(candidate)} chars\n"
            )

            self._decode_runner = DecodeRunner(
                decoder_name=decoder_name,
                text=candidate,
            )
        else:
            # 传统 file-based decoder (e.g. base64-image)
            if not self.current_file:
                self.statusBar().showMessage("请先拖入或打开文件")
                self.output_view.append_text("[!] no file selected\n")
                return

            self.statusBar().showMessage(
                f"running decoder={decoder_name} on {self.current_file.name} (async)…"
            )
            self.output_view.append_text(f"\n=== Decoder: {decoder_name} ===\n")
            self.output_view.append_text(f"=== File:    {self.current_file}\n")

            self._decode_runner = DecodeRunner(
                decoder_name=decoder_name,
                file_path=str(self.current_file),
            )

        self._decode_runner.started_run.connect(self._on_decoder_started)
        self._decode_runner.finished_with_result.connect(self._on_decoder_finished)
        self._decode_runner.failed_with_error.connect(self._on_decoder_failed)
        self._decode_runner.start()

    def _extract_input_candidate(self) -> str | None:
        """从 input 区抽 candidate (selection 优先, 否则最后像 base 的行).

        复用 InputOutputView 的相同逻辑, 保证顶 bar [Hex → ASCII] 按钮和
        菜单栏 [hex-ascii] 工具行为一致.
        """
        return self.output_view.extract_base_candidate()

    def _on_decoder_started(self, decoder_name: str, file_path: str) -> None:
        self.statusBar().showMessage(
            f"running decoder={decoder_name} on {Path(file_path).name}…"
        )

    def _on_decoder_finished(
        self, decoder_name: str, file_path: str, result
    ) -> None:
        """Decoder 跑成功 → 渲染 result 字段 (类似 chain summary)."""
        self.output_view.append_text(f"\n--- decoder result ---")
        for k, v in vars(result).items():
            # 截断 input/output_text 以免爆炸
            if isinstance(v, str) and len(v) > 500:
                v = v[:500] + f"... (truncated, total {len(v)} chars)"
            self.output_view.append_text(f"  {k}: {v}")
        # 特殊: 如果 result 含 output_path, 高亮并附提示
        output_path = getattr(result, "output_path", None)
        if output_path:
            self.output_view.append_text(
                f"\n[输出文件] {output_path}\n"
                f"  └─ 可在 Finder 打开, 或用其他工具 (zbarimg / open 等) 继续处理"
            )
        self.statusBar().showMessage(f"decoder {decoder_name} done")

    def _on_decoder_failed(self, decoder_name: str, error_msg: str) -> None:
        self.output_view.append_text(
            f"[!] decoder {decoder_name} failed: {error_msg}\n"
        )
        self.statusBar().showMessage(f"decoder {decoder_name} error: {error_msg}")
