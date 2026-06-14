"""Action: foremost -t all 自动分离文件 (v0.5-DAG-chain).

输入 context: file_path
输出 context: extract_dir + foremost_dir + extracted_files (路径列表)

v0.5 设计:
- 替代 binwalk -e (macOS 不可靠, 需 dd 工具)
- foremost 1.5.7 在 macOS 稳定
- 支持任意 file type (-t all)
- 输出结构: <output_dir>/<type>/00000NNN.<ext>

v0.5-output-samedir 改造 (2026-06-14):
- 提取目录从 /tmp/foremost_xxxxxx/ 改成 <input_dir>/<input_stem>__foremost/
- 原因: Owner "所有文件输出都跟输入同目录"
- 跑完不删 (caller 决定; CLI 默认保留, GUI 默认保留)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult
from automisc.core.utils.output_path import extract_dir_for


def find_foremost_extract(output_dir: Path) -> list[str]:
    """扫描 foremost 输出目录, 返回所有提取的文件路径 (排除 audit.txt)."""
    extracted: list[str] = []
    if not output_dir.exists():
        return extracted
    for type_dir in output_dir.iterdir():
        if not type_dir.is_dir():
            continue
        for p in type_dir.iterdir():
            if p.is_file() and p.name != "audit.txt":
                extracted.append(str(p))
    return extracted


class ForemostExtractAction(Action):
    """``foremost -t all -i <file> -o <dir>`` 自动分离 embedded files.

    foremost 把文件放在 ``<output_dir>/<type>/00000NNN.<ext>``.
    输出目录必须不存在 (foremost 限制), 用前会先 rmtree.

    v0.5-output-samedir: 默认 extract_dir = ``<input_dir>/<input_stem>__foremost/``,
    与输入同目录, 不写到 /tmp.
    """

    name = "foremost_extract"

    def __init__(self, file_types: str = "all", timeout: int = 120) -> None:
        self.file_types = file_types  # "all" / "zip,7z" / "png,jpg"
        self.timeout = timeout

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(success=False, message="file_path missing in context")

        src = Path(file_path)
        if not src.exists():
            return ActionResult(success=False, message=f"file not found: {src}")

        # 提取目录 (v0.5-output-samedir: 默认与 input 同目录)
        extract_dir = context.get("extract_dir")
        if extract_dir:
            extract_dir = Path(extract_dir)
        else:
            extract_dir = extract_dir_for(src, purpose="foremost")

        # 清理旧 (foremost 拒绝非空目录)
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        foremost = shutil.which("foremost")
        if not foremost:
            return ActionResult(
                success=False,
                message="foremost not found in PATH",
            )

        # foremost 输出目录 (放 extract_dir 下, foremost 仍要求 "目录不存在")
        foremost_dir = extract_dir / "foremost_out"
        if foremost_dir.exists():
            shutil.rmtree(foremost_dir)
        foremost_dir.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.run(
                [foremost, "-t", self.file_types, "-i", str(src), "-o", str(foremost_dir)],
                capture_output=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message=f"foremost timeout after {self.timeout}s on {src}",
            )
        except Exception as e:  # noqa: BLE001
            return ActionResult(
                success=False,
                message=f"foremost failed: {e}",
            )

        extracted_files = find_foremost_extract(foremost_dir)

        if not extracted_files:
            stderr_text = proc.stderr.decode("utf-8", errors="replace")[:200]
            return ActionResult(
                success=False,
                message=(
                    f"foremost exit={proc.returncode} but no files extracted "
                    f"(stderr: {stderr_text})"
                ),
                data={
                    "extract_dir": str(extract_dir),
                    "foremost_dir": str(foremost_dir),
                    "extracted_files": [],
                },
            )

        return ActionResult(
            success=True,
            message=(
                f"foremost extracted {len(extracted_files)} files to {foremost_dir} "
                f"(types: {self.file_types})"
            ),
            data={
                "extract_dir": str(extract_dir),
                "foremost_dir": str(foremost_dir),
                "extracted_files": extracted_files,
            },
        )


__all__ = ["ForemostExtractAction", "find_foremost_extract"]
