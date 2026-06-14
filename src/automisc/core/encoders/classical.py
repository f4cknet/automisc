"""古典密码编码器（per ``tools.md`` §3.8）

8 种古典密码：ROT13/47/18 + Caesar + Vigenère + Atbash + Pigpen + Keyboard Shift + Affine + Rail Fence

**v0.1 范围**：核心算法 + 单测覆盖
"""
from __future__ import annotations

from typing import Optional


# === ROT 系列 ===
def rot13(s: str) -> str:
    """ROT13 — 经典凯撒（a↔n, b↔o, ...）"""
    return s.translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
    ))


def rot_n(s: str, n: int) -> str:
    """通用 ROT-N"""
    n = n % 26
    return s.translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "".join([
            chr((ord(c) - ord("A") + n) % 26 + ord("A")) if c.isupper()
            else chr((ord(c) - ord("a") + n) % 26 + ord("a"))
            for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        ]),
    ))


# === ROT5（仅 digits 0-9）===
def rot5(s: str) -> str:
    """ROT5 — 数字旋转（0→5, 1→6, ..., 5→0, 6→1, ...）

    仅作用于 digits (0-9)，其他字符不变。
    """
    return s.translate(str.maketrans("0123456789", "5678901234"))


# === ROT47（ASCII 33-126 整段 94 字符旋转）===
def rot47(s: str) -> str:
    """ROT47 — ASCII 33-126 整段旋转 47 位（CTF 藏 base64 结果常用）。

    范围：! (33) 到 ~ (126)，共 94 个字符，每个字符位移 47。
    """
    result = []
    for c in s:
        o = ord(c)
        if 33 <= o <= 126:
            result.append(chr(33 + (o - 33 + 47) % 94))
        else:
            result.append(c)
    return "".join(result)


# === ROT18（ROT13 字母 + ROT5 数字）===
def rot18(s: str) -> str:
    """ROT18 — ROT13 + ROT5 组合（字母 ROT13，数字 ROT5，其他不变）。

    CTF 经典组合密码。
    """
    return rot5(rot13(s))


# === Caesar (同 ROT-N，但 N 可变) ===
def caesar_decrypt(s: str, shift: int) -> str:
    """Caesar 解密（shift = 加密时的位移）"""
    return rot_n(s, -shift)


def caesar_encrypt(s: str, shift: int) -> str:
    return rot_n(s, shift)


# === Vigenère ===
def vigenere_decrypt(s: str, key: str) -> str:
    """Vigenère 解密（key 重复使用）"""
    if not key:
        raise ValueError("Vigenère key cannot be empty")
    result = []
    key_idx = 0
    for c in s:
        if c.isalpha():
            shift = ord(key[key_idx % len(key)].upper()) - ord("A")
            if c.isupper():
                result.append(chr((ord(c) - ord("A") - shift) % 26 + ord("A")))
            else:
                result.append(chr((ord(c) - ord("a") - shift) % 26 + ord("a")))
            key_idx += 1
        else:
            result.append(c)
    return "".join(result)


def vigenere_encrypt(s: str, key: str) -> str:
    if not key:
        raise ValueError("Vigenère key cannot be empty")
    result = []
    key_idx = 0
    for c in s:
        if c.isalpha():
            shift = ord(key[key_idx % len(key)].upper()) - ord("A")
            if c.isupper():
                result.append(chr((ord(c) - ord("A") + shift) % 26 + ord("A")))
            else:
                result.append(chr((ord(c) - ord("a") + shift) % 26 + ord("a")))
            key_idx += 1
        else:
            result.append(c)
    return "".join(result)


# === Atbash (a↔z, b↔y, ...) ===
def atbash(s: str) -> str:
    """Atbash — 希伯来字母表镜像"""
    return s.translate(str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvutsrqponmlkjihgfedcba",
    ))


