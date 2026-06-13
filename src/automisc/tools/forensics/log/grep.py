"""grep adapter（per ``tools.md`` §3.4 + §3.12）

``grep``：macOS 自带的关键字搜索工具。

**v0.1 范围**（最小可用 — Log Forensics）：
- ``grep -E -i -n -C 1`` 搜索 CTF 关键字（password / secret / hidden / flag / webshell 关键字）
- 命中行 + 上下文 → 进 SuspiciousPoint
- 限制最大输出（防大日志 OOM）

**注**：与 shared/strings.py 不同：
- strings 提取**所有**可打印字符串
- grep 是**模式匹配**，命中关键字才报
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# CTF Log 关键字（per tools.md §3.4）
_LOG_KEYWORDS = [
    # 凭据 / 敏感数据
    "password",
    "passwd",
    "secret",
    "hidden",
    "token",
    "apikey",
    "api_key",
    "private_key",
    "credentials",
    # 攻击特征
    "failed login",
    "authentication failure",
    "sudo:",
    "privilege escalation",
    "webshell",
    "behinder",
    "caidao",
    "godzilla",
    "antsword",
    # CTF 标志
    "flag",
    "ctf",
    "key{",
]


@register_tool
class GrepAdapter(ToolAdapter):
    """`grep` adapter —— CTF log 关键字搜索（macOS 自带）。"""

    name = "grep"
    category = "forensics_log"
    description = "关键字搜索 CTF log 关键字（password/secret/webshell/flag 等）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # -E: extended regex
        # -i: case-insensitive
        # -n: 显示行号
        # -C 1: 显示前后 1 行上下文
        # -h: 不显示文件名（单文件）
        # --max-count=1000: 限制命中行数（防大日志 OOM）
        pattern = "|".join(_LOG_KEYWORDS)
        cmd = [
            self.binary_path or "grep",
            "-E", "-i", "-n", "-h", "-C", "1",
            "--max-count=1000",
            pattern,
            file_path,
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描（捕获 flag{...}）
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 命中行解析 + 关键字严重度
        for line in stdout.splitlines():
            line_lower = line.lower()

            # 跳过 "--" 上下文分隔行
            if line.startswith("--"):
                continue

            # 提取行号（格式: "42:..."）
            m = re.match(r"^(\d+):(.*)$", line)
            if not m:
                continue
            line_no, content = int(m.group(1)), m.group(2)

            # 命中严重关键字
            for kw in _LOG_KEYWORDS:
                if kw in line_lower:
                    severity = 4 if kw in ("password", "secret", "private_key", "apikey", "api_key", "webshell", "behinder", "caidao") else 2
                    suspicious.append(
                        SuspiciousPoint(
                            id="",
                            tool_name=self.name,
                            file_path=file_path,
                            category="log_keyword",
                            offset=line_no,
                            matched_pattern=f"line {line_no}: kw={kw!r} content={content[:120]!r}",
                            severity=severity,
                            suggested_action=f"日志命中关键字 {kw!r}，建议检查上下文",
                        )
                    )
                    break  # 每行只报一个最强关键字

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
