"""file adapter（per ``tools.md`` §3.12）

``file`` 命令：``file_path: ASCII text`` 格式。
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


@register_tool
class FileAdapter(ToolAdapter):
    """`file` 命令 adapter —— 通过 magic bytes 识别文件类型。"""

    name = "file"
    category = "shared"
    description = "通过 magic bytes 识别文件类型"

    def run(self, file_path: str) -> ToolResult:
        # per v0.5-windows-tool-compat PR2: 走 resolve_tool_binary (PATH → extend-tools/
        # fallback) 而非硬编码 "file". Win 上 file CLI 不在系统 PATH, 必须依赖
        # extend-tools/bin/win-x64/file.exe (per install.ps1 + manifest.yaml).
        from automisc.tools.paths import resolve_tool_binary
        cmd = [
            self.binary_path or resolve_tool_binary("file") or "file",
            "--brief",
            file_path,
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        # file --brief 输出如 "ASCII text" / "PNG image data, 800 x 600"
        # 提取 file type 信息作为 low-severity 可疑点（用户看 magic bytes 决定）
        if exit_code == 0 and stdout.strip():
            file_type = stdout.strip()
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="file_type",
                    offset=None,
                    matched_pattern=file_type,
                    severity=1,
                    suggested_action=f"对比文件后缀判断是否为伪扩展名（{file_type}）",
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