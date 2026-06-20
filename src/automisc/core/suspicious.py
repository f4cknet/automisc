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

# 关键字列表（大小写不敏感）
KEYWORDS: list[str] = [
    "password",
    "secret",
    "hidden",
    "encrypt",
    "cipher",
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
    "keyword": (1, "结合上下文判断是否敏感"),
    "base64_candidate": (3, "尝试 base64 解码"),
    "base32_candidate": (3, "尝试 base32 解码"),
    "hex_string": (3, "尝试 hex 解码（xxd -r）"),
}


def _keyword_pattern() -> re.Pattern:
    """构造关键字正则（case-insensitive）。"""
    escaped = [re.escape(k) for k in KEYWORDS]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


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