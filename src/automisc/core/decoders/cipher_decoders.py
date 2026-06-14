"""12 个经典 cipher decoder 聚合注册（per v0.5-cipher-decoders）

**Owner 18:20 任务**：Tools 菜单下新增 3 个一级目录
- "解密工具1": 12 个 cipher (凯撒/培根/栅栏/猪圈/摩尔斯/xxencode/uuencode/jsfuck/jjencode/Quoted-printable/BrainFuck/BubbleBabble)
- "解密工具2" / "解密工具3": **占位**

**架构**（跟 v0.5-base-rot-decoders 一致）:
- 所有 runner 统一签名 `(text: str | None, file_path: str | None, **kwargs) -> DecodeResult`
- 算法基于 ``core/encoders/classical`` + ``core/encoders/classical_ext``
- 失败返回 ``DecodeResult(error=...)``，不抛
- GUI 走 registry.group="解密工具1" 自动挂到 Tools 顶级下
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from automisc.core.encoders.classical import (
    caesar_decrypt, rail_fence_decrypt, pigpen_decrypt,
)
from automisc.core.encoders import classical_ext


# === Result 数据类（跟 base_rot_decoders.py 复用同 schema）===

@dataclass
class DecodeResult:
    """cipher decoder 通用结果.

    Attributes:
        codec: 解码方式 (e.g. "caesar", "morse")
        input: 输入文本
        output_text: 解出的 ASCII (utf-8 decode, 失败用 'replace')
        output_bytes: 解出的原始 bytes（仅 uudecode/xxdecode/quoted-printable/brainfuck/bubblebabble 用）
        hint: 额外提示 (e.g. "shift=3", "morse word separator=/")
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


# === 输入读取 helper ===

def _read_input(
    text: str | None, file_path: str | None, codec_name: str
) -> str:
    """读取输入（text 优先，file_path 次之，bytes 模式自动读 bytes 后 decode 'latin-1'）."""
    if text is not None:
        return text
    if file_path is not None:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        # cipher 类几乎都是 text-based，UTF-8 with replace
        return p.read_text(errors="replace")
    raise ValueError(f"{codec_name}: 需要 text 或 file_path")


def _read_input_bytes(
    text: str | None, file_path: str | None, codec_name: str
) -> bytes:
    """读取输入为 bytes（uudecode/xxdecode/quoted-printable/brainfuck/bubblebabble 用）."""
    if text is not None:
        return text.encode("latin-1")
    if file_path is not None:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        return p.read_bytes()
    raise ValueError(f"{codec_name}: 需要 text 或 file_path")


def _make_text_runner(codec_name: str, decode_fn, output_to_bytes: bool = False):
    """通用 text-based runner.

    Args:
        codec_name: e.g. "caesar"
        decode_fn: function(s: str) -> str | bytes
        output_to_bytes: decode_fn 返回 bytes 时设 True
    """
    def runner(text=None, file_path=None, **kwargs):
        data = _read_input(text, file_path, codec_name)
        try:
            result = decode_fn(data)
        except (ValueError, FileNotFoundError) as e:
            return DecodeResult(codec=codec_name, input=data, error=str(e))
        if output_to_bytes:
            output_bytes = result
            output_text = result.decode("utf-8", errors="replace") if isinstance(result, (bytes, bytearray)) else str(result)
            return DecodeResult(
                codec=codec_name, input=data,
                output_text=output_text,
                output_bytes=bytes(output_bytes),
            )
        return DecodeResult(
            codec=codec_name, input=data,
            output_text=result if isinstance(result, str) else str(result),
        )
    runner.__name__ = f"run_{codec_name}"
    return runner


def _make_bytes_runner(codec_name: str, decode_fn):
    """bytes-based runner（uudecode/xxdecode/quoted-printable/brainfuck/bubblebabble 用）."""
    def runner(text=None, file_path=None, **kwargs):
        data = _read_input_bytes(text, file_path, codec_name)
        try:
            result = decode_fn(data)
        except (ValueError, FileNotFoundError) as e:
            # cipher input 在 bytes mode 下可能是 latin-1 字符串，需要双向兼容
            try:
                text_repr = data.decode("latin-1")
            except Exception:
                text_repr = repr(data[:100])
            return DecodeResult(codec=codec_name, input=text_repr, error=str(e))
        # 尝试 utf-8 decode (失败用 replace)
        try:
            output_text = result.decode("utf-8") if isinstance(result, (bytes, bytearray)) else str(result)
        except UnicodeDecodeError:
            output_text = result.decode("utf-8", errors="replace") if isinstance(result, (bytes, bytearray)) else str(result)
        return DecodeResult(
            codec=codec_name, input=text_repr if 'text_repr' in dir() else data.decode("latin-1", errors="replace"),
            output_text=output_text,
            output_bytes=bytes(result) if isinstance(result, (bytes, bytearray)) else b"",
        )
    runner.__name__ = f"run_{codec_name}"
    return runner


