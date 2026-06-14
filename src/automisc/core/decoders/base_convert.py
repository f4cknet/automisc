"""Hex/Binary/Base64/Base32 → ASCII 转换器（v0.5-base-convert, v0.5-hex-ascii-fix）

**Owner 触发**（2026-06-14 Bug 修 2/3）：
> "在工具栏没有16进制转ascii的工具"

**职责**：把 4 种进制的串 → ASCII 字符串。GUI 工具栏入口 + CLI `automisc decode hex-ascii` 子命令。

**算法**：
1. 读 input (字符串)
2. 探测格式 (按规则：binary > hex > base64 > base32)
3. decode → ASCII
4. 输出 result dataclass (input / detected_format / output_text / errors)

**v0.5-hex-ascii-fix (2026-06-14 09:50)**:
- **修 Bug**：之前 _runner 读整个 file 当 hex 解，对 233KB meihuai.jpg 触发卡死 + 乱码
- **新行为**：input 必须是**字符串** (用户的 hex 串), 不是文件路径
  - CLI: `--text "<hex串>"` 直接传, 或 `--file <txt>` 读文件当 text
  - GUI: 菜单栏触发从 input 区读 (selection 优先, 否则最后像 base 的行)
- 之前的 _runner 行为 (file_path=读文件) 保留, 但仅当 file 很小 (e.g. 用户写 `28372c37290a` 到 .txt)
- 加上 size guard: 文本超过 1MB 直接拒绝 (避免 OOM)

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


# v0.5-hex-ascii-fix: 上限 (1MB) — 1KB hex 解出 512 字节, 1MB 解 500KB, 够用
MAX_INPUT_SIZE: Final[int] = 1 * 1024 * 1024


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

    def _runner(file_path: str | None = None, text: str | None = None, **_):
        """v0.5-hex-ascii-fix: 接受 text 优先, 退回 file_path.

        Args:
            file_path: 文件路径 (用户写 hex 串到 .txt)
            text: 直接传 hex 串 (CLI --text / GUI 内部)
        """
        if text is not None:
            return convert_text_to_ascii(text)
        if file_path is None:
            raise BaseConvertError(
                "需要 --text '<hex串>' 或 --file <含hex的txt文件> (v0.5-hex-ascii-fix)"
            )
        # file_path 模式: 读文件当 text
        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        text = p.read_text(errors="replace")
        if len(text) > MAX_INPUT_SIZE:
            raise BaseConvertError(
                f"input too large: {len(text)} bytes (max {MAX_INPUT_SIZE}); "
                f"hex-ascii 只设计解短串 (典型 < 1KB), 大文件请用 strings/foremost 等其他工具"
            )
        return convert_text_to_ascii(text)

    register_decoder(
        DecoderSpec(
            name="hex-ascii",
            display="🔢 Hex → ASCII",
            category="convert",
            cli_cmd="decode hex-ascii",
            run=_runner,
            description="Hex / Binary / Base64 / Base32 → ASCII 转换 (自动探测格式; v0.5-hex-ascii-fix)",
        )
    )


_register()


__all__ = [
    "BaseConvertError",
    "BaseConvertResult",
    "MAX_INPUT_SIZE",
    "convert_text_to_ascii",
    "detect_and_decode",
]
