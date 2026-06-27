"""exiftool adapter（per ``tools.md`` §3.5）

``exiftool``：提取文件元数据（EXIF / Office / PDF metadata）。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# exiftool 输出格式: "<TAG>: <VALUE>"
_EXIFTOOL_LINE_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*?)\s*:\s*(?P<value>.+)$")

# 比赛高价值 metadata tag（per ctf-forensics/SKILL.md）
_HIGH_VALUE_TAGS = {
    "Author",
    "Title",
    "Subject",
    "Keywords",
    "Comment",
    "Description",
    "Creator",
    "Producer",
    "Company",
    "Software",
    "Creator Tool",
    "Last Modified By",
    "Create Date",
    "Modify Date",
}


@register_tool
class ExiftoolAdapter(ToolAdapter):
    """`exiftool` adapter —— 提取文件元数据。"""

    name = "exiftool"
    category = "shared"
    description = "提取文件元数据（EXIF / Office / PDF）"

    def run(self, file_path: str) -> ToolResult:
        from automisc.tools.paths import resolve_tool_binary
        cmd = [self.binary_path or resolve_tool_binary("exiftool") or "exiftool", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        seen_tags: set[str] = set()

        for line in stdout.splitlines():
            m = _EXIFTOOL_LINE_RE.match(line)
            if not m:
                continue
            tag = m.group("key").strip()
            value = m.group("value").strip()

            # 高价值 tag → 强可疑（CTF 经常在 metadata 藏 flag）
            if tag in _HIGH_VALUE_TAGS and value and tag not in seen_tags:
                seen_tags.add(tag)
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="metadata",
                        offset=None,
                        matched_pattern=f"{tag}: {value[:120]}",
                        severity=3,
                        suggested_action=f"检查 {tag} 字段是否含 flag 关键字",
                    )
                )

        # 同时跑通用关键字扫描（flag / keyword / base64）
        from automisc.core.suspicious import scan_output_for_suspicious
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name,
            file_path=file_path,
            stdout=stdout,
        ))

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )