"""Base 家族 + ROT 家族 + Base64 隐写 decoder（per v0.5-base-rot-decoders PR3）

**14 个 decoder 聚合注册**：
- Base 系列 (10): base16 / base32 / base36 / base58 / base62 / base64 / base85 / base91 / base92 / base100 / base32768 / base65536
  - 实际 12 个: 16/32/36/58/62/64/85/91/92/100/32768/65536
- ROT 系列 (4): rot5 / rot13 / rot18 / rot47
- Base64 隐写 (1): base64-stego
- 特殊 (1): base64-custom (interactive, 弹 QInputDialog 要表)

**架构**：
- 所有 decoder 都基于 ``core/encoders/`` 模块
- runner 函数统一签名 ``(text: str | None, file_path: str | None, **kwargs) -> ResultDataclass``
- 失败抛 ValueError / CustomError, 不返回 None（GUI 显示错误）

**GUI 集成**：
- 14 个统一在 "🔐 Base/ROT 解码" 二级分类下（per Owner 17:09 扁平决策）
- base64-custom 标 ``interactive=True``，触发时弹 QInputDialog 要 64 字符表
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from automisc.core.encoders import base as base_mod
from automisc.core.encoders import base_custom
from automisc.core.encoders import base64_stego
from automisc.core.encoders import classical


# === Result 数据类（统一所有 base/rot decoder 的输出）===

@dataclass
class DecodeResult:
    """decoder 通用结果.

    Attributes:
        codec: 解码方式 (e.g. "base16", "rot13")
        input: 输入文本
        output_text: 解出的 ASCII (utf-8 decode, 失败用 'replace')
        output_bytes: 解出的原始 bytes
        hint: 额外提示 (e.g. "CTF 自定义表偏移 N 位")
        error: 解码错误 (None = 成功)
    """
    codec: str
    input: str
    output_text: str = ""
    output_bytes: bytes = b""
    hint: str = ""
    error: Optional[str] = None

    def __bool__(self) -> bool:
        return self.error is None


# === Base 系列统一 runner ===

def _make_base_runner(codec_name: str, decode_fn, encode_fn=None):
    """生成 base 系列 decoder 的统一 runner.

    Args:
        codec_name: e.g. "base16"
        decode_fn: function(s: str) -> bytes
        encode_fn: function(data: bytes) -> str (optional)
    """
    def runner(text: str | None = None, file_path: str | None = None, **_):
        if text is not None:
            data = text
        elif file_path is not None:
            from pathlib import Path
            p = Path(file_path)
            if not p.exists():
                raise FileNotFoundError(f"input not found: {file_path}")
            data = p.read_text(errors="replace")
        else:
            raise ValueError(f"{codec_name}: 需要 text 或 file_path")

        try:
            decoded_bytes = decode_fn(data.strip())
        except ValueError as e:
            return DecodeResult(
                codec=codec_name, input=data, error=str(e)
            )

        try:
            output_text = decoded_bytes.decode("utf-8", errors="replace")
        except Exception:
            output_text = ""

        return DecodeResult(
            codec=codec_name,
            input=data,
            output_text=output_text,
            output_bytes=decoded_bytes,
        )

    runner.__name__ = f"run_{codec_name}"
    return runner


# === ROT 系列统一 runner ===

def _make_rot_runner(codec_name: str, fn):
    """ROT 系列 runner（不需 bytes，直接返回 str）"""
    def runner(text: str | None = None, file_path: str | None = None, **_):
        if text is not None:
            data = text
        elif file_path is not None:
            from pathlib import Path
            p = Path(file_path)
            if not p.exists():
                raise FileNotFoundError(f"input not found: {file_path}")
            data = p.read_text(errors="replace")
        else:
            raise ValueError(f"{codec_name}: 需要 text 或 file_path")

        try:
            output = fn(data)
        except (ValueError, TypeError) as e:
            return DecodeResult(codec=codec_name, input=data, error=str(e))

        return DecodeResult(
            codec=codec_name,
            input=data,
            output_text=output,
        )
    runner.__name__ = f"run_{codec_name}"
    return runner


# === Base64 隐写 runner ===

def run_base64_stego(
    text: str | None = None,
    file_path: str | None = None,
    hint_bytes: int | None = None,
    **_,
):
    """base64 stego 解码（每字符末 2 bit 提取）"""
    if text is not None:
        data = text
    elif file_path is not None:
        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        data = p.read_text(errors="replace")
    else:
        raise ValueError("base64-stego: 需要 text 或 file_path")

    try:
        if hint_bytes is not None:
            decoded_bytes = base64_stego.extract_hidden_with_size_hint(data, hint_bytes=hint_bytes)
            hint_msg = f"已截断到 {hint_bytes} bytes"
        else:
            decoded_bytes = base64_stego.decode_base64_stego(data)
            hint_msg = f"自动提取 {len(decoded_bytes)} bytes（可能含末尾垃圾，CTF 通常用 hint_bytes 截断）"
    except ValueError as e:
        return DecodeResult(codec="base64-stego", input=data, error=str(e))

    try:
        output_text = decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        output_text = ""

    return DecodeResult(
        codec="base64-stego",
        input=data,
        output_text=output_text,
        output_bytes=decoded_bytes,
        hint=hint_msg,
    )


# === Base64 自定义表 runner (interactive) ===

def run_base64_custom(
    text: str | None = None,
    file_path: str | None = None,
    custom_table: str | None = None,
    **_,
):
    """base64 自定义表解码（CTF 常见，需要用户提供 64 字符表）

    Args:
        custom_table: 64 字符表（GUI 通过 QInputDialog 收集, CLI 通过 --custom-table 参数）
    """
    if custom_table is None:
        raise ValueError(
            "base64-custom: 需要 custom_table 参数 (GUI 弹 QInputDialog / CLI 用 --custom-table)"
        )
    if len(custom_table) != 64:
        raise ValueError(f"custom_table 长度必须为 64，当前 {len(custom_table)}")

    if text is not None:
        data = text
    elif file_path is not None:
        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        data = p.read_text(errors="replace")
    else:
        raise ValueError("base64-custom: 需要 text 或 file_path")

    try:
        decoded_bytes = base_custom.decode_base64_custom(data.strip(), custom_table)
    except ValueError as e:
        return DecodeResult(codec="base64-custom", input=data, error=str(e))

    try:
        output_text = decoded_bytes.decode("utf-8", errors="replace")
    except Exception:
        output_text = ""

    # 尝试检测位移（如果明文碰巧已知）
    return DecodeResult(
        codec="base64-custom",
        input=data,
        output_text=output_text,
        output_bytes=decoded_bytes,
        hint=f"使用自定义表: {custom_table[:16]}... (len=64)",
    )


# === 注册所有 14 个 decoder ===

def _register_all() -> None:
    from automisc.core.decoders.registry import DecoderSpec, register_decoder

    # === Base 系列 (12 个) ===
    BASE_DECODERS = [
        ("base16", "🔢 Base16", base_mod.decode_base16, "Hex (0-9 a-f) 解码"),
        ("base32", "🔢 Base32", base_mod.decode_base32, "A-Z 2-7 解码"),
        ("base36", "🔢 Base36", base_mod.decode_base36, "0-9 a-z (CTF 偶尔)"),
        ("base58", "🔢 Base58", base_mod.decode_base58, "Bitcoin 风格 (无 0OIl)"),
        ("base62", "🔢 Base62", base_mod.decode_base62, "0-9 A-Z a-z"),
        ("base64", "🔢 Base64", base_mod.decode_base64, "标准 base64"),
        ("base85", "🔢 Base85", base_mod.decode_base85, "ASCII85 风格"),
        ("base91", "🔢 Base91", base_mod.decode_base91, "91 字符高密度"),
        ("base92", "🔢 Base92", base_mod.decode_base92, "92 字符（去 \\\"）"),
        ("base100", "🔢 Base100", base_mod.decode_base100, "100 字符（CTF 极罕见）"),
        ("base32768", "🔢 Base32768", base_mod.decode_base32768, "CJK 基本平面 (CTF 罕见)"),
        ("base65536", "🔢 Base65536", base_mod.decode_base65536, "Unicode BMP (PyPI 库)"),
    ]

    for name, display, decode_fn, desc in BASE_DECODERS:
        register_decoder(
            DecoderSpec(
                name=name,
                display=display,
                category="base_rot",
                cli_cmd=f"decode {name}",
                run=_make_base_runner(name, decode_fn),
                description=f"{desc} → ASCII (per core/encoders/base.py)",
                text_only=True,  # v0.5-cipher-decoders-textfix: 全 text input
            )
        )

    # === ROT 系列 (4 个) ===
    register_decoder(
        DecoderSpec(
            name="rot5",
            display="🅰 ROT5",
            category="base_rot",
            cli_cmd="decode rot5",
            run=_make_rot_runner("rot5", classical.rot5),
            description="Digits 0-9 旋转 5 位 (CTF 数字密码)",
            text_only=True,
        )
    )
    register_decoder(
        DecoderSpec(
            name="rot13",
            display="🅰 ROT13",
            category="base_rot",
            cli_cmd="decode rot13",
            run=_make_rot_runner("rot13", classical.rot13),
            description="字母 A-Z a-z 旋转 13 位 (凯撒密码)",
            text_only=True,
        )
    )
    register_decoder(
        DecoderSpec(
            name="rot18",
            display="🅰 ROT18",
            category="base_rot",
            cli_cmd="decode rot18",
            run=_make_rot_runner("rot18", classical.rot18),
            description="ROT13(字母) + ROT5(数字) 组合",
            text_only=True,
        )
    )
    register_decoder(
        DecoderSpec(
            name="rot47",
            display="🌀 ROT47",
            category="base_rot",
            cli_cmd="decode rot47",
            run=_make_rot_runner("rot47", classical.rot47),
            description="ASCII 33-126 整段旋转 47 位 (藏 base64 结果常用)",
            text_only=True,
        )
    )

    # === Base64 自定义表 (1 个, interactive) ===
    register_decoder(
        DecoderSpec(
            name="base64-custom",
            display="🔐 Base64 自定义表",
            category="base_rot",
            cli_cmd="decode base64-custom",
            run=run_base64_custom,
            description="CTF 变体 base64 (用户提供 64 字符表); interactive=True 弹 QInputDialog",
            text_only=True,
        )
    )

    # === Base64 隐写 (1 个) ===
    register_decoder(
        DecoderSpec(
            name="base64-stego",
            display="🕵 Base64 隐写",
            category="base_rot",
            cli_cmd="decode base64-stego",
            run=run_base64_stego,
            description="base64 末 2 bit 隐写解码 (per core/encoders/base64_stego.py)",
            text_only=True,
        )
    )


_register_all()


__all__ = [
    "DecodeResult",
    "run_base64_stego",
    "run_base64_custom",
]
