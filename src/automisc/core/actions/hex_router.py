"""Action: 长 hex 串智能路由 (v0.5-hex-router)

**Owner 触发** (2026-06-14 13:39):
> 我发现一个问题, 你在窗口中打印的是一部分 hex, 我误以为是全部的 hex 了.
> 我用 vscode 打开 meihuai.jpg, 发现最后一行是非常长的一串 hex,
> 因为太长, 导致我复制该行的时候用了非常多的时间, 这在争分夺秒的 ctf 赛场上是不可接受的.
> 既然发现这么长的 hex 在出现在 strings 的结果中, 那必然是非常重要的线索,
> 所以你应该按 auto_run 逻辑继续走下去, 这串 hex 的背后到底是什么, 是图片、压缩文件还是纯 ASCII?
> 因为 35000+ 会撑爆 window, 你只能截断开头的一部分打印, 所以我无法得到全部的 hex,
> 所以这一步必须是由 auto_run 往下走.
> 如果是非常短, 比如低于 200 字符的 hex, 那你打印给我, 我复制到 input 中, 然后点击 hex->ascii 这没问题.

**职责**: 接收 hex 字符串 (e.g. "89504e470d0a1a0a...") -> 探测 magic number -> 路由到对应文件类型

**算法**:
1. hex 字符串 -> bytes.fromhex() -> raw bytes
2. 看前 4-16 bytes magic number:
   - `89504e47` -> PNG (image)
   - `ffd8ffe0/ffd8ffe1` -> JPEG (image)
   - `47494638` -> GIF (image)
   - `504b0304` -> ZIP (archive)
   - `526172211a07` -> RAR (archive)
   - `377abcaf271c` -> 7z (archive)
   - `1f8b` -> gzip (archive)
   - `425a68` -> bzip2 (archive)
   - `7f454c46` -> ELF (binary)
   - `4d5a` -> PE/exe (binary)
3. 写 raw bytes 到 /tmp/automisc_<magic>_<rand>.<ext>
4. 触发对应后续 (zbar / unzip / unrar / 7z / file)
5. 返回 HexRouterResult (magic, ext, output_path, decoded / extracted info)

**触发条件**:
- strings 命中 hex 类别
- hex 长度 > 200 字符 (per Owner "低于 200 字符的 hex, 你打印给我, 我自己处理")
- auto-run 看到这种"超长 hex" 不打印到 GUI (避免 35000 字符撑爆窗口), 直接 trigger 本 action

macOS 依赖: zbarimg / unzip / unrar / 7z (任一 magic 命中时调)
"""
from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from automisc.core.utils.output_path import text_based_output_path


# v0.5-hex-router (per Owner 13:39): 短于此长度仍打印到 GUI (让人手抄走 hex-ascii 流程)
# 长于此长度不再打印 -> auto-run trigger 本 action
HEX_AUTO_ROUTER_MIN_LEN: Final[int] = 200


# Magic number -> (ext, type, follow-up 描述)
# 4 bytes magic 用 startswith 匹配
_MAGIC_TABLE: Final[list[tuple[bytes, str, str, str]]] = [
    # (magic_bytes, ext, type, follow_up)
    (b"\x89PNG\r\n\x1a\n", "png", "image", "zbarimg 扫 QR / barcode"),
    (b"\xff\xd8\xff", "jpg", "image", "zbarimg 扫 QR / barcode"),
    (b"GIF87a", "gif", "image", "zbarimg 扫 QR / barcode"),
    (b"GIF89a", "gif", "image", "zbarimg 扫 QR / barcode"),
    (b"PK\x03\x04", "zip", "archive", "unzip 提取"),
    (b"PK\x05\x06", "zip", "archive", "unzip 提取 (空 zip)"),
    (b"PK\x07\x08", "zip", "archive", "unzip 提取 (spanned)"),
    (b"Rar!\x1a\x07\x00", "rar", "archive", "unrar / unar 提取"),
    (b"Rar!\x1a\x07\x01\x00", "rar5", "archive", "unrar 5+ 提取"),
    (b"7z\xbc\xaf\x27\x1c", "7z", "archive", "7z x 提取"),
    (b"\x1f\x8b", "gz", "archive", "gunzip 解压"),
    (b"BZh", "bz2", "archive", "bunzip2 解压"),
    (b"\x7fELF", "elf", "binary", "file 探更多, 或 readelf"),
    (b"MZ", "exe", "binary", "file 探更多, 或 strings"),
    (b"BM", "bmp", "image", "zbarimg 扫 QR (bmp 不常见)"),
    (b"RIFF", "riff", "binary", "RIFF container (wav/avi/webp)"),
]


class HexRouterError(Exception):
    """hex 路由失败."""

    pass


@dataclass
class HexRouterResult:
    """hex 智能路由结果.

    Attributes:
        hex_input_len: 原始 hex 字符串长度 (chars)
        raw_size: 解 hex 后 raw bytes 长度
        magic: 命中的 magic 描述 (e.g. "PNG image")
        ext: 输出文件后缀 (e.g. ".png")
        file_type: image / archive / binary / unknown
        output_path: 写入的 raw 文件路径
        follow_up: 后续可走的命令描述
        follow_up_stdout: follow-up 工具的 stdout (None = 跳过)
        follow_up_stderr: follow-up 工具的 stderr
    """

    hex_input_len: int
    raw_size: int
    magic: str
    ext: str
    file_type: str
    output_path: str
    follow_up: str
    follow_up_stdout: str | None = None
    follow_up_stderr: str | None = None


# hex 字符: 0-9 a-f A-F
_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Fa-f]+$")


def is_long_hex_text(text: str, min_len: int = HEX_AUTO_ROUTER_MIN_LEN) -> bool:
    """判断 text 是不是"超长 hex 串" 触发 auto-router.

    Args:
        text: 任意文本
        min_len: 触发阈值 (默认 200 chars per Owner 13:39)

    Returns:
        True = 长度 >= min_len + 全 hex 字符 + 偶数长度 (避免 0x 前缀等干扰)
    """
    text = text.strip()
    if len(text) < min_len:
        return False
    # 必须是偶数长度 (hex chars 必须配对)
    if len(text) % 2 != 0:
        return False
    if not _HEX_RE.match(text):
        return False
    return True


def detect_magic(raw: bytes) -> tuple[str, str, str, str]:
    """从 raw bytes 探测 magic number.

    Returns:
        (magic_label, ext, file_type, follow_up)
        没命中 -> ("unknown", ".bin", "unknown", "file 探更多")
    """
    for magic_bytes, ext, file_type, follow_up in _MAGIC_TABLE:
        if raw.startswith(magic_bytes):
            magic_label = f"{file_type} ({magic_bytes[:8].hex()})"
            return magic_label, ext, file_type, follow_up
    return "unknown", ".bin", "unknown", "file 探更多"


def _run_zbar(p: Path) -> tuple[str, str]:
    """调 zbarimg 扫图, 返回 (stdout, stderr)."""
    zbar = shutil.which("zbarimg")
    if not zbar:
        return "", "zbarimg 未装 (brew install zbar)"
    try:
        r = subprocess.run(
            [zbar, "--quiet", "--raw", str(p)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.stdout.strip(), r.stderr.strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return "", f"zbarimg {type(e).__name__}: {e}"


def _run_unzip(p: Path) -> tuple[str, str]:
    """unzip 提取, 返回 (stdout, stderr)."""
    unzip = shutil.which("unzip")
    if not unzip:
        return "", "unzip 未装"
    try:
        # 提取到 /tmp/<zipstem>_extracted_<ts>/
        extract_dir = p.parent / f"{p.stem}_extracted_{int(time.time())}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [unzip, "-o", str(p), "-d", str(extract_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return (
            f"extracted to {extract_dir}\n{r.stdout.strip()}",
            r.stderr.strip(),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return "", f"unzip {type(e).__name__}: {e}"


def route_hex_to_file(
    hex_text: str,
    out_dir: str | None = None,
    follow_up: bool = True,
) -> HexRouterResult:
    """主入口: hex 字符串 -> 写文件 + (可选) follow-up 工具.

    Args:
        hex_text: hex 字符串 (e.g. "89504e47...")
        out_dir: 输出目录 (None = /tmp/automisc_text_outputs/ via helper)
        follow_up: True = 自动调 zbar / unzip 等后续工具

    Returns:
        HexRouterResult (含 follow_up_stdout / stderr)

    Raises:
        HexRouterError: hex 解析失败 / 写文件失败
    """
    hex_text = hex_text.strip()
    if not is_long_hex_text(hex_text):
        raise HexRouterError(
            f"不是合法 hex 串 (len={len(hex_text)}, "
            f"min={HEX_AUTO_ROUTER_MIN_LEN}, must be even-length 0-9a-f)"
        )

    # 解 hex
    try:
        raw = bytes.fromhex(hex_text)
    except ValueError as e:
        raise HexRouterError(f"hex 解码失败: {e}")

    # 探测 magic
    magic_label, ext, file_type, follow_up_desc = detect_magic(raw)

    # 写 /tmp/<purpose>_<rand>.<ext>
    out_path = text_based_output_path(
        suffix=f".{ext}", purpose=f"hex_router_{file_type}"
    )
    out_path.write_bytes(raw)

    # 可选: 跑 follow-up 工具
    fu_stdout = None
    fu_stderr = None
    if follow_up:
        if file_type == "image":
            fu_stdout, fu_stderr = _run_zbar(out_path)
        elif file_type == "archive" and ext in ("zip",):
            fu_stdout, fu_stderr = _run_unzip(out_path)
        # 其他 archive 类型 (rar/7z/gz/bz2) 等 v0.5+ 实施 unrar/7z/gunzip

    return HexRouterResult(
        hex_input_len=len(hex_text),
        raw_size=len(raw),
        magic=magic_label,
        ext=ext,
        file_type=file_type,
        output_path=str(out_path),
        follow_up=follow_up_desc,
        follow_up_stdout=fu_stdout,
        follow_up_stderr=fu_stderr,
    )


__all__ = [
    "HEX_AUTO_ROUTER_MIN_LEN",
    "HexRouterError",
    "HexRouterResult",
    "detect_magic",
    "is_long_hex_text",
    "route_hex_to_file",
]
