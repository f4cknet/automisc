"""Action: binwalk -e 自动分离文件 (v0.5-DAG-chain).

输入 context: file_path
输出 context: extract_dir + extracted_files (路径列表)

v0.5 改进:
- binwalk -e 在 macOS 上 silent 失败（需要 dd 工具）
- fallback 到 foremost (更可靠)
- binwalk 仅作 detection (不在 extraction)
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


def _find_foremost_extract(output_dir: Path) -> list[str]:
    """foremost 输出在 ``<output_dir>/<type>/00000NNN.ext``."""
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


class BinwalkExtractAction(Action):
    """binwalk 检测 + foremost 分离 embedded files.

    策略:
    1. 调 ``binwalk <file>`` 检测 (不提取)
    2. 调 ``foremost -t all -i <file> -o <dir>`` 提取 (macOS 可靠)
    3. 解析 foremost 输出目录结构

    注: binwalk -e 在 macOS 上需要 dd 工具支持, 静默失败.
    v0.1 简化为 binwalk 检测 + foremost 提取.
    """

    name = "binwalk_extract"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(success=False, message="file_path missing in context")

        src = Path(file_path)
        if not src.exists():
            return ActionResult(success=False, message=f"file not found: {src}")

        # 提取目录
        extract_dir = context.get("extract_dir")
        if extract_dir:
            extract_dir = Path(extract_dir)
        else:
            extract_dir = Path(tempfile.mkdtemp(prefix="binwalk_"))

        extract_dir.mkdir(parents=True, exist_ok=True)

        # 1) binwalk 检测
        binwalk = shutil.which("binwalk")
        if not binwalk:
            return ActionResult(
                success=False,
                message="binwalk not found in PATH",
            )

        try:
            detect_proc = subprocess.run(
                [binwalk, str(src)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message=f"binwalk detection timeout on {src}",
            )
        except Exception as e:  # noqa: BLE001
            return ActionResult(
                success=False,
                message=f"binwalk detection failed: {e}",
            )

        binwalk_stdout = detect_proc.stdout

        # 2) foremost 提取 (macOS 可靠)
        foremost = shutil.which("foremost")
        if not foremost:
            return ActionResult(
                success=False,
                message="foremost not found in PATH",
            )

        # foremost 必须在独立 output 目录, 否则 'output directory already exists' error
        foremost_dir = extract_dir / "foremost_out"
        if foremost_dir.exists():
            import shutil as _sh
            _sh.rmtree(foremost_dir)
        foremost_dir.mkdir(parents=True, exist_ok=True)

        try:
            extract_proc = subprocess.run(
                [foremost, "-t", "all", "-i", str(src), "-o", str(foremost_dir)],
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message=f"foremost timeout after 120s on {src}",
            )
        except Exception as e:  # noqa: BLE001
            return ActionResult(
                success=False,
                message=f"foremost failed: {e}",
            )

        extracted_files = _find_foremost_extract(foremost_dir)

        if not extracted_files:
            stderr_text = extract_proc.stderr.decode("utf-8", errors="replace")[:200]
            return ActionResult(
                success=False,
                message=(
                    f"foremost exit={extract_proc.returncode} but no files extracted "
                    f"(stderr: {stderr_text})"
                ),
                data={
                    "extract_dir": str(extract_dir),
                    "foremost_dir": str(foremost_dir),
                    "extracted_files": [],
                    "binwalk_stdout": binwalk_stdout[:500],
                },
            )

        return ActionResult(
            success=True,
            message=(
                f"foremost extracted {len(extracted_files)} files to {foremost_dir} "
                f"(binwalk detected: {len(binwalk_stdout.splitlines())} patterns)"
            ),
            data={
                "extract_dir": str(extract_dir),
                "foremost_dir": str(foremost_dir),
                "extracted_files": extracted_files,
                "binwalk_stdout": binwalk_stdout[:500],
            },
        )


__all__ = ["BinwalkExtractAction"]
