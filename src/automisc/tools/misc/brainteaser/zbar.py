"""zbar adapter（per ``tools.md`` §3.11）

``zbarimg``：zbar 项目的图片扫描 CLI，**支持 QR / EAN-13 / Code-128 / PDF417 / DataMatrix** 等
30+ 条码格式。

**v0.1 范围**（最小可用 — Brainteaser / QR）：
- ``zbarimg --quiet --raw <file>``：扫描图片，输出识别到的字符串（每行一条）
- 解析输出：识别码类型 + 字符串内容
- 强信号：识别到 `flag{...}` / `ctf{...}` → severity=5（直接拿 flag）
- 弱信号：识别到 URL / 长字符串 → severity=2（可能含线索）

**macOS**：`brew install zbar`（已装 0.23.93）。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# zbarimg --raw 输出格式: "QR-Code:https://example.com" / "CODE-128:ABC123"
# 也可能只是字符串 (--raw 模式不带前缀)
_ZBAR_OUTPUT_RE = re.compile(r"^(?:([\w-]+):)?(.+)$")


@register_tool
class ZbarAdapter(ToolAdapter):
    """`zbarimg` adapter —— QR / 条码识别（zbar CLI，30+ 格式）。"""

    name = "zbar"
    category = "misc_brainteaser"
    description = "QR / 条码识别（zbarimg；QR / EAN-13 / Code-128 / PDF417 等 30+ 格式）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # --quiet: 抑制除结果外的输出
        # --raw: 不输出码类型前缀（仅字符串；让 flag 扫描更容易命中）
        cmd = [self.binary_path or "zbarimg", "--quiet", "--raw", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描（捕获 flag{...}）
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 解析每条识别结果
        # 注意：zbarimg --raw 输出**只**有字符串，没有码类型前缀
        # 但 stdout 里可能含 "scheme:..." 形式（如 https://...），要把 scheme 识别为 code_type
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            # 1) 检测 URL scheme（含 ://）
            url_match = re.match(r"^(https?|ftp|file)://(.+)$", line)
            if url_match:
                code_type, content = url_match.group(1), url_match.group(2)
            else:
                m = _ZBAR_OUTPUT_RE.match(line)
                if not m:
                    continue
                code_type = m.group(1) or "unknown"
                content = m.group(2).strip()

            if not content:
                continue

            # 长度 > 50 的字符串（可能是 base64/URL）
            if len(content) > 50:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_long_content",
                        offset=None,
                        matched_pattern=f"{code_type}: {content[:120]!r} (len={len(content)})",
                        severity=2,
                        suggested_action="长字符串可能是 base64/URL/编码内容，建议 base64/hex 解码或访问 URL",
                    )
                )
            # 看起来像 URL（之前 URL scheme 的 content 可能以 / 开头）
            elif content.startswith(("/", "//", "?", "&")) or code_type in ("http", "https", "ftp", "file"):
                # 拼回完整 URL
                full_url = f"{code_type}:{content}" if not content.startswith("//") else f"{code_type}:/{content}"
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_url",
                        offset=None,
                        matched_pattern=f"{code_type}: {full_url[:120]!r}",
                        severity=2,
                        suggested_action="URL 线索：在浏览器访问或 curl 抓内容",
                    )
                )
            # 短字符串（正常识别结果）
            else:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_text",
                        offset=None,
                        matched_pattern=f"{code_type}: {content[:80]!r}",
                        severity=1,
                        suggested_action="记录识别内容",
                    )
                )

        # 3. 报告识别数量
        n = sum(1 for line in stdout.splitlines() if line.strip())
        if n > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="barcode_meta",
                    offset=None,
                    matched_pattern=f"识别 {n} 个条码/二维码",
                    severity=1,
                    suggested_action="记录识别数量",
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
