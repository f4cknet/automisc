"""Action: binwalk 检测 + foremost 提取 (v0.5-DAG-chain).

v0.5 重构:
- binwalk 只做 detection (列 embedded files 偏移)
- foremost 负责实际提取 (macOS 可靠)
- 复用 core/actions/foremost_extract.py

为何:
- binwalk -e 在 macOS 需 dd 工具支持, silent 失败
- foremost 1.5.7 在 macOS 稳定
- 解耦: 检测 vs 提取 可独立替换
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from automisc.core.actions.foremost_extract import ForemostExtractAction
from automisc.core.dag import Action, ActionResult


class BinwalkExtractAction(Action):
    """binwalk 检测 + foremost 提取 (macOS 可靠方案).

    流程:
    1. 调 ``binwalk <file>`` 检测 (列 magic + offset)
    2. 调 ForemostExtractAction 提取所有 embedded files
    3. 返回 binwalk_stdout + extracted_files 列表
    """

    name = "binwalk_extract"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(success=False, message="file_path missing in context")

        src = Path(file_path)
        if not src.exists():
            return ActionResult(success=False, message=f"file not found: {src}")

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

        # 2) foremost 提取 (delegate)
        foremost_action = ForemostExtractAction(file_types="all")
        foremost_result = foremost_action.run(context)

        if not foremost_result.success:
            return ActionResult(
                success=False,
                message=(
                    f"binwalk detected {len(binwalk_stdout.splitlines())} patterns but "
                    f"foremost failed: {foremost_result.message}"
                ),
                data={
                    "binwalk_stdout": binwalk_stdout[:500],
                    "extracted_files": [],
                },
            )

        # 合并 binwalk 检测 + foremost 提取
        return ActionResult(
            success=True,
            message=(
                f"binwalk detected {len(binwalk_stdout.splitlines())} patterns; "
                f"foremost extracted {len(foremost_result.data['extracted_files'])} files"
            ),
            data={
                **foremost_result.data,
                "binwalk_stdout": binwalk_stdout[:500],
            },
        )


__all__ = ["BinwalkExtractAction"]
