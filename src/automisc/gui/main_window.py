"""Main window — QMainWindow + file drop + 注入 Core.

设计目标（v0.1 简化范围）：
- 拖文件进窗口 → show 推荐工具列表（调 Core.route = v0.5+；v0.1 直接 list_tools）
- 点击菜单项 → 调 Core.run_tool 同步跑（v0.1 不写 QThread，简化）
- 输出区显示 stdout + suspicious_points
- journal 面板累积所有 suspicious_points

macOS only（per AGENTS.md §2.4），需 pip install -e ".[gui]"

**v0.5-coords-qr-fix (2026-06-14 11:46)**: 显式 import `automisc.core.decoders` 触发
`__init__.py` 里的 side-effect (注册所有 decoder module).
- 之前只 import `automisc.core.decoders.registry` 不会触发 base64_image / base_convert / coords_to_qr 注册
- 后果: GUI 菜单栏 [coords-qr] 触发时 DecodeRunner 报 "unknown decoder: coords-qr"
"""

from __future__ import annotations

# 显式 import 触发所有 decoder module 注册 (side-effect import)
# 见 core.decoders.__init__.py: base64_image / base_convert / coords_to_qr
from automisc.core import decoders as _decoders  # noqa: F401  # noqa: E402

# v0.5-journal-highlight-keywords-Q7 (per Owner 2026-06-16 17:00):
# GUI 启动时 setup_logging 已在 __main__.py 调过, 这里拿 logger.
from automisc.core.logging_setup import get_logger  # noqa: E402

log = get_logger(__name__)

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStatusBar,
)

from automisc.core.chains import (
    build_zip_chain_dag,
    build_zip_chain_with_bruteforce,
    # v0.5-philosophy-rethink 删 find_embedded_archives (per owner 决策 4):
    # 之前 _maybe_trigger_zip_chain_from_binwalk 用, 现在函数删了
)
from automisc.core.dag import DAG
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import list_tools
from automisc.core.router import FileRouter, RouteRecommendation

