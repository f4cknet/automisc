"""Base64 自定义表编码器（per ``upgrade/v0.5-base-rot-decoders.md``）

CTF 经常用打乱的 base64 表（替换字母顺序），用户需提供 64 字符自定义表。

**核心 API**：
- ``decode_base64_custom(s, custom_table) -> bytes``
- ``encode_base64_custom(data, custom_table) -> str``
- ``detect_custom_table_shift(s, ref_plaintext) -> Optional[int]``
    已知一段密文 + 部分明文 → 自动尝试右移 N 位找表

**示例**：
```python
# 标准 base64 表右移 13 位（CTF 常见变体）
custom = "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm0123456789+/"
plain = decode_base64_custom(cipher, custom)
```
"""
from __future__ import annotations

import base64
import string
from typing import Optional


# 标准 base64 表（64 chars）
_STD_BASE64_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


# base64 URL-safe 表（64 chars，`-` 和 `_` 替代 `+` 和 `/`）
URL_SAFE_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def encode_base64_custom(data: bytes, custom_table: str) -> str:
    """用自定义表编码 bytes。

    Args:
        data: 原始 bytes
        custom_table: 64 字符表（不能含 `=`，填充用标准 `=` 输出）

    Returns:
        用 custom_table 编码的字符串
    """
    if len(custom_table) != 64:
        raise ValueError(f"custom_table length must be 64, got {len(custom_table)}")
    # 标准 base64 → 用 custom_table 替换字符
    std_encoded = base64.b64encode(data).decode("ascii")
    trans = str.maketrans(_STD_BASE64_TABLE, custom_table)
    return std_encoded.translate(trans)


def decode_base64_custom(s: str, custom_table: str) -> bytes:
    """用自定义表解码字符串。

    Args:
        s: 用 custom_table 编码的字符串（可含 `=` 填充）
        custom_table: 64 字符表

    Returns:
        解码的 bytes

    Raises:
        ValueError: custom_table 长度错误或解码失败
    """
    if len(custom_table) != 64:
        raise ValueError(f"custom_table length must be 64, got {len(custom_table)}")
    # 反向翻译: custom_table → std_table
    trans = str.maketrans(custom_table, _STD_BASE64_TABLE)
    std = s.translate(trans)
    try:
        return base64.b64decode(std, validate=False)
    except (ValueError, base64.binascii.Error) as e:
        raise ValueError(f"base64_custom decode failed: {e}") from e


def detect_custom_table_shift(
    ciphertext: str,
    known_plaintext_b64: str,
    max_shift: int = 64,
) -> Optional[int]:
    """已知"密文 + 明文的标准 base64" → 检测自定义表是右移 N 位。

    CTF 经典变体：把标准 base64 表右移（或左移）N 位。

    Args:
        ciphertext: 用变体表编码的密文
        known_plaintext_b64: 同一明文的标准 base64（用户已知部分明文）
        max_shift: 最大尝试位移 (默认 64，覆盖全表）

    Returns:
        找到的位移 N（ciphertext = plaintext 右移 N 位表），或 None
    """
    if len(ciphertext) < len(known_plaintext_b64):
        # 取较短的前缀
        n = min(len(ciphertext), len(known_plaintext_b64))
        ciphertext = ciphertext[:n]
        known_plaintext_b64 = known_plaintext_b64[:n]

    # 假设密文 = 标准 base64 表右移 N 位后编码（即 cipher_char = std[(plain_idx + N) % 64]）
    # 则 cipher_idx = (plain_idx + N) % 64
    # 所以 N = (cipher_idx - plain_idx) % 64
    candidates = []
    for i in range(min(len(ciphertext), len(known_plaintext_b64))):
        if ciphertext[i] == "=" or known_plaintext_b64[i] == "=":
            continue  # 跳过填充
        if ciphertext[i] not in _STD_BASE64_TABLE or known_plaintext_b64[i] not in _STD_BASE64_TABLE:
            return None  # 不是简单位移变体
        plain_idx = _STD_BASE64_TABLE.index(known_plaintext_b64[i])
        cipher_idx = _STD_BASE64_TABLE.index(ciphertext[i])
        n = (cipher_idx - plain_idx) % 64
        candidates.append(n)

    if not candidates:
        return None
    # 取众数（所有位置应该一致）
    from collections import Counter
    counter = Counter(candidates)
    return counter.most_common(1)[0][0]