# === 凯撒 runner（带 --shift 参数，默认 3）===

def run_caesar(text=None, file_path=None, shift=3, **_):
    """凯撒解密. shift=None → 用默认 3."""
    data = _read_input(text, file_path, "caesar")
    # None / str → int
    if shift is None:
        s = 3
    else:
        try:
            s = int(shift)
        except (ValueError, TypeError):
            return DecodeResult(
                codec="caesar", input=data,
                error=f"shift must be int, got {shift!r}",
            )
    if s == 0:
        return DecodeResult(
            codec="caesar", input=data, output_text=data,
            hint="shift=0 → 无变化",
        )
    try:
        output = caesar_decrypt(data, s)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="caesar", input=data, error=str(e))
    return DecodeResult(
        codec="caesar", input=data,
        output_text=output,
        hint=f"shift={s}" + (" (默认)" if s == 3 else ""),
    )


# === 培根 runner（带 --variant {24,26}）===

def run_bacon(text=None, file_path=None, variant="24", **_):
    """培根解码. variant=None → '24' (I/J+U/V 合并)."""
    data = _read_input(text, file_path, "bacon")
    v = "24" if variant is None else str(variant)
    try:
        output = classical_ext.bacon_decode(data, v)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="bacon", input=data, error=str(e))
    return DecodeResult(
        codec="bacon", input=data,
        output_text=output,
        hint=f"variant={v}" + (" (默认 24字母 I/J+U/V 合并)" if v == "24" else " (26字母独立)"),
    )


# === 栅栏 runner（带 --rails N，默认 2）===

def run_rail_fence(text=None, file_path=None, rails=2, **_):
    """栅栏解码. rails=None → 2."""
    data = _read_input(text, file_path, "rail-fence")
    if rails is None:
        r = 2
    else:
        try:
            r = int(rails)
        except (ValueError, TypeError):
            return DecodeResult(
                codec="rail-fence", input=data,
                error=f"rails must be int, got {rails!r}",
            )
    if r < 2:
        return DecodeResult(
            codec="rail-fence", input=data,
            error=f"rails must be >= 2, got {r}",
        )
    try:
        output = rail_fence_decrypt(data, r)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="rail-fence", input=data, error=str(e))
    return DecodeResult(
        codec="rail-fence", input=data,
        output_text=output,
        hint=f"rails={r}" + (" (默认)" if r == 2 else ""),
    )


# === 猪圈 runner（带 --variant {unicode,simple}）===

def run_pigpen(text=None, file_path=None, variant="unicode", **_):
    """猪圈解码. variant=None → 'unicode'."""
    data = _read_input(text, file_path, "pigpen")
    v = "unicode" if variant is None else str(variant)
    if v == "simple":
        # 走老 classical.pigpen_decrypt（仅字母→符号映射反向）
        try:
            output = pigpen_decrypt(data)
        except Exception as e:
            return DecodeResult(codec="pigpen", input=data, error=str(e))
        return DecodeResult(
            codec="pigpen", input=data,
            output_text=output,
            hint="variant=simple (字母→符号映射反向, 仅兼容)",
        )
    if v != "unicode":
        return DecodeResult(
            codec="pigpen", input=data,
            error=f"variant must be 'unicode' or 'simple', got {v!r}",
        )
    try:
        output = classical_ext.pigpen_decode_v2(data, "unicode")
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="pigpen", input=data, error=str(e))
    return DecodeResult(
        codec="pigpen", input=data,
        output_text=output,
        hint="variant=unicode (⌜⌝⌞⌟/∴/∨ 等 14 字母 + X/V 反转)",
    )


# === 摩尔斯 runner ===

def run_morse(text=None, file_path=None, **_):
    data = _read_input(text, file_path, "morse")
    try:
        output = classical_ext.morse_decode(data)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="morse", input=data, error=str(e))
    return DecodeResult(
        codec="morse", input=data,
        output_text=output,
        hint="word sep=/  char sep=空格  (CTF 包裹 {} 自动去除)",
    )


# === xxencode runner (bytes-based) ===

def run_xxencode(text=None, file_path=None, **_):
    try:
        data = _read_input_bytes(text, file_path, "xxencode")
    except FileNotFoundError as e:
        return DecodeResult(codec="xxencode", input="", error=str(e))
    try:
        result = classical_ext.xxdecode(data.decode("latin-1", errors="replace"))
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="xxencode", input=data.decode("latin-1", errors="replace"), error=str(e))
    try:
        output_text = result.decode("utf-8")
    except UnicodeDecodeError:
        output_text = result.decode("utf-8", errors="replace")
    return DecodeResult(
        codec="xxencode",
        input=data.decode("latin-1", errors="replace"),
        output_text=output_text,
        output_bytes=result,
        hint=f"输出 {len(result)} bytes",
    )


