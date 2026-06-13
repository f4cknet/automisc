"""unzip adapter（per ``tools.md`` §3.9）

``unzip``：macOS 自带 zip 解压器，**比 7z 简单但只支持 zip 格式**。

**v0.1 范围**（最小可用 — zip 伪加密检测）：
- ``unzip -l <file>`` —— list contents
- ``unzip -t <file>`` —— test integrity（伪加密时 fail 报错）
- 伪加密检测：unzip 报 "End-of-central-directory signature not found" 或 "invalid zip file" → 强信号

**与 sevenz adapter 关系**：本 adapter 是 sevenz 的 fallback——只跑 zip 格式 + 不依赖 brew。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# unzip 报错中的伪加密信号
_PSEUDO_ENCRYPTION_HINTS = [
    "End-of-central-directory signature not found",  # ZIP 头异常
    "cannot find zipfile directory",  # 损坏
    "invalid zip file",
    "need PK compat. v4.5 (does V4.5 support)?",  # 加密 zip
    "compression method",  # 不支持的压缩方法
]


@register_tool
class UnzipAdapter(ToolAdapter):
    """`unzip` adapter —— zip 格式 list + 伪加密检测。"""

    name = "unzip"
    category = "misc_archive"
    description = "macOS 自带 zip CLI — list + 伪加密检测（仅 zip 格式）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # -l: list; -t: test integrity
        # 合并 stdout/stderr：unzip 报伪加密错误时常到 stderr
        cmd = [self.binary_path or "unzip", "-l", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 伪加密 / 损坏信号
        for hint in _PSEUDO_ENCRYPTION_HINTS:
            if hint.lower() in combined:
                severity = 4 if "end-of-central-directory" in combined else 3
                action = (
                    "ZIP 头标记异常：可能是伪加密（flag 位 0x09 → 0x00），"
                    "建议 hexedit 修改 + 重试；或用 john/zipcrack 爆破"
                    if "end-of-central-directory" in combined else
                    "ZIP 损坏/加密：建议 foremost 提取或 GUI 触发带密码解压"
                )
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="archive_pseudo_encryption",
                        offset=None,
                        matched_pattern=f"unzip: {hint}",
                        severity=severity,
                        suggested_action=action,
                    )
                )
                break

        # 3. 文件计数（unzip -l 输出格式: "        N  date   time   path"）
        file_count = 0
        for line in stdout.splitlines():
            # 跳过 header / footer 行
            if line.strip().startswith("Archive:") or line.strip().startswith("Length"):
                continue
            # 数据行格式: "   123456  06-13-2026 12:34   file/path"
            m = re.match(r"^\s+\d+\s+\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}\s+.+$", line)
            if m:
                file_count += 1

        if file_count > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="archive_meta",
                    offset=None,
                    matched_pattern=f"archive contains {file_count} files",
                    severity=1,
                    suggested_action="记录归档内容数量",
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