from .auto_runner import (
    AutoRunner,
    FindSuspiciousRunner,
    pick_suspicious_pool,
)
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
        self._auto_runner: Optional[AutoRunner] = None  # legacy auto-runner (向后兼容, 当前未使用)
        self._find_suspicious_runner: Optional[FindSuspiciousRunner] = None  # v0.5-philosophy-rethink 新 auto-runner
        self._current_recommendations: list[RouteRecommendation] = []  # 当前文件的 router 推荐 (仅展示用)
        self._auto_run_enabled: bool = True  # 默认开启 auto-run
        # v0.5-tmp-text-mode: text-based decoder GUI 弹 QFileDialog 时记住用户选
        self.output_dir_for_text_decoder: str = str(Path.cwd())  # 默认 cwd

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

        # v0.5-journal-highlight-keywords-Q7 (per Owner 2026-06-16 17:00):
        # 拖入即打 log, 卡死时 tail -f 能看到这一步发生过.
        log.info("dropEvent: file=%s", local_path)

        # v0.5-clear-on-new-file: 拖入新文件时先清空 output, 避免旧文件的信息残留
        self._on_new_file_selected(Path(local_path), source="drop")

        event.acceptProposedAction()

    # ---------- auto-run (v0.1.1 增强) ----------
    def _start_auto_run(self, recommendations: list[RouteRecommendation]) -> None:
        """启动 AutoRunner 串行跑推荐工具."""
        log.info("_start_auto_run: ENTER")
        if self._auto_runner and self._auto_runner.isRunning():
            log.info("_start_auto_run: skip, AutoRunner already running")
            return  # 已有在跑
        log.info(
            "_start_auto_run: file=%s, %d recommendations, max_tools=8",
            self.current_file, len(recommendations),
        )
        log.info("_start_auto_run: building AutoRunner instance")
        self._auto_runner = AutoRunner(
            self.core, recommendations, str(self.current_file), max_tools=8
        )
        log.info("_start_auto_run: connecting signals")
        self._auto_runner.tool_started.connect(self._on_auto_tool_started)
        self._auto_runner.tool_finished.connect(self._on_auto_tool_finished)
        self._auto_runner.chain_finished.connect(self._on_auto_chain_finished)
        self._auto_runner.chain_failed.connect(self._on_auto_chain_failed)
        self._auto_runner.short_circuited.connect(self._on_auto_short_circuited)
        log.info("_start_auto_run: calling .start()")
        self._auto_runner.start()
        log.info("_start_auto_run: .start() returned, QThread should be running")

    # ---------- v0.5-philosophy-rethink: find_suspicious_from_<type> ----------
    def _start_find_suspicious(self, file_path: Path) -> None:
        """启动 FindSuspiciousRunner 跑 find_suspicious_from_<type> 工具池.

        与 _start_auto_run 区别:
        - 不接 recommendations, 改为按扩展名选 pool
        - pool 工具池固定 (per FIND_SUSPICIOUS_*_TOOLS), 不取 top 5 score
        - **不**触发任何 chain (auto_run 抢 flag 是 owner 决策 1 禁忌)
        - Signal 接口与 AutoRunner 一致, 复用现有 handler

        Args:
            file_path: 当前文件路径 (已在 _on_new_file_selected 里检查存在性)
        """
        log.info("_start_find_suspicious: ENTER, file=%s", file_path)
        if self._find_suspicious_runner and self._find_suspicious_runner.isRunning():
            log.info("_start_find_suspicious: skip, runner already running")
            return
        self._find_suspicious_runner = FindSuspiciousRunner(self.core, str(file_path))
        self._find_suspicious_runner.pool_selected.connect(self._on_find_pool_selected)
        self._find_suspicious_runner.tool_started.connect(self._on_auto_tool_started)
        self._find_suspicious_runner.tool_finished.connect(self._on_auto_tool_finished)
        self._find_suspicious_runner.chain_finished.connect(self._on_auto_chain_finished)
        self._find_suspicious_runner.chain_failed.connect(self._on_auto_chain_failed)
        log.info("_start_find_suspicious: calling .start()")
        self._find_suspicious_runner.start()
        log.info("_start_find_suspicious: .start() returned")

    def _on_find_pool_selected(self, pool_name: str, tools: list[str]) -> None:
        """pool 选定后, 状态栏 + output 区打一行."""
        self.statusBar().showMessage(
            f"[auto-run] pool={pool_name}, {len(tools)} tools: {tools}"
        )

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

        # v0.5-hex-router-journal (per Owner 14:43):
        # 工具写的副作用文件 (e.g. hex_router saved 路径) 推到 journal_panel,
        # **不**再混在 stdout / output 区. 格式:
        #   time, tool, file, sev=0, kind="hex转文件", value="文件保存在/path"
        # 同时 status bar 弹 8s 提示 (除 journal 外的 GUI 可见)
        written_files = result.metadata.get("written_files", []) if result.metadata else []
        if written_files:
            # status bar: 弹最后一条
            last = written_files[-1]
            self.statusBar().showMessage(
                f"auto-run 写文件: {last['path']}", 8000
            )
            # journal: 每条都记
            for wf in written_files:
                self.journal_panel.add_event(
                    tool_name=wf.get("source", tool_name),
                    kind=wf["kind"],
                    value=f"文件保存在{wf['path']}" if "失败" not in wf["kind"]
                          else wf["path"],
                    file_path=self.current_file,
                    severity=0,  # 信息级, 灰色
                )

    def _on_auto_chain_finished(self, summaries) -> None:
        """整链跑完 → 输出总结 + 检测 binwalk 输出含 archive → 触发 zip_chain.

        v0.5-journal-highlight-keywords (per Owner 2026-06-16):
        - 整链跑完时, 调 journal_panel.add_sensitive_keyword_hints()
          把所有 SP 命中 secret/key/password/pass/flag/ctf 的片段写到 journal
          (kind="密码线索候选", severity=0 信息级)
        """
        total = len(summaries)
        ok = sum(1 for s in summaries if s.success)
        sps = sum(s.suspicious_count for s in summaries)
        self.output_view.append_text(
            f"\n[auto-run done] {ok}/{total} OK · {sps} suspicious points found\n"
        )
        self.statusBar().showMessage(
            f"auto-run done: {ok}/{total} OK · {sps} suspicious points"
        )

        # v0.5-journal-highlight-keywords: 归集密码线索
        try:
            # 从 core.journal 拿刚跑完的工具的 SuspiciousPoint
            results_for_hints = []
            seen_tools: set[str] = set()
            for summary in summaries:
                if summary.tool_name in seen_tools:
                    continue
                seen_tools.add(summary.tool_name)
                # 从 core.journal 取最后一次该工具的 ToolResult
                entries = self.core.journal.filter_by_tool(summary.tool_name)
                if entries:
                    # 拿最近的 entry (但 journal 不存完整 ToolResult, 改用 SP list 重组)
                    # 简化: 让 _run_tool 重新跑是不合理的, 直接从 journal 拿 SP list
                    sps_for_tool = [e.suspicious_point for e in entries if hasattr(e, "suspicious_point") and e.suspicious_point]
                    if sps_for_tool:
                        from automisc.core.result import ToolResult
                        results_for_hints.append(
                            ToolResult(
                                tool_name=summary.tool_name,
                                exit_code=0,
                                suspicious_points=sps_for_tool,
                            )
                        )
            if results_for_hints:
                n = self.journal_panel.add_sensitive_keyword_hints(
                    results_for_hints, self.current_file
                )
                if n:
                    self.output_view.append_text(
                        f"\n[journal] 归集 {n} 条密码线索候选 (secret/key/password/pass/flag/ctf) → 见下方 journal\n"
                    )
        except Exception as e:  # noqa: BLE001
            # 归集失败不影响主流程
            pass

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
                    # v0.5-philosophy-rethink 删 _maybe_trigger_zip_chain_from_binwalk 调用
                    # (per owner 决策: auto_run 不该触发链/雕文件, 做题人自己判断下一步)
                    # binwalk SP 已写 journal, 做题人可看 journal 决定是否点工具栏 fix_pseudo_zip

    # v0.5-philosophy-rethink 删 _maybe_trigger_zip_chain_from_binwalk (per owner 决策 4):
    # auto_run 跑 binwalk → 自动跑 binwalk -e 提取 → 自动触发 zip chain = 抢 flag
    # 新设计: binwalk SP 写 journal 即可, 做题人自己看 journal 决定下一步
    # (点工具栏 fix_pseudo_zip 按钮 / 或 CLI: automisc chain --chain zip 手工触发)

    def _on_auto_chain_failed(self, tool_name: str, error_msg: str) -> None:
        self.output_view.append_text(
            f"[!] auto-run chain failed at {tool_name}: {error_msg}\n"
        )

    def _on_auto_short_circuited(self, tool_name: str, reason: str) -> None:
        """v0.5-short-circuit: 命中 severity>=5, 终止后续 tools."""
        self.output_view.append_text(
            f"\n[short-circuit] {tool_name} {reason}\n"
            f"  └─ 后续 tools 跳过, auto-run 结束\n"
        )
        self.statusBar().showMessage(
            f"auto-run short-circuited at {tool_name}: 已命中关键线索"
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

        # v0.5-steghide-GUI (per Owner 2026-06-20 13:48 拍板 "submenu" + 13:57 拍板
        # "steghide 平替为 stegseek, menu 名也要换"):
        # Stegseek 子菜单 — 3 模式入口 (原 "Steghide" 已重命名, 跟 stegseek 平替一致)
        # 1) 自动检测 (空 wordlist) — 走 StegseekCrackAction + 空 wordlist
        # 2) 暴力破解 (带 wordlist) — QFileDialog 收 wordlist → StegseekCrackAction
        # 3) 指定密码提取 — QInputDialog 收 password → SteghideExtractAction (stegseek 优先)
        # (左侧 ToolMenuDock 入口现已改为 "stegseek" (平替 steghide, per Owner 2026-06-20 13:57)
        #  adapter name 已统一为 "stegseek", pool/router/menu_dock 也都改了)
        stegseek_menu = chain_menu.addMenu("Stegseek")
        auto_act = QAction("自动检测 (空 wordlist)", self)
        auto_act.triggered.connect(self._run_steghide_auto)
        stegseek_menu.addAction(auto_act)

        crack_act = QAction("暴力破解 (带 wordlist)", self)
        crack_act.triggered.connect(self._run_stegseek_crack)
        stegseek_menu.addAction(crack_act)

        extract_act = QAction("指定密码提取", self)
        extract_act.triggered.connect(self._run_steghide_extract)
        stegseek_menu.addAction(extract_act)

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
        for runner in (
            self._find_suspicious_runner,
            self._auto_runner,
            self._runner,
            self._chain_runner,
            self._decode_runner,
        ):
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

        # 4. auto-run 开启则启动 (per v0.5-philosophy-rethink, 2026-06-20)
        if self._auto_run_enabled and self.current_file:
            # v0.5-philosophy-rethink (per Owner 2026-06-20 11:49 + 12:02 拍板 C 哲学):
            # 之前 auto-run 对 .zip 自动触发 zip 链 (build_zip_chain_dag) — 违背新哲学 "auto_run 不抢 flag"
            # 之前 auto-run 对 .rar / .7z 留接口, 跟 .zip 走 archive_chain_map — 同上违背
            # 新设计: auto_run 改名 find_suspicious_from_<type>, 按扩展名选工具池
            # - picture (.png/.jpg/.jpeg/.bmp/.gif): zsteg/exiftool/binwalk/strings/file
            # - traffic (.pcap/.pcapng): pcap_protocol_router/tshark/strings/file
            # - archive (.zip/.7z/.rar/.tar/.gz): sevenz/unzip/file/strings
            # - binary (.exe/.dll/.elf/.bin + 默认兜底): file/strings/binwalk/exiftool
            # 4 池都**不**含 foremost / binwalk_extract / steghide_extract / john / fix_pseudo / bruteforce
            # (这些"雕/修/爆"操作留给 GUI 工具栏 / CLI 链手工触发, per owner C 哲学)
            pool_name, tools = pick_suspicious_pool(str(self.current_file))
            self.output_view.append_text(
                f"\n[auto-run] 启动 find_suspicious_from_{pool_name}, 跑 {len(tools)} 个工具: {tools}\n"
                f"  (纯探测, 不雕不修不爆; 做题人看 journal 决定下一步)\n"
            )
            self._start_find_suspicious(self.current_file)
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

        v0.5-action-dispatch-fix (per Owner 15:43):
        之前 action 也走 _run_tool, 但 core.run_tool 只看 adapter registry,
        报 ToolNotFoundError: tool not registered: 'bruteforce_zip'
        修: action 走 _run_chain (ChainRunner 走 ACTION_REGISTRY)
        """
        if kind == "decoder":
            self._run_decoder(name)
        elif kind == "action":
            # v0.5+ 4 快捷 action 走 ChainRunner (内部有 _ACTION_REGISTRY)
            self._run_chain(name)
        else:
            # adapter 走 ToolRunner (subprocess + parse)
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
    def _run_chain(
        self,
        chain_name: str,
        bruteforce_limit: int | None = None,
        extra_context: dict | None = None,
    ) -> None:
        """异步跑 chain (QThread 包装 DAG, 跟 CLI 一致).

        Args:
            chain_name: zip / zip-full / binwalk / foremost / lsb /
                        lsb_extract / fix_pseudo_zip / bruteforce_zip / bruteforce_rar /
                        stegseek_crack / steghide_extract (v0.5-steghide-GUI 新)
            bruteforce_limit: bruteforce 测试用 (e.g. 5000), 加速 CI/开发
            extra_context: 注入 context 的额外字段 (v0.5-steghide-GUI):
                - __wordlist__: wordlist 路径 (stegseek_crack 用)
                - __password__: 密码 (steghide_extract 用)
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
            extra_context=extra_context,
        )
        self._chain_runner.started_run.connect(self._on_chain_started)
        self._chain_runner.finished_with_context.connect(self._on_chain_finished)
        self._chain_runner.failed_with_error.connect(self._on_chain_failed)
        self._chain_runner.start()

    # ---------- v0.5-steghide-GUI: Steghide 子菜单 3 模式入口 ----------
    def _run_steghide_auto(self) -> None:
        """Steghide 子菜单 1: 自动检测 (空密码) — 跟 auto_run 行为一致.

        走 StegseekCrackAction + 空 wordlist (跟 ToolMenuDock 左侧 steghide 等价,
        但走 ChainRunner 输出统一格式的 log).
        """
        # 不传 wordlist → StegseekCrackAction 用 ad-hoc 空 wordlist
        self._run_chain("stegseek_crack")

    def _run_stegseek_crack(self) -> None:
        """Steghide 子菜单 2: 暴力破解 (带 wordlist) — QFileDialog 收 wordlist.

        走 StegseekCrackAction + 用户选 wordlist (e.g. rockyou.txt).
        per owner 决策 1 "GUI 工具栏可 bruteforce" (auto_run 不抢 flag).
        """
        from PySide6.QtWidgets import QFileDialog
        wordlist, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Wordlist (stegseek 暴力破解)",
            str(Path.home()),
            "Text files (*.txt);;All files (*)",
        )
        if not wordlist:
            self.statusBar().showMessage("取消 wordlist 选择")
            return
        self.output_view.append_text(f"\n[Stegseek] wordlist: {wordlist}\n")
        self._run_chain("stegseek_crack", extra_context={"__wordlist__": wordlist})

    def _run_steghide_extract(self) -> None:
        """Steghide 子菜单 3: 指定密码提取 — QInputDialog 收密码.

        走 SteghideExtractAction + 用户输密码.
        per owner 决策 1 "GUI 工具栏可用户密码提取" (auto_run 不抢 flag).
        """
        from PySide6.QtWidgets import QInputDialog
        password, ok = QInputDialog.getText(
            self,
            "Steghide 提取密码",
            "请输入 steghide 提取密码:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not password:
            self.statusBar().showMessage("取消密码输入")
            return
        self.output_view.append_text("\n[Steghide] 用户密码已输入 (隐藏)\n")
        self._run_chain("steghide_extract", extra_context={"__password__": password})

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

            # v0.5-chain-success-journal (per Owner 14:59):
            # 所有 step.success 且 data 里有 'extracted_to' / 'password' / 'foremost_output'
            # / 'lsb_text' 等成功标记 → 推 journal add_event (灰色信息)
            # 让 Owner 在 Journal 区也能看到 'bruteforce 成功' / '解压成功' / '伪加密修复成功'
            if step.get("success") and step_data:
                self._push_chain_step_to_journal(
                    chain_name=chain_name,
                    file_path=file_path,
                    step_name=step_name,
                    step_data=step_data,
                    step_message=step.get("message", ""),
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
        # v0.5-chain-success-journal (per Owner 14:59):
        # chain 整链失败也记 journal, 让 Owner 看到 chain 状态
        self.journal_panel.add_event(
            tool_name=f"chain/{chain_name}",
            kind="chain 失败",
            value=f"chain {chain_name} 失败: {error_msg}",
            file_path=self.current_file,
            severity=4,  # warn
        )

    def _push_chain_step_to_journal(
        self,
        chain_name: str,
        file_path: str,
        step_name: str,
        step_data: dict,
        step_message: str,
    ) -> None:
        """v0.5-chain-success-journal (per Owner 14:59):
        推 step.success 的成功标记到 journal_panel.add_event (灰色信息).

        覆盖 step 类型:
        - bruteforce_zip / bruteforce_rar: data 里有 password + extracted_to
          → kind='bruteforce 成功' value='password=...; 解压到 /xxx'
        - try_unzip / fix_pseudo_encryption: data 里有 extracted_to (无 password)
          → kind='解压成功' / kind='伪加密修复成功' (按 step_name 区分)
        - foremost_extract: data 里有 foremost_output (或 extracted_to)
          → kind='foremost 提取' value='提取到 /xxx'
        - binwalk_extract: data 里有 extracted_to
          → kind='binwalk 提取' value='提取到 /xxx'
        - lsb_extract: data 里有 lsb_text (per Owner '解压到 xxx' 类成功点)
          → kind='LSB 提取成功' value='提取到 /xxx' (若有 extracted_to)
        """
        path_obj = Path(file_path)

        # 1) bruteforce 成功: 有 password
        if "password" in step_data:
            pwd = step_data["password"]
            ext = step_data.get("extracted_to", "?")
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind="bruteforce 成功",
                value=f"password={pwd!r}; 解压到 {ext}",
                file_path=path_obj,
                severity=0,  # 信息, 灰色
            )
            return

        # 2) fix_pseudo_encryption 成功: 有 fixed_count 或 backup
        if step_name == "fix_pseudo_encryption" and "fixed_count" in step_data:
            ext = step_data.get("extracted_to", "?")
            fixed = step_data["fixed_count"]
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind="伪加密修复成功",
                value=f"修复 {fixed} 个 flag_bits; 解压到 {ext}",
                file_path=path_obj,
                severity=0,
            )
            return

        # 3) try_unzip 直接成功 (无 password 无 fix): extracted_to
        if step_name == "try_unzip" and "extracted_to" in step_data:
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind="解压成功",
                value=f"解压到 {step_data['extracted_to']}",
                file_path=path_obj,
                severity=0,
            )
            return

        # 4) foremost_extract: data 里有 foremost_output
        if step_name == "foremost_extract":
            out = step_data.get("foremost_output") or step_data.get("extracted_to", "?")
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind="foremost 提取",
                value=f"提取到 {out}",
                file_path=path_obj,
                severity=0,
            )
            return

        # 5) binwalk_extract: data 里有 extracted_to
        if step_name == "binwalk_extract" and "extracted_to" in step_data:
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind="binwalk 提取",
                value=f"提取到 {step_data['extracted_to']}",
                file_path=path_obj,
                severity=0,
            )
            return

        # 6) 解压类 rar/unzip: extracted_to
        if "extracted_to" in step_data:
            self.journal_panel.add_event(
                tool_name=f"chain/{chain_name}/{step_name}",
                kind=f"{step_name} 成功",
                value=f"解压到 {step_data['extracted_to']}",
                file_path=path_obj,
                severity=0,
            )
            return

    # ---------- decoder menu (v0.5-decoder-menu, GUI 同步 CLI) ----------
    def _build_tools_menu(self, menubar) -> None:
        """从 core.decoders.registry 动态构建 Tools 菜单.

        **渲染顺序**（v0.5-cipher-decoders）:
        1. 先按 ``group`` 分组渲染 — "解密工具1/2/3" 一级目录
        2. 再按 ``category`` 分组兜底 — 老 base/rot/decode/convert/extract

        每个 decoder 一个 QAction, 触发 _run_decoder(name).
        """
        from automisc.core.decoders.registry import (
            list_decoders_by_group,
            list_decoders_by_category,
        )

        tools_menu = menubar.addMenu("&Tools")

        # 1) 按 group 分（v0.5-cipher-decoders — 解密工具1/2/3 一级目录）
        grouped_by_group = list_decoders_by_group()
        for group_name, specs in grouped_by_group.items():
            sub_menu = tools_menu.addMenu(f"&{group_name}")
            for spec in specs:
                act = QAction(spec.display, self)
                act.setToolTip(spec.description)
                act.triggered.connect(
                    lambda checked=False, name=spec.name: self._run_decoder(name)
                )
                sub_menu.addAction(act)

        # 2) 按 category 分（兜底，老 base_rot/decode/convert/extract）
        grouped_by_cat = list_decoders_by_category()
        for category, specs in grouped_by_cat.items():
            sub_menu = tools_menu.addMenu(f"&{category.title()}")
            for spec in specs:
                act = QAction(spec.display, self)
                act.setToolTip(spec.description)
                act.triggered.connect(
                    lambda checked=False, name=spec.name: self._run_decoder(name)
                )
                sub_menu.addAction(act)

        # 兜底: 如果 registry 是空, 加 "no decoders registered" 提示
        if not grouped_by_group and not grouped_by_cat:
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

        # v0.5-hex-ascii-fix + v0.5-coords-qr + v0.5-base-rot-decoders:
        # text-based decoders 走 input 区
        # - hex-ascii: 解 hex/binary/base64/base32 串 (永远走 text 模式)
        # - coords-qr: 解 "(r,c)" 坐标串 (per meihuai 手工解法自动化)
        # - base/rot 系列 (per v0.5-base-rot-decoders PR3): 12 base + 4 rot + 1 stego + 1 custom
        #   都是解文本串, 走 text 模式
        # - cipher 系列 (per v0.5-cipher-decoders): 凯撒/培根/摩尔斯/猪圈/... 全部 text input
        # - base64-image: 解 base64 编码的图片, 走 file 模式 (e.g. 拖了 base64.txt 或 data URL 文件)
        #
        # v0.5-cipher-decoders-textfix (per Owner 19:14):
        # 之前 text_based_decoders 是手写硬编码 list, 加新 cipher 时容易漏.
        # 改成读 spec.text_only 字段 (registry 自动声明). 新 decoder 加 text_only=True 即生效.
        #
        # v0.5-coords-qr-file-mode (per Owner 15:23):
        # coords-qr 有 current_file 时优先 file 模式 (e.g. 拖了 .bin 坐标文件),
        # 走 text 模式会触发 'input_len: 8 chars (CSV text)' bug, 因为
        # extract_base_candidate 抽不到 8 字符坐标, 兜底到 'CSV text' (file 工具把坐标串判成 CSV).
        # 修: coords-qr 且 current_file 存在 -> 走 file 模式让 runner read_text(file_path).
        from automisc.core.decoders.registry import get_decoder
        spec = get_decoder(decoder_name)
        is_text_based = bool(spec and spec.text_only)

        # coords-qr 特殊: 有 current_file 时走 file 模式 (override)
        if decoder_name == "coords-qr" and self.current_file is not None:
            is_text_based = False  # 走 file 模式分支

        # v0.5-base-rot-decoders: base64-custom 是 interactive
        # 触发时弹 QInputDialog 让用户输入 64 字符表
        custom_table: str | None = None
        if decoder_name == "base64-custom":
            from PySide6.QtWidgets import QInputDialog
            custom_table, ok = QInputDialog.getText(
                self,
                "Base64 自定义表",
                "输入 64 字符自定义表（必填，例: URL-safe 表 'A-Za-z0-9-_'）:",
            )
            if not ok or not custom_table or len(custom_table) != 64:
                self.statusBar().showMessage(
                    "base64-custom 已取消 (需 64 字符表)"
                )
                self.output_view.append_text(
                    f"\n=== Decoder: {decoder_name} ===\n"
                    f"[!] 用户取消或输入表长度 != 64 (got {len(custom_table) if custom_table else 0})\n"
                    f"  提示: 自定义表是 64 字符的 base64 字母表 (如标准表右移 N 位、URL-safe 表 等)\n"
                )
                return

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

            # v0.5-tmp-text-mode-2 (per Owner 12:44): QFileDialog 只在 decoder 真有文件输出时弹
            # - hex-ascii / base_convert / cipher: result 是 string, 不写文件 -> 不弹
            # - coords-qr: result 含 output_path (写 PNG) -> 弹
            # spec 已在 is_text_based 判定时拿到 (前面 line ~907), 这里复用
            from PySide6.QtWidgets import QFileDialog
            produces_file = False
            if spec and "output_path" in spec.description.lower():
                # 简单 heuristic: description 提 output_path 就是有文件输出
                produces_file = True
            # 更稳: 直接看 spec 的 run 签名是否接 output_dir (v0.5+ 约定)
            if spec:
                import inspect
                sig = inspect.signature(spec.run)
                produces_file = "output_dir" in sig.parameters

            out_dir = None
            if produces_file:
                out_dir = QFileDialog.getExistingDirectory(
                    self,
                    f"选择 {decoder_name} 输出目录 (text 模式无 current_file)",
                    str(self.output_dir_for_text_decoder),  # 上次选的 / 默认 cwd
                )
                if not out_dir:
                    self.statusBar().showMessage("已取消 (没选 output dir)")
                    self.output_view.append_text(
                        f"\n=== Decoder: {decoder_name} (text mode) ===\n"
                        f"[!] 用户取消 QFileDialog, 没选 output dir\n"
                    )
                    return
                self.output_dir_for_text_decoder = out_dir  # 记住

            status_msg = (
                f"running decoder={decoder_name} (text mode, len={len(candidate)}, "
                f"out_dir={out_dir})…"
            ) if out_dir else (
                f"running decoder={decoder_name} (text mode, len={len(candidate)})…"
            )
            self.statusBar().showMessage(status_msg)

            out_line = (
                f"\n=== Decoder: {decoder_name} (text mode) ===\n"
                f"  input_len: {len(candidate)} chars\n"
            )
            if out_dir:
                out_line += f"  out_dir:   {out_dir}\n"
            # v0.5-base-rot-decoders: base64-custom 显示表头
            if custom_table:
                out_line += f"  custom_table: {custom_table[:32]}... (len=64)\n"
            self.output_view.append_text(out_line)

            # v0.5-base-rot-decoders: 传 custom_table 给 DecodeRunner
            # DecodeRunner inspect 自动识别 runner 签名中的 custom_table 参数
            self._decode_runner = DecodeRunner(
                decoder_name=decoder_name,
                text=candidate,
                out_dir=out_dir,
                custom_table=custom_table,  # 仅 base64-custom 用，其他 decoder 忽略
            )
        else:
            # 传统 file-based decoder (e.g. base64-image / coords-qr with current_file)
            if not self.current_file:
                self.statusBar().showMessage("请先拖入或打开文件")
                self.output_view.append_text("[!] no file selected\n")
                return

            self.statusBar().showMessage(
                f"running decoder={decoder_name} on {self.current_file.name} (async)…"
            )
            self.output_view.append_text(f"\n=== Decoder: {decoder_name} (file mode) ===\n")
            self.output_view.append_text(f"=== File:    {self.current_file}\n")
            # v0.5-coords-qr-file-mode (per Owner 15:23):
            # coords-qr 走 file 模式时, 提示 Owner 全文读 (35019 chars 之类)
            # 区别于 text 模式 input_len: 8 chars
            if decoder_name == "coords-qr":
                try:
                    full_text = self.current_file.read_text(errors="replace")
                    self.output_view.append_text(
                        f"  file_size: {self.current_file.stat().st_size} bytes\n"
                        f"  text_len:  {len(full_text)} chars (全文读, per Owner 15:23 修复)\n"
                    )
                except Exception as e:  # noqa: BLE001
                    self.output_view.append_text(f"  [!] read_text failed: {e}\n")

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

        v0.5-brainfuck-candidate-ux (per Owner 2026-06-20 20:27 实战反馈):
        owner 拖文本文件 (e.g. brainfuck .txt) → auto-run 跑完 → 点 brainfuck decoder.
        之前: input 区是 GUI 日志 + [drop] 信息, 抽 candidate 反复抽错 (GUI log 行).
        修法:
        1. input 区抽 candidate 用 strict=True (没真 base 候选时返回 None)
        2. None 时 fallback 读 current_file 文本内容 (owner 主动拖的 .txt 文件)
           - 仅文本后缀 (.txt/.md/.json/.xml/.csv/.yaml/.yml/.log/.py/.c/.cpp/.js/.html)
           - 仅 < 256KB 读 (大文件 read 进 GUI 会卡)
           - ≥ 85% printable 字符 (避免 binary 假 .txt)
        3. 都没找到 → 返回 None (提示用户手动 paste / selection)
        """
        # strict=True: 没真 base 候选时返回 None, 让 file fallback 接管
        candidate = self.output_view.extract_base_candidate(strict=True)
        if candidate:
            return candidate
        # v0.5-brainfuck-candidate-ux: file fallback — owner 拖文本文件想直接 decoder
        if self.current_file and self.current_file.exists():
            try:
                if self.current_file.stat().st_size > 256 * 1024:  # > 256KB 不读 (防 GUI 卡)
                    return None
                # 仅文本后缀读
                text_suffixes = {
                    ".txt", ".md", ".json", ".xml", ".csv",
                    ".yaml", ".yml", ".log", ".py", ".c", ".cpp",
                    ".js", ".html", ".htm", ".ini", ".conf",
                }
                if self.current_file.suffix.lower() not in text_suffixes:
                    return None
                text = self.current_file.read_text(errors="replace")
                # v0.5-brainfuck-candidate-ux: 二进制假 .txt 检查
                # 注意: utf-8 errors="replace" 会把 \x80-\xff 替换成 \ufffd
                # \ufffd 是 printable, ratio 被高估, 误判二进制为文本
                # 修法: 用 latin-1 decode (每个 byte → U+0000-U+00FF, 无 replacement),
                #       然后 byte 级 printable 检查 (\x20-\x7e + \t\n\r)
                raw_bytes = self.current_file.read_bytes()[:1024]
                sample = raw_bytes.decode("latin-1")
                printable = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
                if printable / max(len(sample), 1) < 0.85:
                    return None
                return text
            except (OSError, UnicodeError):
                return None
        return None

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
