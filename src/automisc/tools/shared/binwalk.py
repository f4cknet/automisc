"""binwalk adapter（per ``tools.md`` §3.5）

``binwalk``：扫描文件中嵌入的文件（firmware / CTF 套娃必备）。

v0.5-binwalk-extract (2026-06-15) 改造:
- 关键字白名单加 "PEM private key" / "SSH private key" / "RSA private key"
  (per Owner 实测 greatescape.pcap — binwalk 扫到 PEM 私钥但 adapter 报 0 SP)
- 扫描后自动调 ``binwalk -e`` 提取嵌入文件到 input 同目录
  (per Owner "理论上流量中包含的文件应该可以通过 foremost 提取吧" — binwalk 同理)
- 提取路径写入 SuspiciousPoint context / suggested_action

**v0.5 推翻旧定论**:
- 之前文档里 "binwalk 在 macOS 兼容性问题" 的结论作废
- binwalk CLI 在 macOS 完全可用，bug 在 adapter 层关键字白名单过窄
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.core.utils.output_path import extract_dir_for
from automisc.tools.base import ToolAdapter


# binwalk 输出行格式: "<DECIMAL>       <HEXADECIMAL>     <DESCRIPTION>"
_BINWALK_LINE_RE = re.compile(
    r"^\s*(\d+)\s+0x[0-9a-fA-F]+\s+(.+)$"
)

# DESCRIPTION 中的常见文件 magic → 强可疑（建议 foremost / binwalk -e 分离）
_FILE_HEADER_KEYWORDS = [
    # 现有 17 项 (v0.1 保留)
    "PNG image",
    "JPEG image",
    "GIF image",
    "PDF document",
    "ZIP archive",
    "RAR archive",
    "7-zip archive",
    "gzip compressed",
    "bzip2 compressed",
    "xz compressed",
    "tar archive",
    "ELF ",
    "PE32 ",
    "Microsoft Office",
    "OpenDocument",
    "pcap",
    # v0.5-binwalk-extract 新增 (per Owner 实测 greatescape.pcap)
    "PEM private key",   # RSA / EC / generic PEM (OpenSSL)
    "SSH private key",   # OpenSSH 私钥
    "RSA private key",   # 旧版 RSA 私钥
]


@register_tool
class BinwalkAdapter(ToolAdapter):
    """`binwalk` adapter —— 扫描并报告嵌入文件 + binwalk -e 提取到 samedir."""

    name = "binwalk"
    category = "shared"
    description = "扫描并报告文件中的嵌入文件（per magic bytes），支持 binwalk -e 一键提取"

    default_timeout = 60.0  # 大文件扫描可能较慢

    def run(self, file_path: str) -> ToolResult:
        binwalk = self.binary_path or "binwalk"

        # Step 1: binwalk <file> 扫描（保留 v0.1 行为）
        cmd_scan = [binwalk, file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd_scan)

        suspicious: list[SuspiciousPoint] = []
        hits: list[tuple[int, str, str]] = []  # (offset, desc, matched_kw)

        for line in stdout.splitlines():
            m = _BINWALK_LINE_RE.match(line)
            if not m:
                continue
            offset = int(m.group(1))
            desc = m.group(2)

            # 命中文件头关键字 → 强可疑（severity 4）
            matched_kw = next(
                (kw for kw in _FILE_HEADER_KEYWORDS if kw.lower() in desc.lower()),
                None,
            )
            if matched_kw:
                hits.append((offset, desc, matched_kw))

        # Step 2: binwalk -e 提取（v0.5-binwalk-extract 新增）
        extracted_files: list[Path] = []
        extract_dir: Path | None = None
        if hits:
            extract_dir = extract_dir_for(file_path, purpose="binwalk_extracted")
            extracted_files = self._extract_files(file_path, extract_dir)

        # Step 3: 把 hits + extracted paths 组装成 SuspiciousPoint
        for offset, desc, matched_kw in hits:
            # 找本 hit 对应的提取文件（offset 匹配子目录名）
            offset_hex = f"{offset:x}".upper()
            related = [
                p for p in extracted_files
                if offset_hex in str(p) or str(offset) in Path(str(p)).name
            ]
            # 用 str 简单拼接（避免 relative_to 在 /tmp vs /private 下的边界问题）
            ext_ctx = (
                ";".join(str(p) for p in related)
                if related
                else ""
            )

            suggestion = f"建议 foremost / binwalk -e 分离（{matched_kw}）"
            if related and extract_dir:
                # 第一个提取文件当主路径
                first = related[0]
                suggestion = (
                    f"已提取 {len(related)} 个文件到 {extract_dir}\n"
                    f"主文件: {first}\n"
                    f"如需用此文件解密 TLS: 配 Wireshark --ssl.keys <server_ip>,<port>,http,<key_path>"
                )

            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="file_header",
                    offset=offset,
                    matched_pattern=f"{matched_kw} @ offset {offset}",
                    severity=4,
                    suggested_action=suggestion,
                    context=f"extracted_files={ext_ctx}" if ext_ctx else desc[:80],
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
            metadata={
                "extracted_files": [str(p) for p in extracted_files],
                "extract_dir": str(extract_dir) if extract_dir else None,
            },
        )

    def _extract_files(self, file_path: str, outdir: Path) -> list[Path]:
        """调 ``binwalk -e`` 提取嵌入文件到 outdir（per v0.5-output-samedir）.

        binwalk 3.1.0 实际行为（macOS verified）:
        - ``--directory <DIR>`` 提取到指定目录（不是 parent）
        - 子目录: ``<DIR>/<file_stem>.extracted/<offset_hex>/<ext>``

        Returns:
            提取出的所有文件路径列表（按 size 降序）
        """
        binwalk = self.binary_path or "binwalk"

        # 清理旧输出（binwalk 会因目录非空而 exit 1）
        if outdir.exists():
            shutil.rmtree(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        # binwalk 3.x: --directory 是目标目录本身（不是 parent）
        cmd = [
            binwalk,
            "-e",                        # extract
            "--directory", str(outdir),  # 提取到 outdir
            file_path,
        ]
        # exit code 非 0 也无所谓（提取可能部分成功）
        self._run_subprocess(cmd)

        # binwalk 3.1.0 实际产出: <outdir>/<file_stem>.extracted/<offset_hex>/<ext>
        # 兼容两种 stem 命名（带 .extracted 后缀 或 不带）
        candidates = [
            outdir / (Path(file_path).stem + ".extracted"),
            outdir / Path(file_path).stem,
        ]
        stem_dir = next((c for c in candidates if c.exists()), outdir)
        # 收集所有文件，按 size 降序（最重要的排前面）
        files = [p for p in stem_dir.rglob("*") if p.is_file()]
        files.sort(key=lambda p: -p.stat().st_size)
        return files


__all__ = ["BinwalkAdapter"]
