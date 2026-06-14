"""Base64 隐写解码器（per ``upgrade/v0.5-base-rot-decoders.md`` PR2）

**原理**：
- 标准 base64：每 3 字节 → 4 字符（每字符 6 bit，共 24 bit = 3 字节）
- 但**末位冗余**：当原始数据 N 字节是 3 倍数时，每字符末 2 bit 都可"隐藏" 2 bit 数据
- 4 个 2-bit → 1 byte → 4 个 base64 字符能藏 1 byte 隐藏数据
- **隐藏容量** = base64 字符数 × 2 / 8 = 字符数 / 4 bytes

**简化假设**：base64 输入对应 3 倍数字节的原始数据（每字符末 2 bit 全部是冗余的）。
对**非 3 倍数**的输入，末尾 1/2 个字符的"末 2 bit"是真实数据位 + 冗余位混合，
本模块**统一按"末 2 bit 全冗余"** 处理（即提取后可能含垃圾位，调用方按需截断）。

**算法伪代码**：
```
decode_base64_stego(s):
    stripped = s.rstrip('=')  # 去掉末尾 = 填充
    bits = []
    for ch in stripped:
        idx = B64_TABLE.index(ch)
        bits.append(idx & 0b11)  # 取末 2 bit
    hidden = bytearray()
    for i in range(0, len(bits) - 3, 4):
        byte = (bits[i] << 6) | (bits[i+1] << 4) | (bits[i+2] << 2) | bits[i+3]
        hidden.append(byte)
    return bytes(hidden)
```

**用法**：
```python
from automisc.core.encoders.base64_stego import decode_base64_stego
hidden_bytes = decode_base64_stego("ZVKg...")
# hidden_bytes 含原始 base64 数据 + 隐藏 bits 提取出的字节
```
"""
from __future__ import annotations

from typing import Optional


# 标准 base64 字符表（用于索引）
_B64_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

# 反向表: char -> 6-bit index (预计算加速)
_B64_INDEX = {c: i for i, c in enumerate(_B64_TABLE)}


def decode_base64_stego(s: str) -> bytes:
    """从 base64 字符串提取隐藏数据（每字符末 2 bit）。

    **简化算法**（per CTF 常见实现）：每字符末 2 bit 都视为可隐藏位 → 4 字符 → 1 byte。
    警告：此算法假设 base64 字符串对应的原文**不**是 3 倍数字节（否则前 N-2 字符末 2 bit 是真实数据位）。

    Args:
        s: 含隐写的 base64 字符串（可含 `=` 填充）

    Returns:
        解出的隐藏 bytes（末尾可能有垃圾位，调用方截断）

    Raises:
        ValueError: 字符串含非 base64 字符（除 `=`）
    """
    if not s:
        return b""

    stripped = s.rstrip("=")
    if not stripped:
        return b""

    bits = []
    for ch in stripped:
        if ch not in _B64_INDEX:
            raise ValueError(f"base64_stego invalid char: {ch!r}")
        idx = _B64_INDEX[ch]
        bits.append(idx & 0b11)  # 末 2 bit (位 0-1)

    hidden = bytearray()
    # 4 个 2-bit 拼成 1 byte
    for i in range(0, len(bits) - 3, 4):
        byte = (bits[i] << 6) | (bits[i+1] << 4) | (bits[i+2] << 2) | bits[i+3]
        hidden.append(byte)
    return bytes(hidden)


def encode_base64_stego(plaintext_b64: str, hidden: bytes) -> str:
    """往 base64 字符串里塞隐藏数据（每字符末 2 bit）。

    **简化算法**（per CTF 常见实现）：每字符末 2 bit 都被覆盖。
    ⚠️ 这会破坏原 base64 解码 — 仅适用于**非 3 倍数字节**原文（前 N-1 个 group 末 2 bit 是真实数据）。
    实际 CTF 题目请用 22/23/25/26 bytes 原文（让末尾 group 提供冗余位）。

    Args:
        plaintext_b64: 标准 base64 编码的字符串
        hidden: 要隐藏的 bytes

    Returns:
        含隐写的 base64 字符串

    Raises:
        ValueError: 隐藏数据超出 plaintext_b64 的隐写容量
    """
    if not plaintext_b64:
        return plaintext_b64

    # 容量 = len(stripped) * 2 / 8 = len(stripped) // 4 bytes
    stripped_len = len(plaintext_b64.rstrip("="))
    capacity = stripped_len // 4
    if len(hidden) > capacity:
        raise ValueError(
            f"hidden data too long: {len(hidden)} bytes > capacity {capacity} bytes "
            f"({stripped_len} base64 chars)"
        )

    # 把 hidden 转成 bit 列表（每字节 8 bit，每 4 字符 1 byte）
    bit_list = []
    for byte in hidden:
        for shift in (6, 4, 2, 0):
            bit_list.append((byte >> shift) & 0b11)

    # 把 bit 列表塞进 plaintext_b64 每字符末 2 bit
    out = []
    bit_idx = 0
    for ch in plaintext_b64:
        if ch == "=":
            out.append(ch)
            continue
        idx = _B64_INDEX.get(ch)
        if idx is None:
            raise ValueError(f"base64_stego invalid char: {ch!r}")
        # 保留前 4 bit，末 2 bit 用 bit_list 替换
        if bit_idx < len(bit_list):
            new_idx = (idx & 0b111100) | bit_list[bit_idx]
            out.append(_B64_TABLE[new_idx])
            bit_idx += 1
        else:
            out.append(ch)

    return "".join(out)


def detect_capacity(b64_string: str) -> int:
    """计算 base64 字符串的隐写容量（bytes，简化算法）。

    ⚠️ 简化算法的容量是"理论上每字符末 2 bit 都能藏"，实际有效容量
    只来自末尾不完整 group。CTF 实际题目请用原文**非 3 倍数字节**
    来获得足够冗余位。

    Args:
        b64_string: 标准 base64 字符串

    Returns:
        理论可隐藏字节数 = len(stripped) // 4
    """
    stripped_len = len(b64_string.rstrip("="))
    return stripped_len // 4


def extract_hidden_with_size_hint(b64_string: str, hint_bytes: Optional[int] = None) -> bytes:
    """提取隐藏数据，可指定期望长度（截断到 hint_bytes）。

    Args:
        b64_string: 含隐写的 base64 字符串
        hint_bytes: 期望的隐藏数据长度（None = 全提取）

    Returns:
        隐藏 bytes（截断到 hint_bytes）
    """
    hidden = decode_base64_stego(b64_string)
    if hint_bytes is not None and hint_bytes < len(hidden):
        return hidden[:hint_bytes]
    return hidden
