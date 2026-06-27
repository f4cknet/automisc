"""binwalk adapter（per ``tools.md`` §3.5）

``binwalk``：扫描文件中嵌入的文件（firmware / CTF 套娃必备）。

v0.5-philosophy-rethink (2026-06-20) 改造 (per Owner 决策 1):
- **删** v0.5-binwalk-extract 的自动 ``binwalk -e`` 提取逻辑
- 原因: auto_run 调用 binwalk adapter 会自动雕文件, 违背"工具=找可疑点"
  "做题人=决策下一步, 不抢 flag" 半自动化哲学
- 现在 binwalk adapter 只做检测 (列 magic + offset), suggested_action 提示
  用户用工具栏 foremost / 链菜单 binwalk 手工触发分离
- 分离逻辑独立到 ``core/actions/binwalk_extract.py::BinwalkExtractAction``,
  走 foremost (macOS 可靠), 由 ``build_binwalk_extract_dag`` 链 / GUI 工具栏入口
  手工触发, **不**在 auto_run pool

v0.5-binwalk-extract (2026-06-15, 已推翻) 历史:
- 关键字白名单加 "PEM private key" / "SSH private key" / "RSA private key"
  (per Owner 实测 greatescape.pcap — binwalk 扫到 PEM 私钥但 adapter 报 0 SP)
- 扫描后自动调 ``binwalk -e`` 提取嵌入文件到 input 同目录
- 提取路径写入 SuspiciousPoint context / suggested_action

**v0.5 推翻旧定论**:
- 之前文档里 "binwalk 在 macOS 兼容性问题" 的结论作废
- binwalk CLI 在 macOS 完全可用，bug 在 adapter 层关键字白名单过窄
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# binwalk 输出行格式: "<DECIMAL>       <HEXADECIMAL>     <DESCRIPTION>"
_BINWALK_LINE_RE = re.compile(
    r"^\s*(\d+)\s+0x[0-9a-fA-F]+\s+(.+)$"
)

# DESCRIPTION 中的常见文件 magic → 强可疑（建议 foremost / binwalk -e 分离）
_FILE_HEADER_KEYWORDS = [
    # 现有 17 项 (v0.1 保留)
    "PNG image",
    "JPEG image",
    "GIF image",
    "PDF document",
    "ZIP archive",
    "RAR archive",
    "7-zip archive",
    "gzip compressed",
    "bzip2 compressed",
    "xz compressed",
    "tar archive",
    "ELF ",
    "PE32 ",
    "Microsoft Office",
    "OpenDocument",
    "pcap",
    # v0.5-binwalk-extract 新增 (per Owner 实测 greatescape.pcap)
    "PEM private key",   # RSA / EC / generic PEM (OpenSSL)
    "SSH private key",   # OpenSSH 私钥
    "RSA private key",   # 旧版 RSA 私钥
]


@register_tool
class BinwalkAdapter(ToolAdapter):
    """`binwalk` adapter —— 纯探测 (列 magic + offset), 不雕文件.

    v0.5-philosophy-rethink: 删 v0.5-binwalk-extract 的自动 binwalk -e 提取.
    用户要分离时, 走:
    - GUI 工具栏 foremost 入口 (雕)
    - GUI Chain 菜单 binwalk 链 (走 BinwalkExtractAction + ForemostExtractAction)
    - CLI ``automisc chain --chain binwalk`` (同上)

    auto_run pool (find_suspicious_from_<type>) 调用本 adapter 只为找可疑点,
    不雕不修不爆, 违背此原则的 auto 行为全部移除.
    """

    name = "binwalk"
    category = "shared"
    description = "扫描并报告文件中的嵌入文件（per magic bytes），纯探测不雕文件"

    default_timeout = 60.0  # 大文件扫描可能较慢

    def run(self, file_path: str) -> ToolResult:
        # v0.5-platform-extend-tools: binwalk 跨平台通过 `python -m binwalk` 调用
        # (venv activate 不需要, system Python 也能跑)
        # binary_path 显式设置时仍优先用 binary_path (向后兼容)
        from automisc.tools.paths import resolve_tool_binary

        if self.binary_path:
            binwalk = self.binary_path
        else:
            # 跨平台统一: python -m binwalk
            import sys as _sys
            binwalk = f"{_sys.executable} -m binwalk"

        # Step 1: binwalk <file> 扫描（v0.5-philosophy-rethink: 不再自动 binwalk -e 提取）
        if " " in binwalk:
            # python -m binwalk → shell 拆分
            cmd_scan = binwalk.split() + [file_path]
        else:
            cmd_scan = [binwalk, file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd_scan)

        suspicious: list[SuspiciousPoint] = []
        hits: list[tuple[int, str, str]] = []  # (offset, desc, matched_kw)

        for line in stdout.splitlines():
            m = _BINWALK_LINE_RE.match(line)
            if not m:
                continue
            offset = int(m.group(1))
            desc = m.group(2)

            # 命中文件头关键字 → 强可疑（severity 4）
            matched_kw = next(
                (kw for kw in _FILE_HEADER_KEYWORDS if kw.lower() in desc.lower()),
                None,
            )
            if matched_kw:
                hits.append((offset, desc, matched_kw))

        # Step 2 (已删): binwalk -e 自动提取
        # v0.5-philosophy-rethink 之前会在此处调 _extract_files, 触发 binwalk -e 雕文件.
        # 现在改为 suggested_action 提示用户手工触发 (GUI 工具栏 foremost / Chain 菜单 binwalk).

        # 把 hits 组装成 SuspiciousPoint
        for offset, desc, matched_kw in hits:
            suggestion = (
                f"建议 foremost / binwalk -e 分离（{matched_kw} @ offset {offset}）\n"
                f"工具栏 foremost 入口 或 Chain 菜单 binwalk 链手工触发\n"
                f"如需用此文件解密 TLS: 配 Wireshark --ssl.keys <server_ip>,<port>,http,<key_path>"
            )

            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="file_header",
                    offset=offset,
                    matched_pattern=f"{matched_kw} @ offset {offset}",
                    severity=4,
                    suggested_action=suggestion,
                    context=desc[:80],
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
            metadata={},  # v0.5-philosophy-rethink: 不再有 extracted_files / extract_dir
        )


__all__ = ["BinwalkAdapter"]  
