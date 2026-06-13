"""xxd adapter（per ``tools.md`` §3.12）

``xxd -l 256``：dump 前 256 字节 hex + ASCII（避免大文件爆炸）。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# xxd 输出行: "<offset>: <hex bytes>  <ascii>"
# 例: "00000000: 6865 6c6c 6f20 776f 726c 6420 666c 6167  hello world flag"
_XXD_LINE_RE = re.compile(
    r"^(?P<offset>[0-9a-fA-F]+):\s+(?P<hex>[0-9a-fA-F ]+?)\s{2,}(?P<ascii>.*)$"
)

# 已知文件 magic bytes（前 4 字节）
_KNOWN_MAGIC = {
    b"\x89PNG\r\n\x1a\n": ("PNG", "image"),
    b"\xff\xd8\xff": ("JPEG", "image"),
    b"GIF87a": ("GIF87a", "image"),
    b"GIF89a": ("GIF89a", "image"),
    b"%PDF": ("PDF", "document"),
    b"PK\x03\x04": ("ZIP", "archive"),
    b"Rar!\x1a\x07": ("RAR", "archive"),
    b"7z\xbc\xaf\x27\x1c": ("7z", "archive"),
    b"\x1f\x8b": ("gzip", "archive"),
    b"BZh": ("bzip2", "archive"),
    b"\xfd7zXZ": ("xz", "archive"),
    b"MZ": ("PE/EXE", "binary"),
    b"\x7fELF": ("ELF", "binary"),
    b"\xca\xfe\xba\xbe": ("Java class", "binary"),
}


@register_tool
class XxdAdapter(ToolAdapter):
    """`xxd` adapter —— hex dump 前 256 字节（含 ASCII）。"""

    name = "xxd"
    category = "shared"
    description = "hex dump 文件前 256 字节（含 ASCII 显示）"

    def run(self, file_path: str) -> ToolResult:
        # -l 256: 只 dump 前 256 字节，避免大文件爆炸
        cmd = [self.binary_path or "xxd", "-l", "256", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 识别文件 magic（最常见 CTF 套路：扩展名伪装）
        try:
            with open(file_path, "rb") as f:
                first_bytes = f.read(16)
            for magic, (name, kind) in _KNOWN_MAGIC.items():
                if first_bytes.startswith(magic):
                    suspicious.append(
                        SuspiciousPoint(
                            id="",
                            tool_name=self.name,
                            file_path=file_path,
                            category="file_header",
                            offset=0,
                            matched_pattern=f"{name} magic bytes detected ({first_bytes[:8].hex()})",
                            severity=4,
                            suggested_action=f"确认文件扩展名是否与 {name} ({kind}) 实际类型一致",
                            context=f"first 16 bytes: {first_bytes.hex()}",
                        )
                    )
                    break
        except OSError:
            pass  # 文件读取失败不影响 xxd 主流程

        # 2. 关键字扫描（xxd 输出含 ASCII 列）
        from automisc.core.suspicious import scan_output_for_suspicious
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name,
            file_path=file_path,
            stdout=stdout,
        ))

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )