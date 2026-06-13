"""Action: ZIP 智能分析链.

逻辑:
1. TryUnzipAction: 直接 unzip（无密码）
2. FixPseudoEncryptionAction: 检测伪加密（高位标志位）并修复
3. BruteforceZipAction: 4-6 位字典爆破（数字 / 字母 / 混合）

DAG 转移:
  TryUnzip.success → 终止
  TryUnzip.failure → FixPseudoEncryption
  FixPseudoEncryption.success → 重试 TryUnzip
  FixPseudoEncryption.failure → Bruteforce
  Bruteforce.success/failure → 终止
"""
from __future__ import annotations

import itertools
import os
import shutil
import string
import struct
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult


def _is_pseudo_encrypted(zip_path: Path) -> bool:
    """检测 zip 是否伪加密（flag bit 0 = 1 但内容无真加密 header）.

    实现：直接读 raw bytes，检查每个 LFH entry:
    - 加密位 set (flag & 0x1)
    - 但 entry data 不含传统加密的 12 字节 PKCS#5 header
      (末字节不在 0-11 范围) → 伪加密
    """
    try:
        with open(zip_path, "rb") as f:
            data = f.read()
    except OSError:
        return False

    i = 0
    while i < len(data) - 4:
        if data[i : i + 4] == b"PK\x03\x04":  # Local File Header
            flag = struct.unpack("<H", data[i + 6 : i + 8])[0]
            if not (flag & 0x1):
                return False  # 无加密位
            comp_size = struct.unpack("<I", data[i + 18 : i + 22])[0]
            fname_len = struct.unpack("<H", data[i + 26 : i + 28])[0]
            extra_len = struct.unpack("<H", data[i + 28 : i + 30])[0]
            data_start = i + 30 + fname_len + extra_len
            if comp_size < 12:
                return True  # 太短不可能有真加密 header
            last_byte = data[data_start + 11]
            if last_byte in range(12):
                return False  # 真加密
            return True  # 伪加密（加密位 set 但无真加密 header）
        i += 1
    return False


