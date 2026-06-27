"""exiftool adapter（per ``tools.md`` §3.5）

``exiftool``：提取文件元数据（EXIF / Office / PDF metadata）。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# exiftool 输出格式: "<TAG>: <VALUE>"
_EXIFTOOL_LINE_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*?)\s*:\s*(?P<value>.+)$")


def _per_line_redecode(s: str) -> str:
    """Per-line 重 decode exiftool 输出 (绕开 base.py latin-1 fallback).

    背景 (per v0.5-windows-tool-compat PR1):
    - exiftool -charset utf8 输出含 2 段编码: EXIF 字段 UTF-8 + FileName/Directory cp936 字节
    - `base.py:_decode_output_bytes` 整 stdout strict 试 utf-8 → 失败 (cp936 字节非 UTF-8)
      → gbk strict 失败 (UTF-8 字节非 GBK) → ... → latin-1 fallback 永远成功
    - latin-1 1:1 字节映射, UTF-8 中文 EXIF 字段被解码成 latin-1 字符 ("å\\x9b¾ç©·..."), 中文破坏
    - 解决: 按行重 decode, 每行单独试 utf-8 → cp936 → gbk → latin-1, UTF-8 EXIF 行正常显示

    Args:
        s: `base.py:_decode_output_bytes` 解码后的 str (latin-1 fallback 状态)

    Returns:
        Per-line 重 decode 后的 str (中文 EXIF 正常显示, cp936 文件名也正常)
    """
    if not s:
        return s
    raw = s.encode("latin-1")  # 1:1 byte mapping 还原原始 bytes
    lines = []
    for line_bytes in raw.split(b"\n"):
        for enc in ("utf-8", "cp936", "gbk", "latin-1"):
            try:
                lines.append(line_bytes.decode(enc))
                break
            except UnicodeDecodeError:
                continue
        else:
            # 全部失败 (理论上 latin-1 永不失败, 兜底)
            lines.append(line_bytes.decode("latin-1", errors="replace"))
    return "\n".join(lines)

# 比赛高价值 metadata tag（per ctf-forensics/SKILL.md）
_HIGH_VALUE_TAGS = {
    "Author",
    "Title",
    "Subject",
    "Keywords",
    "Comment",
    "Description",
    "Creator",
    "Producer",
    "Company",
    "Software",
    "Creator Tool",
    "Last Modified By",
    "Create Date",
    "Modify Date",
}


@register_tool
class ExiftoolAdapter(ToolAdapter):
    """`exiftool` adapter —— 提取文件元数据。"""

    name = "exiftool"
    category = "shared"
    description = "提取文件元数据（EXIF / Office / PDF）"

    def run(self, file_path: str) -> ToolResult:
        from automisc.tools.paths import resolve_tool_binary
        # per v0.5-windows-tool-compat PR1: -charset utf8 强制 exiftool 按 UTF-8 解码
        # EXIF Unicode 字段 (XP*/XMP/Description/Title 等). 不传时 exiftool 按
        # OS locale (Win = GBK code page) 解码, 中文 EXIF 全乱码 (e.g.
        # "图穷flag见" → "å›¾ç©·flagè§"). Linux/macOS 默认 UTF-8 不回归.
        #
        # 注意: 不加 `-charset filename=utf8` — 那会让 exiftool 用 utf8 解析命令行
        # filename, 但 Win 上 Python subprocess 传 argv 是 GBK 字节, exiftool 解析
        # 失败 → exit 1 "File not found". Win 默认用 cp936 解析 filename 反而正常.
        # EXIF 字段 utf-8 输出 + FileName/Directory cp936 字节混 stdout, _decode_output_bytes
        # latin-1 fallback 会破坏 UTF-8 EXIF 字段 (中文变 "å\x9b¾ç©·..."). 所以 adapter
        # 拿 str 后 per-line 重 decode (utf-8 → cp936 → latin-1).
        cmd = [
            self.binary_path or resolve_tool_binary("exiftool") or "exiftool",
            "-charset", "utf8",
            file_path,
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)
        stdout = _per_line_redecode(stdout)
        stderr = _per_line_redecode(stderr)

        suspicious: list[SuspiciousPoint] = []
        seen_tags: set[str] = set()

        for line in stdout.splitlines():
            m = _EXIFTOOL_LINE_RE.match(line)
            if not m:
                continue
            tag = m.group("key").strip()
            value = m.group("value").strip()

            # 高价值 tag → 强可疑（CTF 经常在 metadata 藏 flag）
            if tag in _HIGH_VALUE_TAGS and value and tag not in seen_tags:
                seen_tags.add(tag)
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="metadata",
                        offset=None,
                        matched_pattern=f"{tag}: {value[:120]}",
                        severity=3,
                        suggested_action=f"检查 {tag} 字段是否含 flag 关键字",
                    )
                )

        # 同时跑通用关键字扫描（flag / keyword / base64）
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