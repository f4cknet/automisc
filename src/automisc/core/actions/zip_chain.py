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


def _classify_zip_entries(zip_path: Path) -> dict:
    """逐 entry 分类 (per ctf-wiki 原理 + v0.5-train-005 反馈).

    算法 (per ctf-wiki 伪加密原理 https://ctf-wiki.org/misc/archive/zip/):
    1) 收 LFH map (fname → (lfh_offset, lfh_flag, comp_size, data_start))
    2) 收 CDH map (fname → (cdh_offset, cdh_flag)) — 用 EOCD 倒推外层 CDH 区域 (per v0.5-train-004)
    3) 逐 entry 判断 (per-entry, 不 short-circuit):
       - LFH bit0=0 AND CDH bit0=0 → clear (完全明文, 不需要修)
       - LFH bit0=1 OR CDH bit0=1:
         - comp_size < 12 → pseudo (太短不可能有真加密 PKCS#5 header)
         - data[data_start + 11] in range(12) → real (有 PKCS#5 末位, 修不了)
         - else → pseudo (无 PKCS#5 末位)
    4) 不 short-circuit — 扫完所有 entry (per AGENTS §5.5「可疑点越多越好」)

    Returns:
        {
            "pseudo": {fname: (lfh_offset, cdh_offset)},   # 伪加密 (per-owner 决策 A: 只清这些)
            "real":   {fname: (lfh_offset, cdh_offset)},   # 真加密 (per-owner 决策 A: 不修)
            "clear":  {fname: (lfh_offset, cdh_offset)},   # 完全明文 (不需要修)
        }
        lfh_offset / cdh_offset = -1 表示该 entry 在 LFH/CDH map 中没找到 (理论上不应发生)

    Raises:
        FileNotFoundError: zip_path 不存在
    """
    try:
        with open(zip_path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise FileNotFoundError(f"cannot read zip: {zip_path} ({e})")

    # 1) 收所有 LFH: fname → (lfh_offset, lfh_flag, comp_size, data_start)
    lfh_map: dict = {}  # fname → (lfh_offset, lfh_flag, comp_size, data_start)
    i = 0
    while i < len(data) - 4:
        if data[i : i + 4] == b"PK\x03\x04":  # Local File Header
            fname_len = struct.unpack("<H", data[i + 26 : i + 28])[0]
            extra_len = struct.unpack("<H", data[i + 28 : i + 30])[0]
            comp_size = struct.unpack("<I", data[i + 18 : i + 22])[0]
            lfh_flag = struct.unpack("<H", data[i + 6 : i + 8])[0]
            fname = data[i + 30 : i + 30 + fname_len].decode("utf-8", errors="replace")
            data_start = i + 30 + fname_len + extra_len
            lfh_map[fname] = (i, lfh_flag, comp_size, data_start)
            i = data_start + comp_size
        else:
            i += 1

    # 2) 收外层 CDH (用 EOCD 倒推, 避免误收嵌套 CDH per v0.5-train-004)
    #    fname → (cdh_offset, cdh_flag)
    cdh_map: dict = {}
    eocd_offset = -1
    j = len(data) - 22  # EOCD 最小 22 bytes
    while j >= 0:
        if data[j : j + 4] == b"PK\x05\x06":
            eocd_offset = j
            break
        j -= 1
    if eocd_offset >= 0:
        cdh_count = struct.unpack("<H", data[eocd_offset + 10 : eocd_offset + 12])[0]
        cdh_size = struct.unpack("<I", data[eocd_offset + 12 : eocd_offset + 16])[0]
        cdh_start = struct.unpack("<I", data[eocd_offset + 16 : eocd_offset + 20])[0]
        cdh_end = cdh_start + cdh_size
        k = cdh_start
        while k < cdh_end - 46:
            if data[k : k + 4] == b"PK\x01\x02":
                fnl = struct.unpack("<H", data[k + 28 : k + 30])[0]
                exl = struct.unpack("<H", data[k + 30 : k + 32])[0]
                cmt = struct.unpack("<H", data[k + 32 : k + 34])[0]
                cdh_flag = struct.unpack("<H", data[k + 8 : k + 10])[0]
                cdh_fname = data[k + 46 : k + 46 + fnl].decode("utf-8", errors="replace")
                cdh_map[cdh_fname] = (k, cdh_flag)
                k = k + 46 + fnl + exl + cmt
            else:
                k += 1

    # 3) 逐 entry 分类 (per ctf-wiki 原理 + owner 决策 A)
    pseudo: dict = {}
    real: dict = {}
    clear: dict = {}

    for fname, (lfh_offset, lfh_flag, comp_size, data_start) in lfh_map.items():
        cdh_offset, cdh_flag = cdh_map.get(fname, (-1, 0))
        has_encryption_bit = bool((lfh_flag & 0x1) or (cdh_flag & 0x1))

        if not has_encryption_bit:
            # LFH 和 CDH bit0 都 0 → 完全明文
            clear[fname] = (lfh_offset, cdh_offset)
            continue

        # comp_size < 12: 太短不可能有真加密 PKCS#5 header (zip 加密 header 是 12 字节)
        if comp_size < 12:
            pseudo[fname] = (lfh_offset, cdh_offset)
            continue

        # 看 data 起始 12 字节末位 (PKCS#5 末字节) 是否在 0-11
        last_byte = data[data_start + 11]
        if last_byte in range(12):
            # 有 PKCS#5 header → 真加密 (修了也白修, data 仍加密)
            real[fname] = (lfh_offset, cdh_offset)
        else:
            # 无 PKCS#5 header → 伪加密
            pseudo[fname] = (lfh_offset, cdh_offset)

    return {"pseudo": pseudo, "real": real, "clear": clear}


def _is_pseudo_encrypted(zip_path: Path) -> bool:
    """检测 zip 是否含伪加密 entry (向后兼容 bool 返回).

    升级 (per v0.5-train-005): 内部用 _classify_zip_entries per-entry 分类,
    返回 len(classify['pseudo']) > 0. 保持 bool 返回, 现有调用方不需改.

    覆盖 3 形态 (per v0.5-train-004):
    - A: LFH=1, CDH=0 (仅 LFH 假加密)
    - B: LFH=0, CDH=1 (仅 CDH 假加密) ← zipfile 读 CDH 判定
    - C: LFH=1, CDH=1 (双假加密)
    """
    try:
        classify = _classify_zip_entries(zip_path)
    except (FileNotFoundError, OSError):
        return False
    return len(classify["pseudo"]) > 0


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
                    # 加密 → 失败
                    # v0.5-journal-highlight-keywords (per Owner 2026-06-16):
                    # 区分真加密 vs 伪加密:
                    # - 伪加密 (flag bit 0 = 1 但内容明文) → 不设 encrypted, 让 fix_pseudo 修
                    # - 真加密 → 设 encrypted=True, chain 立刻停
                    is_pseudo = _is_pseudo_encrypted(zip_path)
                    return ActionResult(
                        success=False,
                        message=f"zip is {'pseudo-' if is_pseudo else ''}encrypted: {e}",
                        data={
                            "extracted_to": str(extract_to),
                            "encrypted": not is_pseudo,  # 仅真加密 → chain 立刻停
                            "is_pseudo_encrypted": is_pseudo,  # 显式标志
                            "stop_reason": "真加密 zip, 需密码 (chain 立刻停)" if not is_pseudo
                                          else "伪加密 zip, 需 fix_pseudo",
                        },
                    )
        except zipfile.BadZipFile as e:
            return ActionResult(success=False, message=f"bad zip: {e}")


class FixPseudoEncryptionAction(Action):
    """修 zip 伪加密 (per-entry 修, 只清伪加密 entry 的加密位) 然后重试解压.

    伪加密原理 (per ctf-wiki https://ctf-wiki.org/misc/archive/zip/):
    - 真 zip 加密: entry flag_bits bit 0 = 1, 且内容 AES/RC4 加密 (有 PKCS#5 12 字节 header)
    - 伪加密: entry flag_bits bit 0 = 1, 但内容明文 (无 PKCS#5 header)
    - 修复: 把伪加密 entry 的 flag_bits bit 0 改成 0

    per-entry 分类 (per v0.5-zip-pseudo-per-entry-classify + owner 决策 A+A):
    - 伪加密 entry → 修 (清 LFH + 对应 CDH bit 0)
    - 真加密 entry → 不修 (owner 决策 A: 不修真加密位, 修不破坏原则)
    - 完全明文 entry → 不修 (本来就没加密位)
    - 不 short-circuit (per AGENTS §5.5「可疑点越多越好」)
    """

    name = "fix_pseudo_encryption"

    def run(self, context: dict[str, Any]) -> ActionResult:
        zip_path = Path(context.get("file_path", ""))
        if not zip_path.exists():
            return ActionResult(success=False, message=f"file not found: {zip_path}")

        # 1) per-entry 分类 (per v0.5-zip-pseudo-per-entry-classify)
        try:
            classify = _classify_zip_entries(zip_path)
        except (FileNotFoundError, OSError) as e:
            return ActionResult(success=False, message=f"cannot read zip: {e}")

        pseudo_entries = classify["pseudo"]
        real_entries = classify["real"]
        clear_entries = classify["clear"]

        if not pseudo_entries:
            return ActionResult(
                success=False,
                message=(
                    f"no pseudo-encrypted entry found "
                    f"(real={len(real_entries)}, clear={len(clear_entries)})"
                ),
                data={
                    "real_entries": list(real_entries.keys()),
                    "clear_entries": list(clear_entries.keys()),
                },
            )

        # 2) 修: 只清伪加密 entry 的 LFH + 对应 CDH bit 0 (per-owner 决策 A+A)
        #    用 _classify_zip_entries 拿到的 (lfh_offset, cdh_offset) 直接操作, 不搜索 magic
        try:
            with open(zip_path, "rb") as f:
                data = f.read()
            fixed = bytearray(data)
        except OSError as e:
            return ActionResult(success=False, message=f"cannot read zip: {e}")

        fixed_count = 0
        for fname, (lfh_offset, cdh_offset) in pseudo_entries.items():
            # 清 LFH flag bit 0 (offset 6, 2 bytes)
            if lfh_offset >= 0:
                flag = fixed[lfh_offset + 6] | (fixed[lfh_offset + 7] << 8)
                if flag & 0x1:
                    fixed[lfh_offset + 6] = fixed[lfh_offset + 6] & 0xFE
                    fixed_count += 1
            # 清 CDH flag bit 0 (offset 8, 2 bytes)
            if cdh_offset >= 0:
                flag = fixed[cdh_offset + 8] | (fixed[cdh_offset + 9] << 8)
                if flag & 0x1:
                    fixed[cdh_offset + 8] = fixed[cdh_offset + 8] & 0xFE
                    fixed_count += 1

        if fixed_count == 0:
            return ActionResult(
                success=False,
                message="no encrypted flag bits found to fix (unexpected after classify)",
            )

        # 写回（覆盖原文件，备份在 .bak）
        backup = zip_path.with_suffix(zip_path.suffix + ".bak")
        shutil.copy2(zip_path, backup)
        with open(zip_path, "wb") as f:
            f.write(fixed)

        # 3) 验证 - 一个一个 entry 解, 坏 entry 跳过不阻塞 (per v0.5-zip-pseudo-cdh-detect)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                extract_to = zip_path.parent / f"{zip_path.stem}_unzipped"
                extract_to.mkdir(exist_ok=True)
                extracted = []
                bad_entries = []
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    try:
                        zf.extract(info, path=extract_to)
                        extracted.append(info.filename)
                    except (RuntimeError, zipfile.BadZipFile, Exception) as e:  # noqa: BLE001
                        # 坏 entry (CRC/格式错/真加密) → 跳过, 记录
                        bad_entries.append((info.filename, str(e)))
                if extracted:
                    return ActionResult(
                        success=True,
                        message=(
                            f"fixed {fixed_count} flag_bits on {len(pseudo_entries)} pseudo entry; "
                            f"unzipped {len(extracted)}/{len(zf.namelist())} entries "
                            f"to {extract_to}; "
                            f"{len(real_entries)} real entry kept (need password); "
                            f"{len(bad_entries)} bad entry skipped; "
                            f"backup at {backup}"
                        ),
                        data={
                            "extracted_to": str(extract_to),
                            "fixed_count": fixed_count,
                            "extracted_count": len(extracted),
                            "pseudo_entries": list(pseudo_entries.keys()),
                            "real_entries": list(real_entries.keys()),
                            "clear_entries": list(clear_entries.keys()),
                            "bad_entries": bad_entries,
                            "backup": str(backup),
                        },
                    )
                # 0 entry extracted → 还原 + fail
                shutil.copy2(backup, zip_path)
                return ActionResult(
                    success=False,
                    message=(
                        f"fixed {fixed_count} flag_bits but 0 entries extracted "
                        f"({len(bad_entries)} bad entry); restored from backup"
                    ),
                    data={
                        "fixed_count": fixed_count,
                        "bad_entries": bad_entries,
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
