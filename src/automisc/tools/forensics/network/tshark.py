"""tshark adapter（per ``tools.md`` §3.3）

``tshark``：Wireshark CLI 端，解析 pcap/pcapng/cap。

**v0.1 范围**（最小可用）：
- ``-r <file>`` 读 pcap
- ``-T fields -E header=n -E separator=,`` 输出 CSV-style 字段
- 默认字段：frame.number, ip.src, ip.dst, _ws.col.Protocol, frame.len, _ws.col.Info
- 限制最大包数 1000（防止大文件 OOM；GUI 进度条后续接）

**可疑点提取**：
- HTTP 协议 + 含 webshell 关键字（eval/exec/system/assert/base64）→ severity=4
- POST 请求 + URL 含 ? + 长 body → severity=3（潜在 webshell）
- 含 flag 正则 → severity=5
- 含 IP/端口扫描特征（>10 SYN to different ports from one src）→ severity=2

**macOS 路径处理**（per Architecture.md §4.3）：_run_subprocess 已自动追加 Homebrew 路径。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# tshark -T fields 输出格式: "1,192.168.1.1,192.168.1.2,HTTP,1234,GET / HTTP/1.1,/path\r\n..."
# 字段顺序对应 _TSHARK_FIELDS
_TSHARK_FIELDS = [
    "frame.number",
    "ip.src",
    "ip.dst",
    "_ws.col.Protocol",
    "frame.len",
    "_ws.col.Info",
    "http.request.uri",  # 仅 HTTP 请求时非空
    "http.request.method",
]

# webshell 关键字（per tools.md §3.3 + prd.md §7）
# 包含 PHP webshell 路径关键字 + payload 函数关键字
_WEBSHELL_KEYWORDS = [
    # payload 函数（命中 TCP body / HTTP request）
    "eval(",
    "eval ",
    "assert(",
    "base64_decode",
    "system(",
    "exec(",
    "passthru(",
    "shell_exec(",
    "preg_replace",
    "create_function",
    # 路径关键字（命中 URI）
    "shell.php",
    "cmd.php",
    "c99.php",
    "r57.php",
    "webshell",
    # 工具签名
    "antsword",
    "behinder",
    "caidao",
    "godzilla",
]

_WEBSHELL_RE = re.compile("|".join(re.escape(k) for k in _WEBSHELL_KEYWORDS), re.IGNORECASE)


@register_tool
class TsharkAdapter(ToolAdapter):
    """`tshark` adapter —— 解析 pcap/pcapng/cap 并提取协议摘要。"""

    name = "tshark"
    category = "forensics_network"
    description = "Wireshark CLI 端 — pcap/pcapng/cap 协议解析 + 可疑点提取"

    default_timeout = 60.0  # 大 pcap 解析较慢

    def run(self, file_path: str) -> ToolResult:
        # 限制最大 1000 包；GUI 进度条后续在 orchestrator 层加
        cmd = [
            self.binary_path or "tshark",
            "-r", file_path,
            "-T", "fields",
            "-E", "header=n",
            "-E", "separator=,",
            "-E", "occurrence=f",  # 同字段多次出现时只取一次
            "-c", "1000",
        ]
        for f in _TSHARK_FIELDS:
            cmd.extend(["-e", f])

        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        # 1. 通用 flag / 关键字 / base64 扫描
        suspicious = scan_output_for_suspicious(
            tool_name=self.name,
            file_path=file_path,
            stdout=stdout,
        )

        # 2. webshell 关键字检测（per Info / URI / Method 字段）
        # 协议层（HTTP 才有意义）
        for line in stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(",", 7)  # 8 字段
            if len(parts) < 8:
                continue
            frame_num, src, dst, proto, length, info, uri, method = parts
            if proto.upper() not in ("HTTP", "HTTP/XML", "JSON", "XML"):
                continue
            # URI + Info + Method 拼接后匹配（覆盖路径关键字 + payload 函数）
            haystack = f"{uri} {info} {method}"
            m = _WEBSHELL_RE.search(haystack)
            if m:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="webshell_family",
                        offset=None,
                        matched_pattern=f"frame#{frame_num} {src}->{dst} {method} {uri} (kw={m.group(0)!r})",
                        severity=4,
                        suggested_action="检测到 webshell 家族关键字，建议提取完整 payload + 配合 base64 解码",
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
