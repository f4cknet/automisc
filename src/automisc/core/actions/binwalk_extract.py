"""Action: binwalk -e 自动分离文件.

输入 context: file_path
输出 context: extract_dir + extracted_files (路径列表)
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


class BinwalkExtractAction(Action):
    """``binwalk -e <file> -C <extract_dir>`` 自动分离 embedded files.

    binwalk 把文件放在 ``<extract_dir>/_<filename>.extracted/`` 子目录下.
    """

    name = "binwalk_extract"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(success=False, message="file_path missing in context")

        src = Path(file_path)
        if not src.exists():
            return ActionResult(success=False, message=f"file not found: {src}")

        # 提取目录：context.extract_dir 优先，否则 /tmp/binwalk_<随机>
        extract_dir = context.get("extract_dir")
        if extract_dir:
            extract_dir = Path(extract_dir)
        else:
            extract_dir = Path(tempfile.mkdtemp(prefix="binwalk_"))

        extract_dir.mkdir(parents=True, exist_ok=True)

        binwalk = shutil.which("binwalk")
        if not binwalk:
            return ActionResult(
                success=False,
                message="binwalk not found in PATH",
            )

        try:
            proc = subprocess.run(
                [binwalk, "-e", "--run-as=root", str(src), "-C", str(extract_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message=f"binwalk timeout after 120s on {src}",
            )
        except Exception as e:  # noqa: BLE001
            return ActionResult(
                success=False,
                message=f"binwalk failed: {e}",
            )

        # binwalk -e 在 extract_dir 下建 _src.extracted/ 子目录
        actual_extract = extract_dir / f"_{src.name}.extracted"
        extracted_files: list[str] = []
        if actual_extract.exists():
            for p in actual_extract.rglob("*"):
                if p.is_file():
                    extracted_files.append(str(p))

        if not extracted_files:
            return ActionResult(
                success=False,
                message=(
                    f"binwalk exit={proc.returncode} but no files extracted "
                    f"(stderr: {proc.stderr[:200]})"
                ),
                data={
                    "extract_dir": str(extract_dir),
                    "extracted_files": [],
                    "binwalk_stdout": proc.stdout[:500],
                },
            )

        return ActionResult(
            success=True,
            message=f"binwalk extracted {len(extracted_files)} files to {actual_extract}",
            data={
                "extract_dir": str(extract_dir),
                "actual_extract_dir": str(actual_extract),
                "extracted_files": extracted_files,
                "binwalk_stdout": proc.stdout[:500],
            },
        )


__all__ = ["BinwalkExtractAction"]
