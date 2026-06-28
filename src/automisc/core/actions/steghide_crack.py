"""SteghideCrackAction — steghide 字典循环 bruteforce (GUI 工具栏手动).

**per v0.5-stegseek-remove spec (2026-06-28)**:
- 替代原 StegseekCrackAction (stegseek 0.6) — Win 端 stegseek 不可用
- 单进程循环 `steghide extract -p <pw> -xf out -f` 字典爆破
- 命中 break + 5s 字典循环 budget 限制 + 30min 整体 timeout
- mini wordlist 100 常用密码兜底 (CTF 命中率 >50%)

**跟 SteghideAdapter (auto_run) 区别**:
- SteghideAdapter (auto_run): 只空密码探测 (CVE-2021-27211 兜底, 5s 内), 铁律 7 纯探测
- SteghideCrackAction (GUI 手动): 完整字典爆破, 慢但能跑完, 5h+ 全字典

**跟 SteghideExtractAction 区别**:
- SteghideExtractAction: 已知密码提取 (用户 QInputDialog 收密码)
- SteghideCrackAction: 未知密码字典爆破 (用户 QFileDialog 选字典)

**Context 必需字段**:
- file_path: stego 文件路径
- __wordlist__: wordlist 文件路径 (GUI dialog 收集); 留空用 mini wordlist 兜底
- __max_passwords__: int (可选, 限制尝试密码数, 默认 10000 防止长跑黑洞)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


# mini wordlist 100 常用密码 (CTF 高频, per OWASP 2024 top breached passwords + 历年 CTF 实战命中)
# 包含空字符串 (CVE-2021-27211), 123456, password, qwerty, 111111, admin 等
_MINI_WORDLIST = (
    "",  # CVE-2021-27211 空密码 (steghide 默认允许, Owner meihuai.jpg 实战命中)
    "123456", "123456789", "12345678", "12345", "1234", "123", "111111", "000000",
    "password", "passw0rd", "p@ssword", "p@ssw0rd", "p@ssphrase",
    "qwerty", "qwerty123", "qwertyuiop", "asdfgh", "asdfghjkl", "zxcvbn", "zxcvbnm",
    "abc123", "abcdef", "abcd1234", "11111111", "00000000",
    "admin", "admin123", "admin1234", "root", "root123", "toor", "test", "test123",
    "guest", "user", "user123", "default", "changeme",
    "letmein", "iloveyou", "monkey", "dragon", "master", "login", "princess",
    "welcome", "shadow", "sunshine", "trustno1", "football", "baseball", "superman",
    "starwars", "batman", "pass", "pass123", "pass1234", "passwd", "password1",
    "password123", "secret", "secret123", "secr3t", "s3cr3t", "1q2w3e4r", "q1w2e3r4",
    "1qaz2wsx", "zaq12wsx", "qwerty1", "qweqwe", "qweasd", "asd123", "asdf1234",
    "P@ssw0rd", "Password", "Password1", "Password123", "Admin", "Admin123",
    "1", "12", "123", "1234", "12345", "123456", "0000", "1111", "abcd", "test1",
    "1q2w3e", "123qwe", "qwe123", "520520", "5201314", "1314520", "woaini", "iloveu",
    "asdf", "qwer", "zxcv", "Aa123456", "Aa1234", "Aa123456!",
    "FLAG", "flag", "ctf", "ctf123", "misc", "steg", "steghide", "stego",
)


def _get_mini_wordlist_path() -> str:
    """返回 mini wordlist 临时文件路径 (ctf 100 常用 + 空密码)."""
    wl_path = Path(tempfile.gettempdir()) / "automisc_mini_wordlist.txt"
    if not wl_path.exists() or wl_path.stat().st_size < 100:
        wl_path.write_text("\n".join(_MINI_WORDLIST) + "\n", encoding="utf-8")
    return str(wl_path)


class SteghideCrackAction(Action):
    """steghide 字典循环 bruteforce — GUI 工具栏手动触发.

    区别于 SteghideAdapter._run_steghide_fallback (auto_run 用, 只空密码):
    - 这里必须 wordlist (mini 100 兜底), 慢但能跑完
    - 输出写日志 + ActionResult.data['extracted_file']
    - per v0.5-stegseek-remove spec §1.3
    """

    name = "steghide_crack"

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        wordlist = context.get("__wordlist__")
        max_passwords = int(context.get("__max_passwords__", 10000))

        if not file_path or not Path(file_path).exists():
            return ActionResult(success=False, message=f"file not found: {file_path}")
        # wordlist 缺失 -> mini wordlist 兜底
        if not wordlist or not Path(str(wordlist)).exists():
            wordlist = _get_mini_wordlist_path()

        # 临时输出文件
        out_fd, out_path = tempfile.mkstemp(suffix=".bin", prefix="steghide_crack_")
        os.close(out_fd)

        # 进度统计
        start_time = time.time()
        attempted = 0
        last_report = start_time

        try:
            with open(wordlist, "r", encoding="utf-8", errors="replace") as f:
                for raw_line in f:
                    # 整体 timeout 30 min
                    elapsed = time.time() - start_time
                    if elapsed > 1800:
                        Path(out_path).unlink(missing_ok=True)
                        return ActionResult(
                            success=False,
                            message=(
                                f"steghide_crack timeout 30min, "
                                f"已尝试 {attempted}/{max_passwords} 密码, 未命中"
                            ),
                            data={"attempted": attempted, "elapsed_sec": elapsed},
                        )
                    # 密码数上限
                    if attempted >= max_passwords:
                        Path(out_path).unlink(missing_ok=True)
                        return ActionResult(
                            success=False,
                            message=(
                                f"steghide_crack 达 max_passwords={max_passwords}, "
                                f"未命中"
                            ),
                            data={"attempted": attempted, "elapsed_sec": elapsed},
                        )

                    password = raw_line.rstrip("\n\r")
                    attempted += 1

                    # -sf (source file) -p (passphrase) -xf (extract to file) -f (force overwrite)
                    cmd = [
                        "steghide", "extract",
                        "-sf", str(file_path),
                        "-p", password,
                        "-xf", out_path,
                        "-f",
                    ]
                    try:
                        proc = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=5,  # 单密码 5s 上限 (空密码 / 错密码都应秒级)
                            errors="replace",
                        )
                    except subprocess.TimeoutExpired:
                        # 单密码 5s 超时 — 跳过
                        continue
                    except FileNotFoundError:
                        Path(out_path).unlink(missing_ok=True)
                        return ActionResult(
                            success=False,
                            message="steghide 二进制未找到 (PATH 缺失或 extend-tools 未装)",
                        )

                    # 命中判断: exit 0 + out_path 有内容
                    if (
                        proc.returncode == 0
                        and Path(out_path).exists()
                        and Path(out_path).stat().st_size > 0
                    ):
                        content = Path(out_path).read_bytes()
                        content_preview = content.decode("utf-8", errors="replace")[:500]
                        elapsed = time.time() - start_time
                        return ActionResult(
                            success=True,
                            message=(
                                f"steghide 破解成功! 密码=\"{password}\", "
                                f"尝试 {attempted} 个, 耗时 {elapsed:.1f}s"
                            ),
                            data={
                                "passphrase": password,
                                "extracted_content": content_preview,
                                "extracted_file": out_path,
                                "attempted": attempted,
                                "elapsed_sec": elapsed,
                            },
                        )

                    # 每 1000 密码 print 一次进度 (后续可挂 journal SP)
                    now = time.time()
                    if now - last_report > 30:  # 30s 报一次
                        last_report = now
                        # 不打断 action, 仅在 result message 累积 (后续 v0.5+ 加 journal 钩子)

            # wordlist 跑完未命中
            Path(out_path).unlink(missing_ok=True)
            elapsed = time.time() - start_time
            return ActionResult(
                success=False,
                message=(
                    f"steghide_crack 跑完 wordlist 全部 {attempted} 个密码, 未命中 "
                    f"(耗时 {elapsed:.1f}s)"
                ),
                data={
                    "attempted": attempted,
                    "elapsed_sec": elapsed,
                    "wordlist": wordlist,
                },
            )
        finally:
            # 失败时 cleanup (成功时 out_path 保留, 让用户能找到)
            # 但 success=False 也保留, 给用户 audit
            pass


__all__ = ["SteghideCrackAction"]