# === uuencode runner (bytes-based) ===

def run_uuencode(text=None, file_path=None, **_):
    try:
        data = _read_input_bytes(text, file_path, "uuencode")
    except FileNotFoundError as e:
        return DecodeResult(codec="uuencode", input="", error=str(e))
    try:
        result = classical_ext.uudecode(data.decode("latin-1", errors="replace"))
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="uuencode", input=data.decode("latin-1", errors="replace"), error=str(e))
    try:
        output_text = result.decode("utf-8")
    except UnicodeDecodeError:
        output_text = result.decode("utf-8", errors="replace")
    return DecodeResult(
        codec="uuencode",
        input=data.decode("latin-1", errors="replace"),
        output_text=output_text,
        output_bytes=result,
        hint=f"输出 {len(result)} bytes",
    )


# === jsfuck runner ===

def run_jsfuck(text=None, file_path=None, **_):
    data = _read_input(text, file_path, "jsfuck")
    try:
        output = classical_ext.jsfuck_decode(data)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="jsfuck", input=data, error=str(e))
    # jsfuck 没匹配时 output 包含 "未识别" 提示 — 转 error
    if output.startswith("[jsfuck_decode]"):
        return DecodeResult(
            codec="jsfuck", input=data,
            error=output,
        )
    return DecodeResult(
        codec="jsfuck", input=data,
        output_text=output,
        hint="纯 Python 提取 (支持 String.fromCharCode/return/alert 字面量)",
    )


# === jjencode runner ===

def run_jjencode(text=None, file_path=None, **_):
    data = _read_input(text, file_path, "jjencode")
    try:
        output = classical_ext.jjencode_decode(data)
    except (ValueError, TypeError) as e:
        return DecodeResult(codec="jjencode", input=data, error=str(e))
    if output.startswith("[jjencode_decode]"):
        return DecodeResult(
            codec="jjencode", input=data,
            error=output,
        )
    return DecodeResult(
        codec="jjencode", input=data,
        output_text=output,
        hint="纯 Python 提取 (支持末尾 String.fromCharCode/return/alert 字面量)",
    )


# === Quoted-printable runner (bytes-based) ===

def run_quoted_printable(text=None, file_path=None, **_):
    try:
        data = _read_input_bytes(text, file_path, "quoted-printable")
    except FileNotFoundError as e:
        return DecodeResult(codec="quoted-printable", input="", error=str(e))
    try:
        result = classical_ext.quoted_printable_decode(data.decode("latin-1", errors="replace"))
    except (ValueError, TypeError) as e:
        return DecodeResult(
            codec="quoted-printable",
            input=data.decode("latin-1", errors="replace"),
            error=str(e),
        )
    try:
        output_text = result.decode("utf-8")
    except UnicodeDecodeError:
        output_text = result.decode("utf-8", errors="replace")
    return DecodeResult(
        codec="quoted-printable",
        input=data.decode("latin-1", errors="replace"),
        output_text=output_text,
        output_bytes=result,
        hint=f"输出 {len(result)} bytes (=XX 转义还原)",
    )


# === BrainFuck runner (bytes-based) ===

def run_brainfuck(text=None, file_path=None, **_):
    try:
        data = _read_input_bytes(text, file_path, "brainfuck")
    except FileNotFoundError as e:
        return DecodeResult(codec="brainfuck", input="", error=str(e))
    try:
        result = classical_ext.brainfuck_eval(data.decode("latin-1", errors="replace"))
    except (ValueError, TypeError) as e:
        return DecodeResult(
            codec="brainfuck",
            input=data.decode("latin-1", errors="replace"),
            error=str(e),
        )
    try:
        output_text = result.decode("utf-8")
    except UnicodeDecodeError:
        output_text = result.decode("utf-8", errors="replace")
    return DecodeResult(
        codec="brainfuck",
        input=data.decode("latin-1", errors="replace"),
        output_text=output_text,
        output_bytes=result,
        hint=f"BF 解释器跑完, 输出 {len(result)} bytes",
    )


# === BubbleBabble runner (bytes-based) ===

