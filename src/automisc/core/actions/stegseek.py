"""Stegseek actions (v0.5-philosophy-rethink GUI 工具栏入口)

跟 SteghideAdapter (auto_run 用, 只做空密码检测) 互补:
- StegseekCrackAction: bruteforce 模式 (GUI 工具栏带 wordlist)
- SteghideExtractAction: 用户指定密码模式 (GUI 工具栏弹密码框)

per Owner 决策 (2026-06-20 13:48):
"auto_run 只做空密码探测, GUI 工具栏 stegseek 可实施三种方式:
 1) 暴力破解 (带 wordlist)
 2) 空密码 (跟 auto_run 一致)
 3) 用户输入指定密码"

模式 2 (空密码) 不走这里 — 跟 auto_run 共用 SteghideAdapter
模式 1 + 3 走这里 — 手工触发, per v0.5 owner 决策 1 "auto_run 不抢 flag"
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


# 跟 SteghideAdapter 共用 regex
_STEGSEEK_PASSPHRASE_RE = re.compile(r'Found passphrase:\s*"([^"]*)"')
_STEGSEEK_FILENAME_RE = re.compile(r'Original filename:\s*"([^"]*)"')
_STEGSEEK_NO_DATA_HINTS = [
    "could not find a valid passphrase",
    "the file could not be decoded",
    "no data was extracted",
    "does not contain any stego data",
]


class StegseekCrackAction(Action):
    """stegseek bruteforce 模式 — GUI 工具栏带 wordlist.

    区别于 SteghideAdapter._run_stegseek (auto_run 用, 只空 wordlist):
    - 这里必须 wordlist (不能空, 否则秒级但没意义)
    - 输出写日志 + ActionResult.data['extracted_files']
    - 慢但能跑完 (per owner 决策 1 "GUI 工具栏可 bruteforce")

    Context 必需字段:
    - file_path: stego 文件路径
    - __wordlist__: wordlist 文件路径 (GUI dialog 收集)
    """

    name = "stegseek_crack"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        wordlist = context.get("__wordlist__")

        if not file_path or not Path(file_path).exists():
            return ActionResult(success=False, message=f"file not found: {file_path}")
        if not wordlist or not Path(wordlist).exists():
            return ActionResult(
                success=False,
                message=f"wordlist not found: {wordlist} (GUI dialog 应已传入)",
            )

        out_fd, out_path = tempfile.mkstemp(suffix=".bin", prefix="stegseek_crack_")
        os.close(out_fd)

        try:
            # -f 防 overwrite 提示触发 tty check
            cmd = ["stegseek", "--crack", "-f", file_path, wordlist, out_path]
            # stegseek 会跑很久 (大 wordlist 可能小时级), 给 30 分钟上限
            import subprocess
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    errors="replace",  # per commit d500d79 修复 binary 输出
                )
                exit_code, stdout, stderr, duration_ms = (
                    proc.returncode, proc.stdout, proc.stderr, 0,
                )
            except subprocess.TimeoutExpired:
                Path(out_path).unlink(missing_ok=True)
                return ActionResult(
                    success=False,
                    message="stegseek timeout after 1800s (wordlist too big?)",
                )

            combined_output = stdout + "\n" + stderr

            # 1. 找到密码
            passphrase_match = _STEGSEEK_PASSPHRASE_RE.search(combined_output)
            if passphrase_match:
                passphrase = passphrase_match.group(1)
                filename_match = _STEGSEEK_FILENAME_RE.search(combined_output)
                original_filename = filename_match.group(1) if filename_match else "?"

                try:
                    content_bytes = Path(out_path).read_bytes()
                    content_preview = content_bytes.decode(
                        "utf-8", errors="replace"
                    )[:500]
                except Exception:
                    content_preview = "(unable to read extracted file)"

                return ActionResult(
                    success=True,
                    message=(
                        f"stegseek 破解成功! 密码=\"{passphrase}\", "
                        f"原始文件名={original_filename}, "
                        f"内容={content_preview[:200]}"
                    ),
                    data={
                        "passphrase": passphrase,
                        "original_filename": original_filename,
                        "extracted_content": content_preview,
                        "extracted_file": out_path,  # 留 tmp 路径给用户看
                    },
                )

            # 2. 没找到密码
            return ActionResult(
                success=False,
                message=(
                    f"stegseek 跑完未找到密码 "
                    f"(wordlist={wordlist}, exit={exit_code})"
                ),
                data={"wordlist": wordlist, "duration_ms": duration_ms},
            )
        finally:
            # 保留 extracted file 不删 (让用户能找到) — 如果成功提取
            # 但失败时也保留 audit
            pass


class SteghideExtractAction(Action):
    """steghide extract 模式 — GUI 工具栏用户输入密码.

    用 steghide (macOS 用户) 或 stegseek --seed 都行, 这里用 steghide
    (因为 extract 需要知道密码, stegseek extract 也支持但 steghide 更原生).

    Context 必需字段:
    - file_path: stego 文件路径
    - __password__: 用户输入的密码 (GUI dialog 收集)
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

        # 输出到 input 同目录 / <stem>__steghide_extract
        outdir = Path(file_path).parent / f"{Path(file_path).stem}__steghide_extract"
        outdir.mkdir(exist_ok=True)

        # 先探一下用 steghide 还是 stegseek (macOS 优先 stegseek)
        binary = "stegseek" if shutil.which("stegseek") else "steghide"

        # steghide extract: `steghide extract -sf X -p PW -xf OUT -f`
        # stegseek extract: 用 --crack + 单行 wordlist (含密码) + -xf OUT
        #                   (stegseek 无独立 extract 子命令)
        out_file = outdir / "extracted.bin"
        if binary == "stegseek":
            # 单行 wordlist (含密码)
            wl = outdir / "_single_pw_wl.txt"
            wl.write_text(password + "\n")
            cmd = [
                "stegseek",
                "--crack", "-f",
                file_path,
                str(wl),
                "-xf", str(out_file),
            ]
        else:
            cmd = [
                "steghide",
                "extract",
                "-sf", file_path,
                "-p", password,
                "-xf", str(out_file),
                "-f",  # force overwrite
            ]  

        import subprocess
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            errors="replace",
        )

        combined = (proc.stdout + "\n" + proc.stderr).lower()

        # steghide / stegseek 提取成功的常见错误模式
        if proc.returncode == 0 and out_file.exists() and out_file.stat().st_size > 0:
            content = out_file.read_bytes()
            content_preview = content.decode("utf-8", errors="replace")[:500]
            return ActionResult(
                success=True,
                message=(
                    f"提取成功! 密码正确, 内容={content_preview[:200]}"
                ),
                data={
                    "extracted_file": str(out_file),
                    "extracted_content": content_preview,
                    "binary": binary,
                },
            )

        # 错密码
        if "could not extract any data" in combined or "incorrect passphrase" in combined:
            return ActionResult(
                success=False,
                message=f"密码错误 (extracted_file={out_file if out_file.exists() else '未生成'})",
            )

        # 其他错误
        return ActionResult(
            success=False,
            message=f"{binary} extract 失败 (exit={proc.returncode}): {proc.stderr[:200]}",
        )


__all__ = ["StegseekCrackAction", "SteghideExtractAction"]
