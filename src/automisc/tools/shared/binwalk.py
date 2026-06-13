"""binwalk adapter（per ``tools.md`` §3.5）

``binwalk``：扫描文件中嵌入的文件（firmware / CTF 套娃必备）。
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

# DESCRIPTION 中的常见文件 magic → 强可疑（建议 foremost 分离）
_FILE_HEADER_KEYWORDS = [
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
]


@register_tool
class BinwalkAdapter(ToolAdapter):
    """`binwalk` adapter —— 扫描并报告嵌入文件。"""

    name = "binwalk"
    category = "shared"
    description = "扫描并报告文件中的嵌入文件"

    default_timeout = 60.0  # 大文件扫描可能较慢

    def run(self, file_path: str) -> ToolResult:
        cmd = [self.binary_path or "binwalk", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
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
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="file_header",
                        offset=offset,
                        matched_pattern=f"{matched_kw} @ offset {offset}",
                        severity=4,
                        suggested_action=f"建议 foremost / binwalk -e 分离（{matched_kw}）",
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
        )