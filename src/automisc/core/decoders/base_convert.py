"""Hex/Binary/Base64/Base32 → ASCII 转换器（v0.5-base-convert）

**Owner 触发**（2026-06-14 Bug 修 2/3）：
> "在工具栏没有16进制转ascii的工具"

**职责**：把 4 种进制的串 → ASCII 字符串。GUI 工具栏入口 + CLI `automisc decode hex-ascii` 子命令。

**算法**：
1. 读 input (字符串)
2. 探测格式 (按规则：hex 优先 > binary > base64 > base32)
3. decode → ASCII
4. 输出 result dataclass (input / detected_format / output_text / errors)

**vs v0.5-base64-image**：
- 那个 decode 图片 (输出 file)
- 这个 decode 文本 (输出 string, 不写文件)
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Final


# 与 rule_scanner 同步的 regex
_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]+$")
_BIN_RE: Final[re.Pattern[str]] = re.compile(r"^[01]+$")
_BASE32_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z2-7]+={0,6}$")
_BASE64_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


class BaseConvertError(Exception):
    """进制转换失败."""

    pass


@dataclass
class BaseConvertResult:
    """转换结果.

    Attributes:
        input: 输入串
        detected_format: 探测到的格式 (hex / binary / base64 / base32 / text)
        output_text: 解出的 ASCII
        errors: 探测/解码错误 (None = 成功)
    """

    input: str
    detected_format: str
    output_text: str
    errors: str | None = None


def _strip_text(s: str) -> str:
    """剥前缀 (e.g. "data:..." / "0x" / 换行 / 空白)."""
    s = s.strip()
    # 常见前缀
    for prefix in ("0x", "0X", "\\x", "0b"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    # 剥换行
    s = s.replace("\n", "").replace("\r", "").replace(" ", "")
    return s


def detect_and_decode(text: str) -> tuple[str, str]:
    """探测 + decode.

    优先级 (per Owner 2026-06-14):
    1. binary 优先 (chars 最窄, 0/1 only) — 避免 binary 串被判 hex
    2. hex (chars 次窄) — base64 子集, 但 binary 已先检
    3. base32
    4. base64

    Returns:
        (format, decoded_text)
    Raises:
        BaseConvertError: 不是任何已知格式
    """
    s = _strip_text(text)
    if not s:
        raise BaseConvertError("input is empty")

    # 1. binary (优先, 避免 0101.. 串被判 hex)
    if len(s) >= 8 and len(s) % 8 == 0 and _BIN_RE.match(s):
        try:
            chars = [
                chr(int(s[i : i + 8], 2))
                for i in range(0, len(s), 8)
            ]
            return "binary", "".join(chars)
        except Exception as e:
            raise BaseConvertError(f"binary decode failed: {e}")

    # 2. hex
    if len(s) >= 2 and len(s) % 2 == 0 and _HEX_RE.match(s):
        try:
            decoded = bytes.fromhex(s).decode("utf-8", errors="replace")
            return "hex", decoded
        except Exception as e:
            raise BaseConvertError(f"hex decode failed: {e}")

    # 3. base64
    if len(s) >= 4 and _BASE64_RE.match(s):
        try:
            decoded = base64.b64decode(s, validate=False).decode(
                "utf-8", errors="replace"
            )
            return "base64", decoded
        except Exception as e:
            raise BaseConvertError(f"base64 decode failed: {e}")

    # 4. base32
    if len(s) >= 4 and _BASE32_RE.match(s):
        try:
            decoded = base64.b32decode(s).decode("utf-8", errors="replace")
            return "base32", decoded
        except Exception as e:
            raise BaseConvertError(f"base32 decode failed: {e}")

    raise BaseConvertError(
        f"无法识别格式 (len={len(s)}, "
        f"head={s[:30]!r}, "
        f"hex_valid={bool(_HEX_RE.match(s))}, "
        f"bin_valid={bool(_BIN_RE.match(s))})"
    )


def convert_text_to_ascii(text: str) -> BaseConvertResult:
    """主入口: text -> 探测格式 -> decode.

    Args:
        text: 输入字符串 (hex / binary / base64 / base32 之一)

    Returns:
        BaseConvertResult

    Raises:
        BaseConvertError: 不是任何已知格式 / 解码失败
    """
    try:
        fmt, decoded = detect_and_decode(text)
        return BaseConvertResult(
            input=text,
            detected_format=fmt,
            output_text=decoded,
        )
    except BaseConvertError as e:
        return BaseConvertResult(
            input=text,
            detected_format="unknown",
            output_text="",
            errors=str(e),
        )


# ---------- v0.5-decoder-menu: 注册到 registry ----------
def _register() -> None:
    from automisc.core.decoders.registry import DecoderSpec, register_decoder

    def _runner(file_path: str, **_):
        from pathlib import Path
        text = Path(file_path).read_text(errors="replace")
        return convert_text_to_ascii(text)

    register_decoder(
        DecoderSpec(
            name="hex-ascii",
            display="🔢 Hex → ASCII",
            category="convert",
            cli_cmd="decode hex-ascii",
            run=_runner,
            description="Hex / Binary / Base64 / Base32 → ASCII 转换（自动探测格式）",
        )
    )


_register()


__all__ = [
    "BaseConvertError",
    "BaseConvertResult",
    "convert_text_to_ascii",
    "detect_and_decode",
]
