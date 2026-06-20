"""AutoRunner 链式调度（v0.1.1 GUI 增强 + v0.5-philosophy-rethink）

v0.5-philosophy-rethink 升级 (2026-06-20, per owner 决策 C "彻底改哲学"):
- **保留** AutoRunner 类 (向后兼容, GUI 工具栏可手工调用)
- **加** 4 个 find_suspicious_from_<type> 函数 (替代 auto_run 入口)
  - 每类独立工具池, **不**互相串联
  - **不**触发任何 chain (链留给人工触发: automisc chain / GUI 工具栏按钮)
  - **不**雕不修不爆 (auto_run 自动化只做可疑点分析)
  - 结果写 journal (per tool run_tool 内部已写)

按 owner 11:49 + 12:02 拍板:
- tool = 找可疑点 (探测)
- journal = 可疑点累积
- 做题人 = 决策下一步 (人工判断, 不抢 flag)

**auto_run 自动化禁忌** (per owner 决策 1):
- foremost (雕) — **不**在 auto_run 推荐
- binwalk -e / binwalk_extract (雕) — **不**在 auto_run (binwalk 探测模式 OK)
- steghide extract (抽) — **不**在 auto_run
- john (爆破) — **不**在 auto_run
- fix_pseudo_zip (修) — **不**在 auto_run (链菜单手工触发)
- bruteforce_zip (爆) — **不**在 auto_run (链菜单手工触发)

**v0.5-journal-highlight-keywords Q12 推翻** (per Owner 2026-06-16 2:12 实测拍板):
- 旧 v0.5-short-circuit-on-flag (per 2026-06-14 10:46): 命中 severity>=5 终止链
- 推翻原因: owner 实测 misc2.jpg, exiftool 命中 "this_is_not_password" (误导性 keyword)
  → 链停了, binwalk/foremost/strings 全没跑 → 漏掉雕 ZIP / 漏掉所有后续信号
- 铁律 (per Owner): "可疑点越多越好, 宁可多给错给, 也不能少给"
- 新行为: SHORT_CIRCUIT_SEVERITY = 99 → 永远不触发 short-circuit, 跑完全部 max_tools 个工具
- 链仍 emit tool_finished + chain_finished (GUI 知道哪些跑完)

v0.1.1 范围：串行（v0.5+ 范围：并发池 QThreadPool）
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from automisc.core.exceptions import AutomiscError
from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.result import ToolResult
from automisc.core.router import RouteRecommendation


# v0.5-journal-highlight-keywords Q12 (per Owner 2026-06-16 2:12):
# 旧 SHORT_CIRCUIT_SEVERITY = 5 (命中 sensitive_keyword 就停) — 推翻
# 新: 99 永远不触发, 跑完全部 max_tools 个工具
# 理由: 宁可多给错给, 也不能少给 (owner 铁律)
SHORT_CIRCUIT_SEVERITY = 99


# v0.5-philosophy-rethink 4 类工具池 (per owner 决策 1 "auto_run 改名 find_suspicious_from_picture"):
# - 纯探测, **不**雕不修不爆
# - **不**含: foremost / binwalk_extract / steghide_extract / john / fix_pseudo / bruteforce (这些留 GUI 工具栏 / CLI 链)
# - binwalk adapter 默认探测模式 (跑 `binwalk <file>` 不带 -e), 写 SP 到 journal — OK
FIND_SUSPICIOUS_PICTURE_TOOLS = [
    "zsteg",        # PNG LSB 隐写探测 (JPEG/BMP/GIF 会 fail, 不影响)
    "steghide",     # JPEG/BMP 隐写 info (无密码, 纯探测; PNG/GIF 不支持会 fail)
    "exiftool",     # EXIF metadata
    "binwalk",      # 探测 (不 -e)
    "strings",      # rule_scanner 可疑字符串
    "file",         # 文件类型
]  
FIND_SUSPICIOUS_TRAFFIC_TOOLS = [
    "pcap_protocol_router",  # pcap 协议分类 + key 候选
    "tshark",                # 协议解析
    "strings",               # 明文协议字段
    "file",
]
FIND_SUSPICIOUS_ARCHIVE_TOOLS = [
    "sevenz",  # 7z l 列表 (不实际解压)
    "unzip",   # unzip -l 列表 (不实际解压)
    "file",
    "strings",
]
FIND_SUSPICIOUS_BINARY_TOOLS = [
    "file",
    "strings",
    "binwalk",    # 探测 (不 -e)
    "exiftool",
]


# v0.5-philosophy-rethink: 扩展名 → pool 名 (per owner 决策 1)
# GUI 拖入文件后, 根据扩展名选对应的 find_suspicious_from_<type> 工具池
# 缺省: binary (含 file/strings/binwalk/exiftool, 通用探测)
EXTENSION_TO_POOL: dict[str, str] = {
    # picture
    ".png": "picture",
    ".jpg": "picture",
    ".jpeg": "picture",
    ".bmp": "picture",
    ".gif": "picture",
    # traffic
    ".pcap": "traffic",
    ".pcapng": "traffic",
    # archive
    ".zip": "archive",
    ".7z": "archive",
    ".rar": "archive",
    ".tar": "archive",
    ".gz": "archive",
    # binary (exe/dll/elf/bin, 默认兜底也是 binary)
    ".bin": "binary",
    ".exe": "binary",
    ".dll": "binary",
    ".elf": "binary",
}


def pick_suspicious_pool(file_path: str) -> tuple[str, list[str]]:
    """根据文件扩展名选 find_suspicious_from_<type> 工具池.

    Args:
        file_path: 目标文件路径

    Returns:
        (pool_name, tools):
            pool_name: "picture" / "traffic" / "archive" / "binary" / "fallback"
            tools:     对应的工具名列表 (per FIND_SUSPICIOUS_*_TOOLS)
    """
    ext = Path(file_path).suffix.lower()
    pool_name = EXTENSION_TO_POOL.get(ext, "binary")
    if pool_name == "picture":
        return pool_name, FIND_SUSPICIOUS_PICTURE_TOOLS
    elif pool_name == "traffic":
        return pool_name, FIND_SUSPICIOUS_TRAFFIC_TOOLS
    elif pool_name == "archive":
        return pool_name, FIND_SUSPICIOUS_ARCHIVE_TOOLS
    else:  # binary (含默认)
        return "binary", FIND_SUSPICIOUS_BINARY_TOOLS


def find_suspicious_from_picture(core: CoreOrchestrator, file_path: str) -> list[ToolResult]:
    """图片专用探测器 (per v0.5-philosophy-rethink).

    跑 [zsteg / exiftool / binwalk / strings / file] — 纯探测, **不**雕不修不爆.
    结果自动写 journal (per core.run_tool).

    Args:
        core: CoreOrchestrator 实例
        file_path: 目标文件路径

    Returns:
        list[ToolResult]: 各工具跑完结果 (失败也返回, 调方看 exit_code)
    """
    results: list[ToolResult] = []
    for tool_name in FIND_SUSPICIOUS_PICTURE_TOOLS:
        try:
            result = core.run_tool(tool_name, file_path)
        except AutomiscError as e:
            # 工具不存在 / 文件不存在 → 跳过, 不中断
            results.append(
                ToolResult(
                    tool_name=tool_name,
                    exit_code=-1,
                    stdout="",
                    stderr=f"ToolNotFoundError: {e}",
                    suspicious_points=[],
                    error=str(e),
                )
            )
            continue
        results.append(result)
    return results


def find_suspicious_from_traffic(core: CoreOrchestrator, file_path: str) -> list[ToolResult]:
    """流量包专用探测器 (pcap/pcapng/cap).

    跑 [pcap_protocol_router / tshark / strings / file] — 纯探测.
    """
    results: list[ToolResult] = []
    for tool_name in FIND_SUSPICIOUS_TRAFFIC_TOOLS:
        try:
            result = core.run_tool(tool_name, file_path)
        except AutomiscError as e:
            results.append(
                ToolResult(
                    tool_name=tool_name,
                    exit_code=-1,
                    stdout="",
                    stderr=f"ToolNotFoundError: {e}",
                    suspicious_points=[],
                    error=str(e),
                )
            )
            continue
        results.append(result)
    return results


def find_suspicious_from_archive(core: CoreOrchestrator, file_path: str) -> list[ToolResult]:
    """压缩包专用探测器 (zip/7z/rar/tar/gz).

    跑 [sevenz / unzip / file / strings] — 纯探测 (列表不实际解压).
    **不**跑 john (爆破) — 留给 GUI 工具栏.
    """
    results: list[ToolResult] = []
    for tool_name in FIND_SUSPICIOUS_ARCHIVE_TOOLS:
        try:
            result = core.run_tool(tool_name, file_path)
        except AutomiscError as e:
            results.append(
                ToolResult(
                    tool_name=tool_name,
                    exit_code=-1,
                    stdout="",
                    stderr=f"ToolNotFoundError: {e}",
                    suspicious_points=[],
                    error=str(e),
                )
            )
            continue
        results.append(result)
    return results


def find_suspicious_from_binary(core: CoreOrchestrator, file_path: str) -> list[ToolResult]:
    """二进制专用探测器 (bin/exe/dll/elf).

    跑 [file / strings / binwalk (探测) / exiftool].
    """
    results: list[ToolResult] = []
    for tool_name in FIND_SUSPICIOUS_BINARY_TOOLS:
        try:
            result = core.run_tool(tool_name, file_path)
        except AutomiscError as e:
            results.append(
                ToolResult(
                    tool_name=tool_name,
                    exit_code=-1,
                    stdout="",
                    stderr=f"ToolNotFoundError: {e}",
                    suspicious_points=[],
                    error=str(e),
                )
            )
            continue
        results.append(result)
    return results


class FindSuspiciousRunner(QThread):
    """v0.5-philosophy-rethink 新 QThread: 跑 find_suspicious_from_<type>.

    与 AutoRunner 的区别:
    - 不接受 recommendations; 改为按 file extension 选 pool
    - pool = pick_suspicious_pool(file_path) 决定跑哪些工具
    - **不**触发任何 chain (auto_run 抢 flag 是 owner 决策 1 禁忌)
    - **不**雕不修不爆 (binwalk 探测模式 OK, binwalk -e / fix_pseudo / bruteforce 留给人工)
    - Signal 接口与 AutoRunner 一致 (tool_started / tool_finished / chain_finished / chain_failed),
      GUI 现有 _on_auto_tool_started / _on_auto_tool_finished / _on_auto_chain_finished handler 直接复用

    用法::

        runner = FindSuspiciousRunner(core, str(file_path))
        runner.tool_started.connect(...)
        runner.chain_finished.connect(...)
        runner.start()
    """

    # Signal: pool 已选 (pool_name, list[tool_name])
    pool_selected = Signal(str, list)
    # Signal: 单个工具开始 (tool_name, index, total)
    tool_started = Signal(str, int, int)
    # Signal: 单个工具跑完 (tool_name, AutoRunSummary, ToolResult)
    tool_finished = Signal(str, object, object)
    # Signal: 整 pool 跑完 (list[AutoRunSummary])
    chain_finished = Signal(list)
    # Signal: pool 中某个工具 fatal error (tool_name, error_msg)
    chain_failed = Signal(str, str)
    # Signal: 整体进度 (current_index, total)
    progress = Signal(int, int)

    def __init__(
        self,
        core: CoreOrchestrator,
        file_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.file_path = file_path
        self._summaries: list[AutoRunSummary] = []
        self._stopped = False

    def stop(self) -> None:
        """请求停止 (下一个工具开始前检查)."""
        self._stopped = True

    def run(self) -> None:
        """QThread 入口: 串行跑 pool 里所有工具.

        pool 工具列表由 pick_suspicious_pool(self.file_path) 按扩展名决定.
        """
        from automisc.core.logging_setup import get_logger

        log = get_logger(__name__)
        pool_name, tool_names = pick_suspicious_pool(self.file_path)
        log.info(
            "FindSuspiciousRunner.run: file=%s, pool=%s, tools=%s",
            self.file_path, pool_name, tool_names,
        )
        self.pool_selected.emit(pool_name, list(tool_names))

        total = len(tool_names)
        for i, tool_name in enumerate(tool_names):
            if self._stopped:
                log.info("FindSuspiciousRunner.run: stopped, exit")
                break

            log.info(
                "FindSuspiciousRunner.run: [%d/%d] starting %s",
                i + 1, total, tool_name,
            )
            self.tool_started.emit(tool_name, i, total)
            self.progress.emit(i, total)

            try:
                result = self.core.run_tool(tool_name, self.file_path)
                log.info(
                    "FindSuspiciousRunner.run: [%d/%d] %s done, exit=%d, susp=%d",
                    i + 1, total, tool_name, result.exit_code, len(result.suspicious_points),
                )
            except AutomiscError as e:
                log.error(
                    "FindSuspiciousRunner.run: %s raised AutomiscError: %s",
                    tool_name, e,
                )
                self.chain_failed.emit(tool_name, str(e))
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=str(e),
                    )
                )
                break
            except Exception as e:  # noqa: BLE001
                log.error(
                    "FindSuspiciousRunner.run: %s raised %s: %s",
                    tool_name, type(e).__name__, e,
                )
                import traceback
                log.error(
                    "FindSuspiciousRunner.run: traceback: %s",
                    traceback.format_exc(),
                )
                self.chain_failed.emit(
                    tool_name, f"{type(e).__name__}: {e}",
                )
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
                break

            summary = AutoRunSummary(
                tool_name=tool_name,
                success=result.exit_code == 0 and result.error is None,
                exit_code=result.exit_code,
                suspicious_count=len(result.suspicious_points),
                error=result.error,
            )
            self._summaries.append(summary)
            self.tool_finished.emit(tool_name, summary, result)

        self.progress.emit(total, total)
        self.chain_finished.emit(self._summaries)

    def summaries(self) -> list[AutoRunSummary]:
        return list(self._summaries)


@dataclass
class AutoRunSummary:
    """链中一个工具的跑完总结."""

    tool_name: str
    success: bool
    exit_code: int
    suspicious_count: int
    error: Optional[str] = None


class AutoRunner(QThread):
    """按顺序跑多个工具的 QThread.

    用法::

        runner = AutoRunner(core, recommendations, file_path)
        runner.tool_started.connect(lambda t, i, n: ...)
        runner.tool_finished.connect(lambda t, summary: ...)
        runner.chain_finished.connect(lambda summaries: ...)
        runner.chain_failed.connect(lambda tool, err: ...)
        runner.start()
    """

    # Signal: 单个工具开始 (tool_name, index, total)
    tool_started = Signal(str, int, int)
    # Signal: 单个工具跑完 (tool_name, AutoRunSummary, ToolResult)
    tool_finished = Signal(str, object, object)
    # Signal: 整个链跑完 (list[AutoRunSummary])
    chain_finished = Signal(list)
    # Signal: 链中某个工具 fatal error (ToolNotFoundError / FileNotAutomiscError)
    chain_failed = Signal(str, str)
    # Signal: 整体进度 (current_index, total)
    progress = Signal(int, int)
    # v0.5-short-circuit: 链因命中 severity>=5 终止 (reason=str)
    short_circuited = Signal(str, str)  # tool_name, reason

    def __init__(
        self,
        core: CoreOrchestrator,
        recommendations: list[RouteRecommendation],
        file_path: str,
        max_tools: int = 5,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.file_path = file_path
        # 取 score > 0 的前 max_tools 个
        self.tool_names: list[str] = [
            rec.tool_name
            for rec in recommendations[:max_tools]
            if rec.score > 0
        ]
        self._summaries: list[AutoRunSummary] = []
        self._stopped = False

    def stop(self) -> None:
        """请求停止（下一个工具开始前检查）."""
        self._stopped = True

    def run(self) -> None:
        """QThread 入口：串行跑 self.tool_names."""
        from automisc.core.logging_setup import get_logger
        log = get_logger(__name__)
        log.info("AutoRunner.run: ENTER, tool_names=%s", self.tool_names)
        total = len(self.tool_names)
        for i, tool_name in enumerate(self.tool_names):
            if self._stopped:
                log.info("AutoRunner.run: stopped, exit")
                break

            log.info("AutoRunner.run: [%d/%d] starting %s", i + 1, total, tool_name)
            self.tool_started.emit(tool_name, i, total)
            self.progress.emit(i, total)

            try:
                result = self.core.run_tool(tool_name, self.file_path)
                log.info(
                    "AutoRunner.run: [%d/%d] %s done, exit=%d, susp=%d",
                    i + 1, total, tool_name, result.exit_code, len(result.suspicious_points),
                )
            except AutomiscError as e:
                log.error("AutoRunner.run: %s raised AutomiscError: %s", tool_name, e)
                # 致命错误（ToolNotFoundError 等）→ 链失败
                self.chain_failed.emit(tool_name, str(e))
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=str(e),
                    )
                )
                break  # 终止链
            except Exception as e:  # noqa: BLE001
                log.error(
                    "AutoRunner.run: %s raised %s: %s (traceback follows)",
                    tool_name, type(e).__name__, e,
                )
                import traceback
                log.error("AutoRunner.run: traceback: %s", traceback.format_exc())
                # 未知错误
                self.chain_failed.emit(tool_name, f"{type(e).__name__}: {e}")
                self._summaries.append(
                    AutoRunSummary(
                        tool_name=tool_name,
                        success=False,
                        exit_code=-1,
                        suspicious_count=0,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
                break

            # 单个工具跑完
            summary = AutoRunSummary(
                tool_name=tool_name,
                success=result.exit_code == 0 and result.error is None,
                exit_code=result.exit_code,
                suspicious_count=len(result.suspicious_points),
                error=result.error,
            )
            self._summaries.append(summary)
            # 传完整 ToolResult 给 GUI（避免重复执行）
            self.tool_finished.emit(tool_name, summary, result)

            # v0.5-short-circuit: 命中 severity>=5 -> 终止链
            max_severity = max(
                (sp.severity for sp in result.suspicious_points),
                default=0,
            )
            if max_severity >= SHORT_CIRCUIT_SEVERITY:
                self.short_circuited.emit(
                    tool_name,
                    f"命中 severity={max_severity} (>= {SHORT_CIRCUIT_SEVERITY}), 终止后续 tools",
                )
                break

        # 链结束
        self.progress.emit(total, total)
        self.chain_finished.emit(self._summaries)

    def summaries(self) -> list[AutoRunSummary]:
        return list(self._summaries)


__all__ = [
    "AutoRunner",
    "AutoRunSummary",
    "SHORT_CIRCUIT_SEVERITY",
    "find_suspicious_from_picture",
    "find_suspicious_from_traffic",
    "find_suspicious_from_archive",
    "find_suspicious_from_binary",
    "FIND_SUSPICIOUS_PICTURE_TOOLS",
    "FIND_SUSPICIOUS_TRAFFIC_TOOLS",
    "FIND_SUSPICIOUS_ARCHIVE_TOOLS",
    "FIND_SUSPICIOUS_BINARY_TOOLS",
    "EXTENSION_TO_POOL",
    "pick_suspicious_pool",
    "FindSuspiciousRunner",
]
