"""zsteg adapter（per ``tools.md`` §3.5）

``zsteg``：PNG/BMP LSB 全通道检测（Ruby gem，per tools.md §4 修正）。

**zsteg 输出格式**::

    b1,r,lsb,xy         .. text: "flag{...}"
    b2,rgb,msb,xy       .. file: Zip archive data

**关键匹配模式**：
- ``text:`` 后跟字符串 → flag / 关键字（severity=4）
- ``file:`` 后跟文件类型 → 文件头（severity=5，因为是已知文件 magic）

**v0.1.0b-PR2 范围**：
- 默认 zsteg（不传 -a，速度优先；如需全通道检测 v0.5 加 adapter）
- 解析 text: 和 file: 行
- 不解析 `file: RDI Acoustic Doppler Current Profiler` 等 false positive（关键词白名单）
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# zsteg 输出行格式: "<bit>,<channel>,<order>,<scan>   .. <type>: <content>"
# 例: "b1,r,lsb,xy         .. text: \"flag{test}\""
_ZSTEG_LINE_RE = re.compile(
    r"^(?P<channel>b\d+,\w+,\w+,\w+)\s+\.\.\s+(?P<kind>text|file):\s+(?P<content>.+?)\s*$"
)

# false positive 文件类型白名单（zsteg 偶尔会误判"小写文本"为未知文件格式）
# 命中这些就降级 severity 1（不视为强可疑）
_FALSE_POSITIVE_FILE_PATTERNS = [
    "RDI Acoustic Doppler",
    "AIX core file",
    "MPEG ADTS",
    "old packed data",
    "ddis/ddif",
    "MS Windows COFF PowerPC",
]


@register_tool
class ZstegAdapter(ToolAdapter):
    """`zsteg` adapter —— PNG/BMP LSB 全通道检测。"""

    name = "zsteg"
    category = "steganography_image"
    description = "PNG/BMP LSB 全通道检测（Ruby gem，需 zsteg 可执行）"

    default_timeout = 60.0  # 大图扫描较慢

    def run(self, file_path: str) -> ToolResult:
        # 不传 -a：默认模式（只检 LSB/MSB 各通道），速度优先
        # v0.5 计划加 zsteg_all adapter（-a 全通道）
        cmd = [self.binary_path or "zsteg", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        for line in stdout.splitlines():
            m = _ZSTEG_LINE_RE.match(line)
            if not m:
                continue

            channel = m.group("channel")
            kind = m.group("kind")
            content = m.group("content")

            # 去掉外层引号（如 "flag{...}"）
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]

            # false positive 文件类型 → 降级
            is_fp = any(fp in content for fp in _FALSE_POSITIVE_FILE_PATTERNS)

            if kind == "file":
                severity = 1 if is_fp else 5  # 已知文件 magic = 强可疑
                cat = "file_header_lsb"
                action = (
                    f"zsteg 在 {channel} 通道发现文件 magic（{content}）"
                    + ("，可能是 false positive，建议 foremost 二次验证" if is_fp else "，建议 foremost 分离")
                )
            elif kind == "text":
                severity = 4
                cat = "lsb_text"
                action = f"zsteg 在 {channel} 通道提取到文本，建议检查是否含 flag"
            else:
                continue

            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category=cat,
                    offset=None,
                    matched_pattern=f"{channel}: {content[:120]}",
                    severity=severity,
                    suggested_action=action,
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