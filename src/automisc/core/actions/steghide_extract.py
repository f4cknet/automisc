"""SteghideExtractAction — steghide 指定密码提取 (GUI 工具栏用户输入密码).

**per v0.5-stegseek-remove spec (2026-06-28)**:
- 替代原 StegseekExtractAction 逻辑 (去 stegseek 优先分支)
- 统一走 steghide extract -p <pw> -xf out -f
- 输出到 input 同目录 / <stem>__steghide_extract/extracted.bin (per v0.5-output-samedir)

**跟 SteghideCrackAction 区别**:
- SteghideExtractAction: 已知密码 (用户 QInputDialog 收)
- SteghideCrackAction: 未知密码字典爆破 (用户 QFileDialog 选字典)

**Context 必需字段**:
- file_path: stego 文件路径
- __password__: 用户输入的密码 (空字符串合法, per CVE-2021-27211)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


class SteghideExtractAction(Action):
    """steghide extract 模式 — GUI 工具栏用户输入密码.

    per v0.5-stegseek-remove: 删原 stegseek --crack 单行 wordlist 路径, 统一 steghide extract.
    """

    name = "steghide_extract"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        password = context.get("__password__")

        if not file_path or not Path(file_path).exists():
            return ActionResult(success=False, message=f"file not found: {file_path}")
        if password is None:
            # 区分 "用户没输入" (None) 和 "用户输入了空密码" ("")
            # 空密码在 steghide 是合法密码 (CTF 常见, e.g. 123456cry.jpg good-已合并.jpg)
            return ActionResult(
                success=False,
                message="password not provided (GUI dialog 应已传入)",
            )

        # 输出到 input 同目录 / <stem>__steghide_extract (per v0.5-output-samedir)
        outdir = Path(file_path).parent / f"{Path(file_path).stem}__steghide_extract"
        outdir.mkdir(exist_ok=True)
        out_file = outdir / "extracted.bin"

        # steghide extract: `steghide extract -sf X -p PW -xf OUT -f`
        cmd = [
            "steghide", "extract",
            "-sf", str(file_path),
            "-p", password,
            "-xf", str(out_file),
            "-f",  # force overwrite
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                errors="replace",
            )
        except FileNotFoundError:
            return ActionResult(
                success=False,
                message="steghide 二进制未找到 (PATH 缺失或 extend-tools 未装)",
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                message="steghide extract timeout 60s",
            )

        combined = (proc.stdout + "\n" + proc.stderr).lower()

        # 命中: exit 0 + output 文件存在 + 有内容
        if proc.returncode == 0 and out_file.exists() and out_file.stat().st_size > 0:
            content = out_file.read_bytes()
            content_preview = content.decode("utf-8", errors="replace")[:500]
            return ActionResult(
                success=True,
                message=(
                    f"steghide 提取成功! 密码正确, 内容={content_preview[:200]}"
                ),
                data={
                    "extracted_file": str(out_file),
                    "extracted_content": content_preview,
                },
            )

        # 错密码
        if "could not extract any data" in combined or "incorrect passphrase" in combined:
            return ActionResult(
                success=False,
                message=(
                    f"密码错误 (extracted_file="
                    f"{out_file if out_file.exists() else '未生成'})"
                ),
            )

        # 其他错误
        return ActionResult(
            success=False,
            message=f"steghide extract 失败 (exit={proc.returncode}): {proc.stderr[:200]}",
        )


__all__ = ["SteghideExtractAction"]
