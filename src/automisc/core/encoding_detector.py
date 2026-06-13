"""编码检测器（v0.5-LSB-router）

LSB 抽出后判断"抽出的是 text / file / 编码特殊形态"——是路由决策的依据。

**决策树**：
```
text 内容 → 哪种严重度?
  含 secret/key/flag/ctf → severity=5 (Q1 敏感关键词) + 终止链
  base64 串 (长度 ≥ 16, 可解码) → severity=4
  binary 串 (0/1 字符, 长度 ≥ 32) → severity=4
  hex 串 (0-9a-f, 长度 ≥ 32) → severity=4
  普通文本 → severity=3 (Q1 兜底, 让用户看)
```

**边界**：
- 普通英文 / 中文 → 不认为是编码（severity=3）
- 短字符串 (< 8 chars) → 不判定 (避免误报)
"""
from __future__ import annotations

import base64
import re
import string
from typing import Final


# 敏感关键词 (Q1 + Owner 后补)
_SENSITIVE_KEYWORDS: Final[tuple[str, ...]] = (
    "key",
    "flag",
    "secret",
    "ctf",
    "password",
)

# base64 字符集
_BASE64_CHARS: Final[set[str]] = set(
    string.ascii_letters + string.digits + "+/="
)

# base64 候选 regex (核心字符 ≥ 12, 可选 = padding)
# base64 4 chars = 3 bytes, 12 chars = 9 bytes (最小有意义)
_BASE64_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9+/]{12,}={0,2}$"
)

# base32 候选 (核心字符 ≥ 12, base32 8 chars = 5 bytes, 12 chars ≈ 7.5 bytes)
_BASE32_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Z2-7]{12,}={0,6}$"
)

# hex 串 (长度 ≥ 32 = 16 bytes)
_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]{32,}$")

# binary 串 (仅 0/1, 长度 ≥ 32 = 4 bytes)
_BINARY_RE: Final[re.Pattern[str]] = re.compile(r"^[01]{32,}$")


def has_sensitive_keyword(text: str) -> bool:
    """是否含 secret/key/flag/ctf (Q1 高度敏感)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _SENSITIVE_KEYWORDS)


def is_base64(text: str) -> bool:
    """是否像 base64 (核心字符 ≥ 12 + 字符集匹配 + 可解码)."""
    if not _BASE64_RE.match(text):
        return False
    try:
        # 必须能解码 (允许 padding 错误 - 简单容错)
        base64.b64decode(text, validate=False)
        return True
    except Exception:
        return False


def is_base32(text: str) -> bool:
    """是否像 base32 (核心字符 ≥ 12 + 字符集匹配)."""
    return bool(_BASE32_RE.match(text))


def is_binary_string(text: str) -> bool:
    """是否像 binary 串 (0/1 chars, 长度 ≥ 32)."""
    return bool(_BINARY_RE.match(text))


def is_hex_string(text: str) -> bool:
    """是否像 hex 串 (0-9a-f, 长度 ≥ 32)."""
    return bool(_HEX_RE.match(text))


def score_text_severity(text: str) -> int:
    """Q1 主入口: 给 LSB 抽出的 text 打严重度.

    Returns:
        3 = 普通文本 (兜底)
        4 = 编码特殊形态 (base64/binary/hex)
        5 = 敏感关键词 (secret/key/flag/ctf)
    """
    if has_sensitive_keyword(text):
        return 5
    if is_base64(text) or is_base32(text):
        return 4
    if is_binary_string(text) or is_hex_string(text):
        return 4
    return 3


__all__ = [
    "has_sensitive_keyword",
    "is_base64",
    "is_base32",
    "is_binary_string",
    "is_hex_string",
    "score_text_severity",
]
