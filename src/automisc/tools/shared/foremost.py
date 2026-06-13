"""foremost adapter（per ``tools.md`` §3.5）

``foremost -t all -o <outdir> -i <file>``：文件雕刻（carving）。
"""
from __future__ import annotations

import re
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


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
        # foremost 必须有 -o 输出目录（不存在会自动创建）
        # 临时目录放到 /tmp 下；foremost 拒绝非空目录，先清后用
        outdir = Path("/tmp") / f"automisc_foremost_{Path(file_path).stem}"

        # 清理旧输出目录（foremost 会因目录非空而 exit 1）
        import shutil
        if outdir.exists():
            shutil.rmtree(outdir)

        cmd = [
            self.binary_path or "foremost",
            "-t", "all",  # 全部类型
            "-i", file_path,
            "-o", str(outdir),
            "-q",  # 安静模式（少噪声）
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        # 扫描 foremost 输出目录，找出分离出的文件
        if outdir.exists():
            extract_dir = outdir / "FOREMOST"
            if extract_dir.exists():
                extracted_files = sorted(extract_dir.iterdir())
                if extracted_files:
                    # 汇总一条 summary 可疑点
                    file_list = "\n".join(
                        f"  {f.name} ({f.stat().st_size} bytes)"
                        for f in extracted_files[:20]
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
                                f"-> {extract_dir}\n{file_list}"
                            ),
                            severity=4,
                            suggested_action=(
                                f"查看分离文件清单（{extract_dir}）"
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