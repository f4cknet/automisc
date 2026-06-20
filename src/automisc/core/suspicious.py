"""SuspiciousPoint dataclass + 关键字扫描器（per ``prd.md`` §7 + ``Architecture.md`` §3.5）

v0.1.0b-PR1 范围：
- ``SuspiciousPoint`` dataclass（统一 schema）
- ``SUSPICIOUS_PATTERNS`` 关键字 / 正则集合（最小可用）
- ``scan_output_for_suspicious()`` 扫描函数
- 4 类 category: flag / keyword / file_header（hex 字节）/ base64_candidate

v0.1.0b-PR1 不做的事：
- file_header 二进制扫描（v0.5+ 优化）
- 完整 webshell 家族识别（v0.5+）
- 高精度 hex 串识别（v0.5+）
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SuspiciousPoint:
    """可疑点统一 schema（per ``prd.md`` §7）。"""

    id: str
    tool_name: str
    file_path: str
    category: str
    matched_pattern: str
    severity: int  # 1=info / 3=warn / 5=critical
    suggested_action: str
    offset: int | None = None
    context: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())


# 关键字 / 正则集合（v0.1 最小可用）
SUSPICIOUS_PATTERNS: dict[str, re.Pattern] = {
    # flag 格式（最优先 — 比赛直接判定）
    "flag": re.compile(
        r"(?:flag|ctf|key)\{[^}]{1,256}\}",
        re.IGNORECASE,
    ),
    # base64 候选（长度 16+，字符集合法）
    "base64_candidate": re.compile(
        r"^[A-Za-z0-9+/]{16,}={0,2}$",
        re.MULTILINE,
    ),
    # base32 候选
    "base32_candidate": re.compile(
        r"^[A-Z2-7]{16,}={0,6}$",
        re.MULTILINE,
    ),
    # 纯 hex 字符串
    "hex_string": re.compile(
        r"^[0-9A-Fa-f]{16,}$",
        re.MULTILINE,
    ),
}

# 关键字列表（大小写不敏感，子串匹配，不用正则）
# per Owner 2026-06-20 18:03 + 18:05 拍板 (跨项目铁律):
# pass | password | key | flag | f1ag | p@ssw0rd | secret | ctf
# 实战累积 — 遇到新的同类 keyword, owner 拍板后加
KEYWORDS: list[str] = [
    # 高优先级可疑关键词（per Owner 铁律）
    "pass",
    "password",
    "key",
    "flag",
    "f1ag",
    "p@ssw0rd",
    "secret",
    "ctf",
    # 工具名（per v0.5-相关历史决策 — 命中表示含该工具的处理痕迹）
    "steghide",
    "stegseek",
    "outguess",
    "stegdetect",
    "jsteg",
    "zsteg",
    "binwalk",
    "foremost",
]

# category → (severity, suggested_action) 映射
SEVERITY_MAP: dict[str, tuple[int, str]] = {
    "flag": (5, "直接拿 flag 提交"),
    # per Owner 2026-06-20 18:03 + 18:05 拍板铁律: 高优先级可疑关键词命中 = severity 5
    # (与 rule_scanner.CATEGORY_SENSITIVE severity=5 保持一致)
    # 不触发 short-circuit — SHORT_CIRCUIT_SEVERITY=99 (per v0.5-journal-highlight-keywords Q12 拍板)
    "keyword": (5, "高优先级可疑关键词命中 (pass/password/key/flag/f1ag/p@ssw0rd/secret/ctf), 检查上下文"),
    "base64_candidate": (3, "尝试 base64 解码"),
    "base32_candidate": (3, "尝试 base32 解码"),
    "hex_string": (3, "尝试 hex 解码（xxd -r）"),
}


def _keyword_pattern() -> re.Pattern:
    """构造关键字正则（case-insensitive + 子串匹配，不用 \\b 边界 + 长 keyword 优先）.

    per Owner 2026-06-20 18:03 + 18:05 拍板铁律:
    - 子串匹配 (不是 \\\\b word boundary) — `this_is_not_password` / `passphrase` /
      `p@ssphrase` / `PASSWORD` / `PassWord` 全部命中
    - case-insensitive (IGNORECASE) — F1AG / PASS / Password 全部命中
    - 不用正则做整段匹配 — 用 keyword 子串定位
    - **长度降序** — `password` (8) 排在 `pass` (4) 之前,
      否则正则 alternatives 按顺序匹配会先吃 `pass`,
      `password=hunter2` 命中 `pass` 而不是 `password`

    修前 bug (per Owner 18:03 实测):
    - 旧实现 `\\\\b(?:` + kws + `)\\\\b` → `this_is_not_password` 里的 `password`
      前面是 `_`，word boundary 不匹配，SP 漏生成，journal 不收
    - 修后: 直接 `(?:` + kws + `)` → 子串命中，severity 5 SP 进 journal
    """
    # 长度降序 — `password` (8) 在 `pass` (4) 前, `p@ssw0rd` (8) 在 `pass` 前
    escaped = sorted((re.escape(k) for k in KEYWORDS), key=len, reverse=True)
    return re.compile("(?:" + "|".join(escaped) + ")", re.IGNORECASE)


def scan_output_for_suspicious(
    *,
    tool_name: str,
    file_path: str,
    stdout: str,
) -> list[SuspiciousPoint]:
    """扫描工具输出，提取所有可疑点。

    Args:
        tool_name: 触发的工具名
        file_path: 原始文件路径
        stdout: 工具的 stdout 输出

    Returns:
        SuspiciousPoint 列表（去重前；调用方决定是否去重）
    """
    points: list[SuspiciousPoint] = []

    # 1. flag 正则（最高优先级）
    for m in SUSPICIOUS_PATTERNS["flag"].finditer(stdout):
        sev, action = SEVERITY_MAP["flag"]
        matched = m.group(0)
        start = max(0, m.start() - 16)
        end = min(len(stdout), m.end() + 16)
        context = stdout[start:end].replace("\n", "\\n")
        points.append(
            SuspiciousPoint(
                id="",
                tool_name=tool_name,
                file_path=file_path,
                category="flag",
                offset=m.start(),
                matched_pattern=matched,
                severity=sev,
                suggested_action=action,
                context=context,
            )
        )

    # 2. 关键字
    kw_re = _keyword_pattern()
    seen_kw: set[tuple[int, str]] = set()
    for m in kw_re.finditer(stdout):
        key = (m.start(), m.group(0).lower())
        if key in seen_kw:
            continue
        seen_kw.add(key)
        sev, action = SEVERITY_MAP["keyword"]
        points.append(
            SuspiciousPoint(
                id="",
                tool_name=tool_name,
                file_path=file_path,
                category="keyword",
                offset=m.start(),
                matched_pattern=m.group(0),
                severity=sev,
                suggested_action=action,
            )
        )

    # 3. base64 / base32 / hex candidates（仅取每类前 5 个，避免海量误报）
    for cat in ("base64_candidate", "base32_candidate", "hex_string"):
        count = 0
        for m in SUSPICIOUS_PATTERNS[cat].finditer(stdout):
            if count >= 5:
                break
            sev, action = SEVERITY_MAP[cat]
            points.append(
                SuspiciousPoint(
                    id="",
                    tool_name=tool_name,
                    file_path=file_path,
                    category=cat,
                    offset=m.start(),
                    matched_pattern=m.group(0)[:80],
                    severity=sev,
                    suggested_action=action,
                )
            )
            count += 1

    return points