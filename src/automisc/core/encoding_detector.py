"""编码检测器（v0.5-LSB-router, v0.5+ 重构为薄包装）

LSB 抽出后判断"抽出的是 text / file / 编码特殊形态"——是路由决策的依据。

**v0.5+ 重构**（per Owner 2026-06-14）：
- 实现已迁到 `core.utils.rule_scanner`（更通用, 整段 + 逐行扫, 返回 span）
- 本文件保留 LSB-router 专用的 2 入口 (`score_text_severity` + 兼容的 is_* 包装)
- 旧 import 路径 (lsb_extract) 保持兼容

**决策树** (per Q1)：
```
text 内容 → 哪种严重度?
  含 secret/key/flag/ctf/password → severity=5 (敏感关键词) + 终止链
  base64 串 (长度 ≥ 12, 可解码) → severity=4
  base32 串 (长度 ≥ 12) → severity=4
  binary 串 (0/1 chars, 长度 ≥ 32) → severity=4
  hex 串 (0-9a-f, 长度 ≥ 32) → severity=4
  普通文本 → severity=3 (Q1 兜底, 让用户看)
```
"""
from __future__ import annotations

from automisc.core.utils.rule_scanner import (
    TextMatch,
    classify_text,
    has_sensitive_keyword,
    has_any_suspicious,
    is_base32,
    is_base64,
    is_binary_string,
    is_hex_string,
    max_severity,
)


def score_text_severity(text: str) -> int:
    """Q1 主入口: 给 LSB 抽出的 text 打严重度.

    Returns:
        0 = 空 / 无命中
        3 = 普通文本 (兜底)
        4 = 编码特殊形态 (base64/binary/hex)
        5 = 敏感关键词 (secret/key/flag/ctf/password)
    """
    if not text or not text.strip():
        return 0
    matches = classify_text(text)
    if not matches:
        return 3  # 普通文本兜底
    return max(m.severity for m in matches)


# 兼容旧 import (v0.5-LSB-router 已在用)
# 这些 wrapper 保留是因为 lsb_router 集成测试和 lsb_extract.py 内部用


__all__ = [
    "TextMatch",
    "classify_text",
    "has_sensitive_keyword",
    "has_any_suspicious",
    "is_base64",
    "is_base32",
    "is_binary_string",
    "is_hex_string",
    "max_severity",
    "score_text_severity",
]