def run_bubblebabble(text=None, file_path=None, **_):
    try:
        data = _read_input_bytes(text, file_path, "bubblebabble")
    except FileNotFoundError as e:
        return DecodeResult(codec="bubblebabble", input="", error=str(e))
    try:
        result = classical_ext.bubblebabble_decode(data.decode("latin-1", errors="replace"))
    except (ValueError, TypeError) as e:
        return DecodeResult(
            codec="bubblebabble",
            input=data.decode("latin-1", errors="replace"),
            error=str(e),
        )
    try:
        output_text = result.decode("utf-8")
    except UnicodeDecodeError:
        output_text = result.decode("utf-8", errors="replace")
    return DecodeResult(
        codec="bubblebabble",
        input=data.decode("latin-1", errors="replace"),
        output_text=output_text,
        output_bytes=result,
        hint=f"输出 {len(result)} bytes (PGP fingerprint 风格)",
    )


# === 占位 runner（解密工具2/3） ===

def run_placeholder(text=None, file_path=None, group: str = "", **kwargs):
    """占位 runner（解密工具2/3）— 跑就返回 TBD 提示."""
    return DecodeResult(
        codec=f"placeholder-{group}",
        input=text or file_path or "",
        error=f"'{group}' 目录尚未实现。等待 Owner 后续定义具体 cipher。",
    )


# === 注册 14 个 spec (12 cipher + 2 占位) ===

def _register_all() -> None:
    from automisc.core.decoders.registry import DecoderSpec, register_decoder

    CIPHER_DECODERS = [
        # name, display, runner, description
        ("caesar",         "🔤 凯撒解密",         run_caesar,
         "凯撒密码解密 (默认 shift=3, --shift N 可调)"),
        ("bacon",          "🥓 培根解密",         run_bacon,
         "培根密码解码 (A/B 二值 → 5-bit 字母, 默认 24 字母版, --variant {24,26})"),
        ("rail-fence",     "🚧 栅栏解密",         run_rail_fence,
         "栅栏密码解密 (默认 rails=2, --rails N 可调)"),
        ("pigpen",         "🐖 猪圈解密",         run_pigpen,
         "猪圈密码解密 (unicode 网格符号, --variant {unicode,simple})"),
        ("morse",          "📡 摩尔斯解密",       run_morse,
         "摩尔斯电码解码 (ITU 标准 + 标点扩展, 词间 / 或双空格)"),
        ("xxencode",       "✖ xxencode 解密",    run_xxencode,
         "XXencode 解码 (CTF .xx 文件, +- 字符集 + 6-bit)"),
        ("uuencode",       "📦 uuencode 解密",    run_uuencode,
         "UUencode 解码 (Unix-to-Unix encoding)"),
        ("jsfuck",         "🤯 JSFuck 解密",      run_jsfuck,
         "JSFuck 纯 Python 提取 (支持 String.fromCharCode/return/alert 字面量)"),
        ("jjencode",       "🌀 JJEncode 解密",    run_jjencode,
         "JJEncode 纯 Python 提取 (支持末尾 String.fromCharCode/return/alert 字面量)"),
        ("quoted-printable", "🆎 Quoted-printable 解密", run_quoted_printable,
         "Quoted-Printable =XX 转义还原 (RFC 2045)"),
        ("brainfuck",      "🧠 BrainFuck 解密",   run_brainfuck,
         "BrainFuck 8 指令解释器 (><+-.,[])"),
        ("bubblebabble",   "🫧 BubbleBabble 解密", run_bubblebabble,
         "Bubble Babble 校验和编码解码 (PGP fingerprint 风格)"),
    ]

    for name, display, runner, desc in CIPHER_DECODERS:
        register_decoder(
            DecoderSpec(
                name=name,
                display=display,
                category="cipher",  # 兜底 category
                group="解密工具1",
                cli_cmd=f"decode {name}",
                run=runner,
                description=desc,
                text_only=True,  # 12 cipher 全是 text input (e.g. "KHOOR" "..." "⌜⌜⌝")
            )
        )

    # 占位：解密工具2 + 解密工具3
    for group in ("解密工具2", "解密工具3"):
        register_decoder(
            DecoderSpec(
                name=f"placeholder-{group}",
                display="（占位 — TBD）",
                category="placeholder",
                group=group,
                cli_cmd=f"decode placeholder-{group}",
                run=lambda **kw: run_placeholder(group=group, **kw),
                description=f"'{group}' 目录尚未实现，等待 Owner 定义具体 cipher。",
                text_only=True,  # 占位也是 text-only (跑就立刻 TBD 提示)
            )
        )


_register_all()


__all__ = [
    "DecodeResult",
    "run_caesar",
    "run_bacon",
    "run_rail_fence",
    "run_pigpen",
    "run_morse",
    "run_xxencode",
    "run_uuencode",
    "run_jsfuck",
    "run_jjencode",
    "run_quoted_printable",
    "run_brainfuck",
    "run_bubblebabble",
    "run_placeholder",
]
