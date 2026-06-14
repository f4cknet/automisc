"""base64 -> 图片解码器（v0.5+ standalone 模块）

**用途**：CTF Misc 常见 `data:image/jpg;base64,...` 头（直接转），或纯 base64（尝试加 `data:image/jpg` 头 + file 识别）。

**决策树**（per Owner 规格 · 2026-06-14）:

```
输入: 文件路径
  1. 读全文
  2. 预处理: 剥 data URL 头 (data:image/(jpeg|jpg|png|gif|webp|bmp);base64,) -> 记 mime
  3. base64 decode (validate=True 严格) -> raw bytes
     失败 -> Base64ImageError("不是有效 base64")
  4. 写 raw 到 input 同目录, 命名 `<stem>__base64.<ext>` (v0.5-output-samedir)
  5. 用 `file` 命令检测 mime
     - image/* -> 成功 (返回 path)
     - 非 image -> Base64ImageError("转图片失败, file 检测: <type>")
```

**v0.5+ 接入 DAG**：暂不接（per Owner "先单独模块, 后面再决定"）。

**v0.5-output-samedir 改造 (2026-06-14)**:
- 输出文件从 /tmp/automisc_b64_xxxxxx.<ext> 改成 <input_dir>/<input_stem>__base64.<ext>
- 原因: Owner "不论是 foremost 还是 base64 转图片, 都把输出文件保存到输入文件的相同目录下"

macOS 依赖：`file`（系统自带，/usr/bin/file）。
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from automisc.core.utils.output_path import output_path_for


# 1. data URL 头正则 (per RFC 2397)
_DATA_URL_RE = re.compile(
    r"^\s*data:(?P<mime>image/(?:jpeg|jpg|png|gif|webp|bmp))(?P<extra>;[^,]*)?;base64,(?P<data>.+?)\s*$",
    re.DOTALL,
)


class Base64ImageError(Exception):
    """base64 -> 图片解码失败."""

    pass


@dataclass
class Base64ImageResult:
    """成功解码结果.

    Attributes:
        output_path: 解出的图片临时文件路径
        detected_mime: file 命令检测的 mime (e.g. "PNG image data, 133 x 133")
        source_mime_hint: data URL 头里的 mime (None 表示文件无头)
        raw_size: 解出的字节数
        kept_output: True = caller 决定保留 (CLI 不删); False = CLI 默认删
    """

    output_path: str
    detected_mime: str
    source_mime_hint: str | None
    raw_size: int
    kept_output: bool = False


def _strip_data_url(text: str) -> tuple[str, str | None]:
    """剥 data URL 头.

    Returns:
        (pure_base64_str, mime_hint) — mime 来自 data: 头, None 表示无
    """
    m = _DATA_URL_RE.match(text)
    if m:
        return m.group("data"), m.group("mime")
    return text, None


def _try_strict_base64_decode(s: str) -> bytes:
    """base64 decode (validate=True 严格模式, 长度必须是 4 倍数)."""
    try:
        return base64.b64decode(s, validate=True)
    except Exception as e:
        raise Base64ImageError(f"不是有效 base64: {type(e).__name__}: {e}")


def _strip_padding(s: str) -> str:
    """补齐 base64 长度到 4 倍数 (避免 validate=True 抛错)."""
    return s + "=" * (-len(s) % 4)


def _try_with_fallback_headers(raw: str) -> tuple[bytes, str] | None:
    """无 data URL 头时, 尝试加常见 image/* 头 + 严格 decode.

    Returns:
        (decoded_bytes, mime) — 第一个严格 decode 成功的; 全失败 -> None
    """
    fallback_mime_pairs = (
        ("data:image/jpeg;base64,", "image/jpeg"),
        ("data:image/jpg;base64,", "image/jpg"),
        ("data:image/png;base64,", "image/png"),
        ("data:image/gif;base64,", "image/gif"),
        ("data:image/webp;base64,", "image/webp"),
        ("data:image/bmp;base64,", "image/bmp"),
    )
    # 1. 试加每个头 (有 mime hint)
    for header, mime in fallback_mime_pairs:
        full = header + raw
        try:
            decoded = base64.b64decode(full, validate=True)
            return decoded, mime
        except Exception:
            continue
    # 2. 试直接 decode 纯 base64 (无 mime hint — 默认按 image/png 处理)
    try:
        decoded = base64.b64decode(_strip_padding(raw), validate=True)
        return decoded, "image/png"
    except Exception:
        return None


def _file_detect(path: str) -> str:
    """`file --brief` 检测文件 mime. 失败返回空字符串."""
    file_bin = shutil.which("file")
    if not file_bin:
        return ""
    try:
        r = subprocess.run(
            [file_bin, "--brief", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _is_image_mime(detected: str) -> bool:
    """file 输出含 'image' (PNG/JPEG/BMP/GIF/WebP/... 都被识别为 'image')."""
    return "image" in detected.lower() if detected else False


def decode_file_to_image(
    file_path: str,
    *,
    output_dir: str | None = None,
    keep_output: bool = False,
) -> Base64ImageResult:
    """主入口: 文件 -> 图片.

    Args:
        file_path: 输入文件路径 (含 base64)
        output_dir: 输出目录 (None = tempfile 默认 /tmp)
        keep_output: True = 保留 output 文件 (caller 决定)

    Returns:
        Base64ImageResult (成功)

    Raises:
        Base64ImageError: 不是 base64 / 不是图片
        FileNotFoundError: 输入文件不存在
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"input not found: {file_path}")

    text = p.read_text(errors="replace")

    # Step 1+2: 剥 data URL 头
    pure_b64, source_mime = _strip_data_url(text)
    has_data_url_header = source_mime is not None

    # Step 3: base64 decode
    if has_data_url_header:
        # 有 data URL 头: 严格 decode (validate=True)
        pure_b64 = _strip_padding(pure_b64)
        raw = _try_strict_base64_decode(pure_b64)
    else:
        # 无 data URL 头: 尝试加常见头 + 严格 decode
        result = _try_with_fallback_headers(pure_b64)
        if result is None:
            raise Base64ImageError(
                f"不是有效 base64 (无 data: 头, 加常见 image/* 头也失败)"
            )
        raw, source_mime = result  # 用 fallback 推断的 mime

    # Step 4: 写 output (v0.5-output-samedir: 与 input 同目录, 命名 <stem>__base64.<ext>)
    suffix_map = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg",
        "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "image/bmp": ".bmp",
    }
    suffix = suffix_map.get(source_mime, ".png")  # fallback .png 让 file 有 hint

    if output_dir:
        # caller 显式指定了 output_dir (向后兼容 CLI --out-dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        out_path = Path(output_dir) / f"{p.stem}__base64{suffix}"
    else:
        # 默认: 与 input 同目录 (v0.5-output-samedir)
        out_path = output_path_for(p, suffix=suffix, purpose="base64")
    out_path.write_bytes(raw)

    # Step 5: `file` 命令检测
    detected = _file_detect(str(out_path))
    if not _is_image_mime(detected):
        # 不是图片
        out_path.unlink(missing_ok=True)
        raise Base64ImageError(
            f"转图片失败, file 检测: {detected or '(empty / no file command)'}"
        )

    return Base64ImageResult(
        output_path=str(out_path),
        detected_mime=detected,
        source_mime_hint=source_mime,
        raw_size=len(raw),
        kept_output=keep_output,
    )


# ---------- v0.5-decoder-menu: 注册到 registry ----------
def _register() -> None:
    from automisc.core.decoders.registry import DecoderSpec, register_decoder
    register_decoder(
        DecoderSpec(
            name="base64-image",
            display="🔓 Base64 → 图片",
            category="decode",
            cli_cmd="decode base64-image",
            run=decode_file_to_image,
            description="base64 -> 图片（自动识别 data: 头 + file 验证）",
        )
    )


_register()


__all__ = [
    "Base64ImageError",
    "Base64ImageResult",
    "decode_file_to_image",
]
