"""strings adapter（per ``tools.md`` §3.12）

``strings -n 4``：提取 ≥4 字节可打印字符串。
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


@register_tool
class StringsAdapter(ToolAdapter):
    """`strings` 命令 adapter —— 提取可打印字符串。"""

    name = "strings"
    category = "shared"
    description = "提取文件中的可打印字符串（≥4 字节）"

    def run(self, file_path: str) -> ToolResult:
        # -a: scan the whole file, not just the initialized data section of object files
        # -n 4: sequences of >= 4 printable chars
        cmd = [self.binary_path or "strings", "-a", "-n", "4", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious = scan_output_for_suspicious(
            tool_name=self.name,
            file_path=file_path,
            stdout=stdout,
        )

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )