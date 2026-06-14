"""文本规则扫描器（v0.5+ 独立规则库）

**职责**：从任意 text 中提取"可疑子串"，返回结构化命中。

**重构动机**（per Owner 2026-06-14）：
- 旧 `encoding_detector.is_*` 系列只判断"整段 text 是不是 base64/binary/hex" — 粒度太粗
- CTF strings 输出**多行**（一行一个字符串），要逐行扫
- LSB 抽出的 text 也常含"长 hex 串 + 普通文字"混搭 — 要在长 text 里**定位**子串
- 解耦后供 `encoding_detector` / `strings|grep` / 其他模块复用

**规则清单**（per Owner Q1 决策 + lsb-router 已有）:

| category | 模式 | severity | 例子 |
|---|---|---|---|
| `sensitive_keyword` | `secret/key/flag/ctf/password` 出现 | **5** | "secret key is: st3g0" |
| `base64` | `^[A-Za-z0-9+/]{12,}={0,2}$` + 可解码 | 4 | "aGVsbG8gd29ybGQ=" |
| `base32` | `^[A-Z2-7]{12,}={0,6}$` | 4 | "JBSWY3DPEB3W64TMMQ======" |
| `hex` | `^[0-9A-Fa-f]{32,}$` | 4 | "deadbeefcafe1234567890abcdef" |
| `binary` | `^[01]{32,}$` | 4 | "010101001110110010110100" |

**使用**:
```python
from automisc.core.utils.rule_scanner import classify_text
matches = classify_text(long_text)
for m in matches:
    print(m.category, m.severity, repr(m.value))
```
"""
from __future__ import annotations

import base64
import re
import string
from dataclasses import dataclass
from typing import Final


# 敏感关键词 (Q1 + Owner 后补, 与 encoding_detector 同步)
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

# 分类 category 常量
CATEGORY_SENSITIVE = "sensitive_keyword"
CATEGORY_BASE64 = "base64"
CATEGORY_BASE32 = "base32"
CATEGORY_HEX = "hex"
CATEGORY_BINARY = "binary"


@dataclass(frozen=True)
class TextMatch:
    """一次规则命中.

    Attributes:
        category: 规则分类 (sensitive_keyword / base64 / base32 / hex / binary)
        value: 命中的子串内容
        span_start: 在原 text 中的起始偏移 (None = 全段)
        span_end: 在原 text 中的结束偏移 (None = 全段)
        severity: 严重度 (3/4/5)
    """

    category: str
    value: str
    severity: int
    span_start: int = 0
    span_end: int = 0

    @property
    def is_sensitive(self) -> bool:
        """是否含敏感关键词 (severity=5) — owner 重点关注."""
        return self.severity >= 5


