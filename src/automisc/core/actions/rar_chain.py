"""Action: RAR 暴力破解（per v0.5-LSB-router 同 session 增量）

**逻辑**：
1. rar2john 生成 hash（写到 tmp）
2. 复用 `_generate_passwords(min_len, max_len)` 字典（同 zip 链）
3. john 跑 `--wordlist` 爆破
4. 用 `unrar` / `7z` 解压验证（v0.5+ 提示用户装 `unar` 或 `unrar`）
5. 找到密码 → 解压

**macOS**：
- `john-jumbo`（已装，1.9.0-jumbo-1，rar2john 路径在 `/usr/local/Cellar/john-jumbo/*/share/john/rar2john`）
- `unrar` / `unar`（**需 Owner 装**：brew install unar；v0.5+ 当前未装）

**v0.5 范围**：
- 爆破 OK（john 找到密码）
- 解压如果 unrar 未装，**告诉用户**手动解压（不报 hard fail）

DAG 转移：
  BruteforceRar.success → 终止
  BruteforceRar.failure → 终止
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult
from automisc.core.actions.zip_chain import _generate_passwords


# john-jumbo 路径（macOS brew 默认）
_JOHN_PATHS = [
    "/usr/local/Cellar/john-jumbo/1.9.0_1/share/john",  # brew 1.9.0
    "/opt/homebrew/Cellar/john-jumbo/1.9.0_1/share/john",  # M1 brew
    "/usr/local/share/john",  # 老 brew
    "/opt/homebrew/share/john",
]


def _find_rar2john() -> str | None:
    """找 rar2john 路径."""
    p = shutil.which("rar2john")
    if p:
        return p
    for base in _JOHN_PATHS:
        cand = os.path.join(base, "rar2john")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _find_john() -> str | None:
    """找 john 主程序."""
    p = shutil.which("john")
    if p:
        return p
    return None


def _find_unar() -> str | None:
    """找 unar（解压 rar 推荐 CLI，brew install unar）."""
    for name in ("unar", "unrar", "7z"):
        p = shutil.which(name)
        if p:
            return p
    return None


class BruteforceRarAction(Action):
    """RAR 密码爆破（john + rar2john）.

    Args:
        min_len: 密码最短长度 (默认 4)
        max_len: 密码最长长度 (默认 6)
    """

    name = "bruteforce_rar"

    def __init__(self, min_len: int = 4, max_len: int = 6):
        self.min_len = min_len
        self.max_len = max_len

    def run(self, context: dict[str, Any]) -> ActionResult:
        rar_path = Path(context.get("file_path", ""))
        if not rar_path.exists():
            return ActionResult(success=False, message=f"file not found: {rar_path}")

        # 前置检查
        rar2john = _find_rar2john()
        john = _find_john()
        if not rar2john:
            return ActionResult(
                success=False,
                message="rar2john 未找到（brew install john-jumbo 装 john-jumbo）",
            )
        if not john:
            return ActionResult(
                success=False,
                message="john 未找到（brew install john-jumbo）",
            )

        # 1. rar2john 生成 hash
        hash_file = tempfile.NamedTemporaryFile(
            delete=False, mode="w", suffix=".hash", prefix="automisc_rar_"
        )
        hash_file.close()
        try:
            r = subprocess.run(
                [rar2john, str(rar_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return ActionResult(
                    success=False,
                    message=f"rar2john 失败: {r.stderr or 'empty hash'}",
                )
            Path(hash_file.name).write_text(r.stdout)

            # 2. 生成字典
            passwords = _generate_passwords(min_len=self.min_len, max_len=self.max_len)
            if context.get("__bruteforce_limit__"):
                passwords = passwords[: int(context["__bruteforce_limit__"])]

            wordlist = tempfile.NamedTemporaryFile(
                delete=False, mode="w", suffix=".txt", prefix="automisc_rar_wordlist_"
            )
            for p in passwords:
                wordlist.write(p + "\n")
            wordlist.close()

            # 3. john 爆破
            john_pot = tempfile.NamedTemporaryFile(
                delete=False, suffix=".pot", prefix="automisc_rar_pot_"
            )
            john_pot.close()

            r = subprocess.run(
                [
                    john,
                    f"--wordlist={wordlist.name}",
                    f"--pot={john_pot.name}",
                    hash_file.name,
                ],
                capture_output=True,
                text=True,
                timeout=600,  # 10min 上限
            )

            # 4. 读 pot 找密码
            pot = Path(john_pot.name).read_text(errors="replace") if Path(john_pot.name).exists() else ""
            # pot 格式: "$rar3$*0*...:password\n"
            password = None
            for line in pot.splitlines():
                if line.startswith("$") and ":" in line:
                    password = line.rsplit(":", 1)[-1]
                    break

            # 清理
            Path(hash_file.name).unlink(missing_ok=True)
            Path(wordlist.name).unlink(missing_ok=True)
            Path(john_pot.name).unlink(missing_ok=True)

            if not password:
                return ActionResult(
                    success=False,
                    message=f"john 未找到密码 (tested {len(passwords)} passwords)",
                    data={"tested": len(passwords)},
                )

            # 5. 找到密码 → 解压（用 unar/unrar/7z）
            unar = _find_unar()
            extract_to = rar_path.parent / f"{rar_path.stem}_bruteforced"
            extract_to.mkdir(exist_ok=True)

            if unar:
                try:
                    r2 = subprocess.run(
                        [unar, "-o", "-p", password, str(rar_path), str(extract_to)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if r2.returncode != 0:
                        # 7z 用不同参数
                        if unar.endswith("7z"):
                            r2 = subprocess.run(
                                [unar, "x", f"-p{password}", f"-o{extract_to}", str(rar_path)],
                                capture_output=True,
                                text=True,
                                timeout=60,
                            )
                except (subprocess.TimeoutExpired, OSError) as e:
                    return ActionResult(
                        success=True,  # 密码找到
                        message=(
                            f"FOUND password={password!r}; "
                            f"但解压失败 ({type(e).__name__}: {e}); "
                            f"已提示解压目录 {extract_to}"
                        ),
                        data={
                            "password": password,
                            "tool": unar,
                            "extracted_to": str(extract_to),
                        },
                    )

                return ActionResult(
                    success=True,
                    message=(
                        f"FOUND password={password!r}; "
                        f"unzipped to {extract_to}"
                    ),
                    data={
                        "password": password,
                        "tool": unar,
                        "extracted_to": str(extract_to),
                    },
                )
            else:
                # unar 未装 → 提示用户
                return ActionResult(
                    success=True,  # 密码找到 = 主要工作完成
                    message=(
                        f"FOUND password={password!r}; "
                        f"但 unar/unrar 未装，请手动解压: "
                        f"unar -p {password!r} {rar_path.name} -o {extract_to}"
                    ),
                    data={
                        "password": password,
                        "tool": None,  # 没解压工具
                        "extracted_to": str(extract_to),
                        "manual_unzip_hint": f"unar -p {password!r} {rar_path.name} -o {extract_to}",
                    },
                )
        except (subprocess.TimeoutExpired, OSError) as e:
            return ActionResult(
                success=False,
                message=f"rar bruteforce failed: {type(e).__name__}: {e}",
            )


__all__ = ["BruteforceRarAction"]
