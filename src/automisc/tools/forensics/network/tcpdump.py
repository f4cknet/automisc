"""tcpdump adapter（per ``tools.md`` §3.3）

``tcpdump``：libpcap 经典 CLI，pcap 解析 fallback。

**v0.1 范围**（最小可用）：
- ``-r <file> -nn -tttt`` 读 pcap + 数字端口 + 人类可读时间戳
- 限制最大 1000 行（防止大文件 OOM）
- 主要作为 tshark 不可用时的 fallback（tshark 输出更结构化）

**可疑点提取**：
- tshark 已覆盖的 flag / 关键字 / base64 扫描同样适用
- macOS 自带，subprocess PATH 沙箱处理已由 ``_run_subprocess`` 解决
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


@register_tool
class TcpdumpAdapter(ToolAdapter):
    """`tcpdump` adapter —— pcap 解析 fallback（macOS 自带）。"""

    name = "tcpdump"
    category = "forensics_network"
    description = "libpcap CLI 端 — pcap 解析 fallback（macOS 自带）"

    default_timeout = 60.0

    def run(self, file_path: str) -> ToolResult:
        # -r: read pcap; -nn: 数字端口 (no name resolution); -tttt: human-readable timestamp
        # -c 1000: limit packets to prevent OOM on huge pcaps
        cmd = [
            self.binary_path or "tcpdump",
            "-r", file_path,
            "-nn",
            "-tttt",
            "-c", "1000",
        ]

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