class TryUnzipAction(Action):
    """直接 unzip 看是否能解压（无密码或已知密码）.

    输入 context: file_path (zip)
    输出 context: extracted_to (解压目录，success 时)
    """

    name = "try_unzip"

    def run(self, context: dict[str, Any]) -> ActionResult:
        zip_path = Path(context.get("file_path", ""))
        if not zip_path.exists():
            return ActionResult(success=False, message=f"file not found: {zip_path}")

        if not zipfile.is_zipfile(zip_path):
            return ActionResult(success=False, message=f"not a valid zip: {zip_path}")

        extract_to = zip_path.parent / f"{zip_path.stem}_unzipped"
        extract_to.mkdir(exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                # 试 no password
                try:
                    zf.extractall(path=extract_to)
                    return ActionResult(
                        success=True,
                        message=f"unzipped to {extract_to} (no password)",
                        data={
                            "extracted_to": str(extract_to),
                            "extracted_count": len(zf.namelist()),
                        },
                    )
                except RuntimeError as e:
                    # 加密 → 失败 (try pseudo fix)
                    return ActionResult(
                        success=False,
                        message=f"zip is encrypted: {e}",
                        data={"extracted_to": str(extract_to)},
                    )
        except zipfile.BadZipFile as e:
            return ActionResult(success=False, message=f"bad zip: {e}")


class FixPseudoEncryptionAction(Action):
    """修 zip 伪加密（清 encryption flag bit）然后重试解压.

    伪加密原理：
    - 真 zip 加密：entry flag_bits bit 0 = 1，且内容 AES/RC4 加密
    - 伪加密：entry flag_bits bit 0 = 1，但内容明文
    - 修复：把 flag_bits bit 0 改成 0
    """

    name = "fix_pseudo_encryption"

    def run(self, context: dict[str, Any]) -> ActionResult:
        zip_path = Path(context.get("file_path", ""))
        if not zip_path.exists():
            return ActionResult(success=False, message=f"file not found: {zip_path}")

        # 先检测是否伪加密
        if not _is_pseudo_encrypted(zip_path):
            return ActionResult(
                success=False,
                message="not pseudo-encrypted (real encryption or no encryption)",
            )

        # 修：把 local file header + central directory 的 flag_bits bit 0 清掉
        # zip 格式：每个 entry 有 local file header (LFH) + central directory entry (CDH)
        # 两者都含 general purpose bit flag (offset 6, 2 bytes); bit 0 = encryption
        try:
            with open(zip_path, "rb") as f:
                data = f.read()

            fixed = bytearray(data)
            fixed_count = 0
            i = 0
            while i < len(fixed) - 4:
                # LFH 签名 PK\x03\x04
                if fixed[i : i + 4] == b"PK\x03\x04":
                    # flag_bits 在 offset 6, 2 bytes
                    flag = fixed[i + 6] | (fixed[i + 7] << 8)
                    if flag & 0x1:
                        # 清除 bit 0
                        fixed[i + 6] = fixed[i + 6] & 0xFE
                        fixed_count += 1
                # CDH 签名 PK\x01\x02
                elif fixed[i : i + 4] == b"PK\x01\x02":
                    flag = fixed[i + 8] | (fixed[i + 9] << 8)
                    if flag & 0x1:
                        fixed[i + 8] = fixed[i + 8] & 0xFE
                        fixed_count += 1
                i += 1

            if fixed_count == 0:
                return ActionResult(
                    success=False,
                    message="no encrypted flag bits found to fix",
                )

            # 写回（覆盖原文件，备份在 .bak）
            backup = zip_path.with_suffix(zip_path.suffix + ".bak")
            shutil.copy2(zip_path, backup)
            with open(zip_path, "wb") as f:
                f.write(fixed)

            # 验证
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    extract_to = zip_path.parent / f"{zip_path.stem}_unzipped"
                    extract_to.mkdir(exist_ok=True)
                    zf.extractall(path=extract_to)
                    return ActionResult(
                        success=True,
                        message=(
                            f"fixed {fixed_count} flag_bits; "
                            f"unzipped to {extract_to}; backup at {backup}"
                        ),
                        data={
                            "extracted_to": str(extract_to),
                            "fixed_count": fixed_count,
                            "backup": str(backup),
                        },
                    )
            except Exception as e:  # noqa: BLE001
                # 修复失败还原
                shutil.copy2(backup, zip_path)
                return ActionResult(
                    success=False,
                    message=f"fix failed, restored from backup: {e}",
                )
        except Exception as e:  # noqa: BLE001
            return ActionResult(success=False, message=f"fix_pseudo_encryption error: {e}")


def _generate_passwords(min_len: int = 4, max_len: int = 6) -> list[str]:
    """生成 4-6 位密码字典.

    v0.1 简化策略（避免 20 亿组合卡死）:
    - 数字 4-6 位: 10^4 + 10^5 + 10^6 = 1,111,000
    - 字母 4 位: 52^4 = 7,311,616
    - 字母 5 位: 52^5 = 380,204,032 （v0.1 跳过太大）
    - 字母+数字 4-6 位: 同上 v0.1 跳过

    实际 v0.1 字典: ~8.4M (10^4 + 10^5 + 10^6 + 52^4)
    v0.5+ 优化: 改用 john zip2john + 内存 wordlist 调度
    """
    digits = string.digits
    letters = string.ascii_letters
    alnum = digits + letters

    passwords: list[str] = []

    # 数字 4-6 位 (必含)
    for length in range(min_len, max_len + 1):
        for combo in itertools.product(digits, repeat=length):
            passwords.append("".join(combo))

    # 字母 4 位 (52^4 ≈ 7M 可接受)
    for combo in itertools.product(letters, repeat=min_len):
        passwords.append("".join(combo))

    # 字母+数字 4 位 (62^4 ≈ 14.7M 太大，v0.1 跳过)
    # 字母 5/6 位 / 字母+数字 5/6 位 -> v0.5+ 走 john 字典爆破
    # 但 context['__bruteforce_limit__'] 限制时仍生成
    if int(os.environ.get("AUTOMISC_BRUTEFORCE_FULL", "0")):
        for length in range(min_len + 1, max_len + 1):
            for combo in itertools.product(letters, repeat=length):
                passwords.append("".join(combo))
        for length in range(min_len, max_len + 1):
            for combo in itertools.product(alnum, repeat=length):
                passwords.append("".join(combo))

    return passwords


class BruteforceZipAction(Action):
    """4-6 位数字/字母/混合字典爆破 zip 密码.

    v0.1 简化：纯 Python zipfile 试密码 (无 john 调用).
    v0.5+ 优化：调 john zip2john + john --wordlist (快 10x+).
    """

    name = "bruteforce_zip"

    def run(self, context: dict[str, Any]) -> ActionResult:
        zip_path = Path(context.get("file_path", ""))
        if not zip_path.exists():
            return ActionResult(success=False, message=f"file not found: {zip_path}")

        # 先生成字典
        passwords = _generate_passwords(min_len=4, max_len=6)
        if context.get("__bruteforce_limit__"):
            passwords = passwords[: int(context["__bruteforce_limit__"])]

        # 第一个 entry 试
        try:
            with zipfile.ZipFile(zip_path) as zf:
                # 找第一个加密的 entry
                target_entry = None
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        target_entry = info
                        break
                if not target_entry:
                    return ActionResult(
                        success=False,
                        message="no encrypted entry found (not really encrypted?)",
                    )

                extract_to = zip_path.parent / f"{zip_path.stem}_bruteforced"
                extract_to.mkdir(exist_ok=True)

                tried = 0
                for pwd in passwords:
                    tried += 1
                    try:
                        data = zf.read(target_entry.filename, pwd=pwd.encode("utf-8"))
                        # 成功！解压整个
                        zf.extractall(path=extract_to, pwd=pwd.encode("utf-8"))
                        return ActionResult(
                            success=True,
                            message=(
                                f"FOUND password={pwd!r} (tried {tried}/{len(passwords)}); "
                                f"unzipped to {extract_to}"
                            ),
                            data={
                                "password": pwd,
                                "tried": tried,
                                "total": len(passwords),
                                "extracted_to": str(extract_to),
                            },
                        )
                    except (RuntimeError, zipfile.BadZipFile):
                        continue
                    except Exception:  # noqa: BLE001
                        continue

                return ActionResult(
                    success=False,
                    message=f"bruteforce failed: tried {tried} passwords, no match",
                    data={"tried": tried, "total": len(passwords)},
                )
        except zipfile.BadZipFile as e:
            return ActionResult(success=False, message=f"bad zip: {e}")


__all__ = [
    "TryUnzipAction",
    "FixPseudoEncryptionAction",
    "BruteforceZipAction",
    "_is_pseudo_encrypted",
    "_generate_passwords",
]
