"""john adapter（per ``tools.md`` §3.9）

``john``：John the Ripper，**密码爆破瑞士军刀**（jumbo 版本支持 zip / 7z / rar / pdf / office 等）。

**v0.1 范围**（最小可用 — 爆破入口）：
- adapter **不实际爆破**（爆破是长时间任务，v0.1 只生成爆破 plan）
- 检测 hash 文件类型（用 ``zip2john`` / ``rar2john`` / 等子工具生成 hash file）
- 子工具列表：john 自带 zip2john / rar2john / pdf2john / 7z2john 等（jumbo 版）

**v0.5+ 计划**：GUI 触发实际爆破（带进度条 / 中断点）。

**macOS**：`brew install john-jumbo`（已装，1.9.0-jumbo-1）。
"""
from __future__ import annotations

import shutil
import subprocess

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# john 自带的 hash 提取工具
_JOHN_HASH_TOOLS = [
    ("zip2john", "ZIP 归档（CTF 最常见）"),
    ("rar2john", "RAR 归档"),
    ("7z2john", "7-Zip 归档"),
    ("pdf2john", "PDF 文档密码"),
    ("ssh2john", "SSH 私钥"),
    ("office2john", "Office 文档密码"),
    ("gpg2john", "GPG 私钥"),
]


@register_tool
class JohnAdapter(ToolAdapter):
    """`john` adapter —— 密码爆破入口（v0.1 仅检测能力 + 输出工具列表）。"""

    name = "john"
    category = "misc_archive"
    description = "John the Ripper jumbo — 密码爆破入口（v0.1 仅检测 hash 工具能力）"

    default_timeout = 15.0  # 仅做能力检测

    def run(self, file_path: str) -> ToolResult:
        # v0.1 策略：尝试 zip2john（最常见格式），能跑通就说明 john jumbo + 对应
        # helper tool 可用
        # 注意：zip2john 对非 zip 文件会出错，但不应该 panic
        john_dir = "/usr/local/share/john"  # brew 装的位置
        zip2john = shutil.which("zip2john") or f"{john_dir}/zip2john"

        # 用 zip2john 测试文件（成功 / 失败都好，关键是工具可用）
        cmd = [zip2john, file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. zip2john 输出解析
        # 成功: "file.zip/file_name:$zip2$*0*3*0*...*$/zip2$"
        # 失败: "file.zip/... : No password hash found"
        if exit_code == 0 and "$zip2$" in stdout.lower() or "$pkzip2$" in stdout.lower():
            # 提取 hash
            for line in stdout.splitlines():
                if "$zip2$" in line.lower() or "$pkzip2$" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        hash_str = parts[1].strip()
                        suspicious.append(
                            SuspiciousPoint(
                                id="",
                                tool_name=self.name,
                                file_path=file_path,
                                category="archive_password_hash",
                                offset=None,
                                matched_pattern=f"zip hash extracted ({len(hash_str)} chars)",
                                severity=4,
                                suggested_action=(
                                    "已提取 ZIP 密码 hash；建议 GUI 触发 john 爆破"
                                    "（rockyou.txt / top10k 等 wordlist）"
                                ),
                            )
                        )
                        break
        else:
            # zip2john 失败（不是 zip / 不含密码 / 非 zip 格式）
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="john_unsupported",
                    offset=None,
                    matched_pattern=f"zip2john 未能提取 hash (exit={exit_code}, stderr={stderr[:80]!r})",
                    severity=1,
                    suggested_action=(
                        "文件可能不是 ZIP；可尝试 7z2john / rar2john / pdf2john 等其他工具"
                    ),
                )
            )

        # 3. 工具能力报告
        for tool_name, desc in _JOHN_HASH_TOOLS:
            tool_path = shutil.which(tool_name) or f"{john_dir}/{tool_name}"
            if shutil.which(tool_name) or self._path_exists(tool_path):
                # 只列前 3 个（避免噪音）
                if _JOHN_HASH_TOOLS.index((tool_name, desc)) < 3:
                    suspicious.append(
                        SuspiciousPoint(
                            id="",
                            tool_name=self.name,
                            file_path=file_path,
                            category="john_capability",
                            offset=None,
                            matched_pattern=f"{tool_name} available: {desc}",
                            severity=1,
                            suggested_action=f"如需爆破此文件类型，可用 {tool_name} 提取 hash",
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

    @staticmethod
    def _path_exists(path: str) -> bool:
        from pathlib import Path
        return Path(path).exists()
