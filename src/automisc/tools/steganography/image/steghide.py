"""steghide adapter（per ``tools.md`` §3.5）

``steghide``：JPEG/BMP/WAV/AU 隐写（**注意**：macOS 默认 steghide 编译时**未启用 JPEG 支持**，per 实测。

**v0.1.0b-PR2 范围**：
- adapter 主调用 ``steghide info`` —— **不需要密码**就能报告文件是否含嵌入数据
- 如果用户有密码，GUI 触发 ``steghide extract -p <password>`` 写到指定 outdir
- adapter 仅暴露 info 路径（无密码安全 + 无临时文件责任）

**steghide info 输出格式**：
- 成功嵌入：``"<filename>": format: ... capacity: ...``，含嵌入数据信息
- 错密码：``steghide: could not extract any data with that passphrase!``
- 无嵌入：``steghide: the file "<name>" does not contain any steghide data.``
- 不支持格式：``steghide: can not read input file. ...``
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# steghide info 成功时的关键行（无密码也能获取的信息）
_STEGHIDE_CAPACITY_RE = re.compile(r"capacity:\s*(?P<cap>\d+\.?\d*)\s*(?P<unit>[KMG]B)")
_STEGHIDE_EMBED_RE = re.compile(r"embeds:\s*(?P<n>\d+)\s+files?")

# 错密码的强信号（说明文件 100% 含嵌入数据）
_HAS_DATA_HINTS = [
    "could not extract any data with that passphrase",
    "the embedded data has been encrypted",
]

# steghide 调用失败的常见原因（macOS 编译限制 + 无 tty）
_UNAVAILABLE_HINTS = [
    "can not read input file",  # 格式不支持
    "could not get terminal attributes",  # 无 tty 环境
]


@register_tool
class SteghideAdapter(ToolAdapter):
    """`steghide` adapter —— 检测文件是否含 steghide 嵌入数据。"""

    name = "steghide"
    category = "steganography_image"
    description = "JPEG/BMP/WAV/AU 隐写检测（无密码信息探测 + GUI 触发口令爆破）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # steghide info 不需要密码——仅报告容量 + 是否含嵌入
        # 注意 1：macOS 自带 steghide 默认未编译 JPEG 支持，
        #       会对 .jpg 报 "can not read input file"，视为强信号（unavailable）
        # 注意 2：steghide 在**无 tty** 环境（CI / subprocess 调用）报错
        #       "could not get terminal attributes"——这是 steghide 的限制，
        #       adapter 不应崩溃；GUI 触发时用户在 tty 下调用 OK
        cmd = [self.binary_path or "steghide", "info", file_path]
        # steghide info 会在错密码时返回 1，但仍有有用信息——不设 check
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

        # 信号 1：文件含嵌入数据（错密码信号）
        for hint in _HAS_DATA_HINTS:
            if hint in combined:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="steghide_embedded",
                        offset=None,
                        matched_pattern=f"steghide: {hint}",
                        severity=5,
                        suggested_action=(
                            "文件确认含 steghide 嵌入！建议在 GUI 中触发 "
                            "`steghide extract -p <password>` 提取（口令爆破可用 stegseek）"
                        ),
                    )
                )
                break

        # 信号 2：容量信息（无嵌入数据时输出）
        for m in _STEGHIDE_CAPACITY_RE.finditer(stdout):
            cap = m.group("cap") + m.group("unit")
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="steghide_capacity",
                    offset=None,
                    matched_pattern=f"steghide capacity: {cap}",
                    severity=1,
                    suggested_action="记录容量，便于估算嵌入数据大小",
                )
            )

        # 信号 3：嵌入文件数
        for m in _STEGHIDE_EMBED_RE.finditer(stdout):
            n = m.group("n")
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="steghide_embeds",
                    offset=None,
                    matched_pattern=f"steghide embeds: {n} files",
                    severity=3,
                    suggested_action=f"steghide 嵌入了 {n} 个文件，建议提取查看",
                )
            )

        # 信号 4：steghide 不支持格式（macOS 编译限制）/ 无 tty
        for hint in _UNAVAILABLE_HINTS:
            if hint in combined:
                if hint == "can not read input file":
                    matched = "steghide 编译未启用此格式支持（macOS 限制）"
                    action = (
                        "macOS 自带 steghide 编译时未启用此格式；"
                        "建议 brew install steghide --with-jpeg 或换工具（outguess）"
                    )
                else:  # could not get terminal attributes
                    matched = "steghide 需要 tty 环境（无 GUI 终端时不可用）"
                    action = (
                        "steghide 在 GUI/终端 tty 环境调用正常；"
                        "当前 subprocess 环境无 tty 触发其 isatty() 校验失败"
                    )
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="steghide_unavailable",
                        offset=None,
                        matched_pattern=matched,
                        severity=1,
                        suggested_action=action,
                    )
                )
                break  # 只报第一个 unavailable 提示

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )