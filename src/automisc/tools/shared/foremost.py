"""foremost adapter（per ``tools.md`` §3.5）

``foremost -t all -o <outdir> -i <file>``：文件雕刻（carving）。

v0.5-output-samedir 改造 (2026-06-14):
- 输出目录从 /tmp/automisc_foremost_<stem>/ 改成 <input_dir>/<input_stem>__foremost/
- 原因: Owner "所有文件输出都跟输入同目录"
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
from automisc.tools.paths import resolve_tool_binary


# foremost 输出行格式: "Extract|<TYPE>|<OFFSET>|<LENGTH>|<PATH>"
# 或 "FOREMOST/output/<TYPE>-<OFFSET>.<EXT>"
_FOREMOST_EXTRACT_RE = re.compile(
    r"=+(?P<path>\S+)\s+(?P<size>\d+)\s+bytes\s+extracted\s+=\+"
)


@register_tool
class ForemostAdapter(ToolAdapter):
    """`foremost` adapter —— 文件雕刻（按 magic bytes 分离嵌入文件）。"""

    name = "foremost"
    category = "shared"
    description = "按 magic bytes 雕刻并分离嵌入文件"

    default_timeout = 120.0  # 大文件雕刻可能很慢

    def run(self, file_path: str) -> ToolResult:
        # v0.5-output-samedir: 输出目录 = input 同目录 / <stem>__foremost
        outdir = extract_dir_for(file_path, purpose="foremost")

        # 清理旧输出目录（foremost 会因目录非空而 exit 1）
        if outdir.exists():
            shutil.rmtree(outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.binary_path or resolve_tool_binary("foremost") or "foremost",
            "-t", "all",  # 全部类型
            "-i", file_path,
            "-o", str(outdir),
            # 修 foremost ZIP 提取 bug: foremoset 1.5.7 macOS homebrew 在 -q (quiet) 模式下
            # 会漏掉 ZIP 提取 (实测 -t all -i X -o Y -q → 1 file, -t all -i X -o Y → 2 files).
            # 删 -q 让 foremost 走 verbose 模式, 内部 ZIP 中央目录解析正常.
            # Owner 实测 (2026-06-20 13:11): 命令行 `foremost 123456cry.jpg` (无 flag) 成功分离 zip+jpg.
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        # 修 foremost 输出路径 bug: 实际输出结构是 outdir/<type>/<file>
        # (e.g. outdir/jpg/00000000.jpg, outdir/zip/00000038.zip), 没有 outdir/FOREMOST/ 子目录.
        # 用 rglob 递归扫 outdir, 排除 audit.txt (不是分离文件).
        if outdir.exists():
            extracted_files = sorted(
                p for p in outdir.rglob("*")
                if p.is_file() and p.name != "audit.txt"
            )
            if extracted_files:
                # 汇总一条 summary 可疑点
                file_list = "\n".join(
                    f"  {p.relative_to(outdir)} ({p.stat().st_size} bytes)"
                    for p in extracted_files[:20]
                )
                if len(extracted_files) > 20:
                    file_list += f"\n  ... and {len(extracted_files) - 20} more"
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="extracted_files",
                        offset=None,
                        matched_pattern=(
                            f"foremost 分离出 {len(extracted_files)} 个文件 "
                            f"-> {outdir}\n{file_list}"
                        ),
                        severity=4,
                        suggested_action=(
                            f"查看分离文件清单（{outdir}）"
                        ),
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