"""Forensics/Audio + Video + Image steghide 共用 logic（v0.1.0b-PR4）

steghide 支持的格式：JPEG / BMP / WAV / AU
- image 用 steganography/image/steghide.py（PR2）
- audio 用 steganography/audio/steghide_audio.py（PR4，**复用 PR2 逻辑**）

这两个 adapter 的核心逻辑（steghide info / extract）相同，
只是 GUI 菜单分类不同。所以本文件只包一个 thin wrapper：
实际命令调用 steghide 命令，仅改 ``name`` / ``category`` / ``description``。
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# 复用 PR2 steghide.py 的正则 + hint
import re
_STEGHIDE_CAPACITY_RE = re.compile(r"capacity:\s*(?P<cap>\d+\.?\d*)\s*(?P<unit>[KMG]B)")
_STEGHIDE_EMBED_RE = re.compile(r"embeds:\s*(?P<n>\d+)\s+files?")
_HAS_DATA_HINTS = [
    "could not extract any data with that passphrase",
    "the embedded data has been encrypted",
]
_UNAVAILABLE_HINTS = [
    "can not read input file",
    "could not get terminal attributes",
]


@register_tool
class SteghideAudioAdapter(ToolAdapter):
    """`steghide` audio wrapper —— 仅 name/category 区别于 image 版。"""

    name = "steghide_audio"
    category = "steganography_audio"
    description = "WAV/AU 隐写检测（steghide 同 binary，仅 audio 入口）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        cmd = [self.binary_path or "steghide", "info", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

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
                            "音频文件含 steghide 嵌入，建议 GUI 触发 "
                            "`steghide extract -p <password>` 提取"
                        ),
                    )
                )
                break

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

        for hint in _UNAVAILABLE_HINTS:
            if hint in combined:
                matched = "steghide 编译未启用此格式" if hint == "can not read input file" else "steghide 需要 tty 环境"
                action = (
                    "macOS 自带 steghide 编译时未启用此格式；brew install steghide --with-jpeg"
                    if hint == "can not read input file"
                    else "steghide 在 GUI/终端 tty 环境调用正常；subprocess 环境无 tty 校验失败"
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
                break

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