# === Affine (E(x) = (ax + b) mod 26) ===
def affine_decrypt(s: str, a: int, b: int) -> str:
    """Affine 解密（a 必须与 26 互质）"""
    from math import gcd
    if gcd(a, 26) != 1:
        raise ValueError(f"a={a} not coprime with 26")
    # 求 a 的模 26 逆元
    a_inv = pow(a, -1, 26)
    result = []
    for c in s:
        if c.isupper():
            x = ord(c) - ord("A")
            y = (a_inv * (x - b)) % 26
            result.append(chr(y + ord("A")))
        elif c.islower():
            x = ord(c) - ord("a")
            y = (a_inv * (x - b)) % 26
            result.append(chr(y + ord("a")))
        else:
            result.append(c)
    return "".join(result)


def affine_encrypt(s: str, a: int, b: int) -> str:
    return "".join(
        chr((a * (ord(c) - ord("A")) + b) % 26 + ord("A")) if c.isupper()
        else chr((a * (ord(c) - ord("a")) + b) % 26 + ord("a")) if c.islower()
        else c
        for c in s
    )


# === Pigpen Cipher (FreeMason / 简单网格) ===
_PIGPEN_MAP = {
    "a": "⠁", "b": "⠃", "c": "⠉", "d": "⠙", "e": "⠑",
    "f": "⠋", "g": "⠛", "h": "⠓", "i": "⠊", "j": "⠚",
    "k": "⠅", "l": "⠇", "m": "⠍", "n": "⠝", "o": "⠕",
    "p": "⠏", "q": "⠟", "r": "⠗", "s": "⠎", "t": "⠞",
    "u": "⠥", "v": "⠧", "w": "⠺", "x": "⠭", "y": "⠽", "z": "⠵",
}


def pigpen_decrypt(s: str) -> str:
    """Pigpen 视觉密码 → 字母"""
    # 反向查表
    inv = {v: k for k, v in _PIGPEN_MAP.items()}
    return "".join(inv.get(c, c) for c in s)


def pigpen_encrypt(s: str) -> str:
    return "".join(_PIGPEN_MAP.get(c.lower(), c) for c in s)


# === Rail Fence (栅栏密码) ===
def rail_fence_decrypt(s: str, num_rails: int) -> str:
    """栅栏密码解密"""
    if num_rails < 2:
        raise ValueError("num_rails must be >= 2")
    n = len(s)
    # 计算每行字符数
    cycle = 2 * (num_rails - 1)
    if cycle == 0:
        return s
    rail_lengths = [0] * num_rails
    for i in range(n):
        pos = i % cycle
        rail = pos if pos < num_rails else cycle - pos
        rail_lengths[rail] += 1
    # 拆分
    rails = []
    idx = 0
    for length in rail_lengths:
        rails.append(s[idx:idx + length])
        idx += length
    # 重排
    result = []
    rail_idx = [0] * num_rails
    for i in range(n):
        pos = i % cycle
        rail = pos if pos < num_rails else cycle - pos
        result.append(rails[rail][rail_idx[rail]])
        rail_idx[rail] += 1
    return "".join(result)


def rail_fence_encrypt(s: str, num_rails: int) -> str:
    if num_rails < 2:
        raise ValueError("num_rails must be >= 2")
    cycle = 2 * (num_rails - 1)
    if cycle == 0:
        return s
    rails = [[] for _ in range(num_rails)]
    for i, c in enumerate(s):
        pos = i % cycle
        rail = pos if pos < num_rails else cycle - pos
        rails[rail].append(c)
    return "".join("".join(r) for r in rails)


# === auto_try: 自动尝试多种古典密码 ===
def auto_try_caesar(s: str) -> Optional[tuple[int, str]]:
    """自动尝试 26 种 Caesar shift，返回 (shift, decoded) 第一个看起来像英文的。

    启发：解码后含常见英文单词。
    """
    common_words = {"the", "be", "to", "of", "and", "in", "that", "have", "it", "for", "not", "on", "with", "he"}
    for shift in range(1, 26):
        decoded = caesar_decrypt(s, shift)
        words = set(decoded.lower().split())
        if words & common_words:
            return (shift, decoded)
    return None