# ---------- 单规则函数 (per line / per 整段) ----------
def has_sensitive_keyword(text: str) -> bool:
    """text 是否含 secret/key/flag/ctf/password (Q1 高度敏感)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _SENSITIVE_KEYWORDS)


def find_sensitive_keywords(text: str) -> list[TextMatch]:
    """在 text 中找所有敏感关键词 + 完整命中 substring.

    Returns:
        每命中一个 keyword 返回 1 个 TextMatch
        e.g. "the secret key is: abc" -> 2 matches (secret, key)
    """
    matches = []
    text_lower = text.lower()
    for kw in _SENSITIVE_KEYWORDS:
        start = 0
        while True:
            idx = text_lower.find(kw, start)
            if idx < 0:
                break
            matches.append(
                TextMatch(
                    category=CATEGORY_SENSITIVE,
                    value=text[idx : idx + len(kw)],
                    severity=5,
                    span_start=idx,
                    span_end=idx + len(kw),
                )
            )
            start = idx + len(kw)
    return matches


def is_base64(text: str) -> bool:
    """text 整段是否像 base64 (核心字符 ≥ 12 + 字符集匹配 + 可解码).

    注意: hex 串 (仅 0-9a-f) 是 base64 字符集子集, 也匹配.
    调用方应先检 hex (per is_hex_string).
    """
    if not _BASE64_RE.match(text):
        return False
    try:
        base64.b64decode(text, validate=False)
        return True
    except Exception:
        return False


def is_base32(text: str) -> bool:
    """text 整段是否像 base32 (核心字符 ≥ 12 + 字符集匹配)."""
    return bool(_BASE32_RE.match(text))


def is_hex_string(text: str) -> bool:
    """text 整段是否像 hex 串 (仅 0-9a-f, 长度 ≥ 32, 偶数长度).

    hex 是 base64 字符集子集, 这里**严格**: 必须仅含 0-9a-f (不含 +/= 也不含 g-z)
    且偶数长度 (hex 编码都是偶数 bytes).
    """
    if not _HEX_RE.match(text):
        return False
    if len(text) % 2 != 0:
        return False
    return True


def is_binary_string(text: str) -> bool:
    """text 整段是否像 binary 串 (0/1 chars, 长度 ≥ 32)."""
    return bool(_BINARY_RE.match(text))


def _classify_single_token(text: str) -> TextMatch | None:
    """单 token (整段) 分类. None = 不是编码特殊形态 / 不含敏感词.

    **优先级** (per Owner 2026-06-14):
    1. binary (chars 集最窄, 最具体)
    2. hex (chars 集次窄, 是 base64 子集)
    3. base32 (chars 集不含小写)
    4. base64 (chars 集最宽, 兜底)

    注意: sensitive_keyword 不在此处判定 (会触发 has_sensitive_keyword 的子串匹配,
    错判整段含密码等 text).
    sensitive_keyword 判定在 classify_text 顶层 (per line/per 整段).
    """
    if is_binary_string(text):
        return TextMatch(category=CATEGORY_BINARY, value=text, severity=4)
    if is_hex_string(text):
        return TextMatch(category=CATEGORY_HEX, value=text, severity=4)
    if is_base32(text):
        return TextMatch(category=CATEGORY_BASE32, value=text, severity=4)
    if is_base64(text):
        return TextMatch(category=CATEGORY_BASE64, value=text, severity=4)
    return None


# ---------- 主入口 ----------
def classify_text(text: str) -> list[TextMatch]:
    """主入口: 扫整段 text, 返回所有规则命中 (去重).

    算法 (per Owner 2026-06-14):
    1. 单行 (1 个 \\n 或 无 \\n):
       a. 整段先看 sensitive_keyword (severity 5) -> 1 match
       b. 整段看是不是 hex/base64/base32/binary -> 1 match
       c. 整段是普通文本但在 text 内含 base64/hex 子串 -> 用子串匹配 (适配 LSB 抽出 long text)
    2. 多行 (2+ \\n): 逐行扫 (适配 strings 输出多行)
       - 每行: 整行 = 编码 -> 记 1 个 match
       - 每行: 整行含 keyword -> 记 keyword 位置
       - 每行: 普通文本 -> 跳过

    Args:
        text: 任意字符串 (单行 / 多行 / 混合)

    Returns:
        list[TextMatch] — 所有规则命中 (按出现顺序)
    """
    if not text or not text.strip():
        return []

    matches: list[TextMatch] = []
    lines = text.splitlines()
    is_multiline = len(lines) > 1

    if not is_multiline:
        # 单行: 整段判定优先
        single_line = lines[0].strip()
        # a. sensitive_keyword (severity 5, 最高)
        sensitive_matches = find_sensitive_keywords(single_line)
        if sensitive_matches:
            matches.append(
                TextMatch(
                    category=CATEGORY_SENSITIVE,
                    value=single_line,
                    severity=5,
                )
            )
            return matches
        # b. 整段 = 编码
        whole = _classify_single_token(single_line)
        if whole is not None:
            matches.append(whole)
            return matches
        # c. 整段不命中 -> 子串匹配 (适配 long text with embedded base64/hex)
        # 找 _SENSITIVE_KEYWORDS 子串
        for m in find_sensitive_keywords(single_line):
            matches.append(m)
        # 找 base64/hex/binary 子串
        for m in _find_substring_encodings(single_line):
            matches.append(m)
        return matches

    # 多行: 逐行扫
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line_offset = text.find(line)
        # 整行 = 编码
        line_match = _classify_single_token(line)
        if line_match is not None:
            line_match = TextMatch(
                category=line_match.category,
                value=line_match.value,
                severity=line_match.severity,
                span_start=line_offset,
                span_end=line_offset + len(line),
            )
            matches.append(line_match)
            continue
        # 整行普通文本: 找敏感关键词
        for m in find_sensitive_keywords(line):
            matches.append(
                TextMatch(
                    category=m.category,
                    value=m.value,
                    severity=m.severity,
                    span_start=line_offset + m.span_start,
                    span_end=line_offset + m.span_end,
                )
            )

    return matches


# ---------- 子串编码匹配 (适配 LSB long text + 数据 URL 头场景) ----------
# 在 long text 内找 base64 / hex / binary 子串 (忽略敏感词子串, 那个 find_sensitive_keywords 单独处理)

# base64 substring regex: 至少 12 chars + 0-2 padding
_B64_SUB_RE = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")
# hex substring regex: 至少 32 chars (16 bytes), 不带空格
_HEX_SUB_RE = re.compile(r"[0-9A-Fa-f]{32,}")
# binary substring regex: 至少 32 chars
_BIN_SUB_RE = re.compile(r"[01]{32,}")


def _find_substring_encodings(text: str) -> list[TextMatch]:
    """在 text 内找所有编码子串 (返回 TextMatch list, span 准确)."""
    matches = []
    # base64 子串
    for m in _B64_SUB_RE.finditer(text):
        s = m.group(0)
        # 必须能严格 decode
        try:
            base64.b64decode(s, validate=False)
        except Exception:
            continue
        matches.append(
            TextMatch(
                category=CATEGORY_BASE64,
                value=s,
                severity=4,
                span_start=m.start(),
                span_end=m.end(),
            )
        )
    # hex 子串 (且**不**与已匹配的 base64 子串重叠)
    for m in _HEX_SUB_RE.finditer(text):
        s = m.group(0)
        # 跳过已被 base64 命中的部分
        if any(
            mm.span_start <= m.start() and mm.span_end >= m.end()
            for mm in matches
        ):
            continue
        matches.append(
            TextMatch(
                category=CATEGORY_HEX,
                value=s,
                severity=4,
                span_start=m.start(),
                span_end=m.end(),
            )
        )
    # binary 子串
    for m in _BIN_SUB_RE.finditer(text):
        s = m.group(0)
        if any(
            mm.span_start <= m.start() and mm.span_end >= m.end()
            for mm in matches
        ):
            continue
        matches.append(
            TextMatch(
                category=CATEGORY_BINARY,
                value=s,
                severity=4,
                span_start=m.start(),
                span_end=m.end(),
            )
        )
    return matches


def has_any_suspicious(text: str) -> bool:
    """text 是否含任何规则命中 (含敏感词 / 编码特殊形态)."""
    return len(classify_text(text)) > 0


def max_severity(text: str) -> int:
    """text 中所有命中的最高 severity. 0 = 无命中."""
    matches = classify_text(text)
    if not matches:
        return 0
    return max(m.severity for m in matches)


__all__ = [
    "TextMatch",
    "CATEGORY_SENSITIVE",
    "CATEGORY_BASE64",
    "CATEGORY_BASE32",
    "CATEGORY_HEX",
    "CATEGORY_BINARY",
    "has_sensitive_keyword",
    "find_sensitive_keywords",
    "is_base64",
    "is_base32",
    "is_hex_string",
    "is_binary_string",
    "classify_text",
    "has_any_suspicious",
    "max_severity",
]
