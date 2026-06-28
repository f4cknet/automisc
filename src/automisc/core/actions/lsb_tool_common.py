"""LSB 工具公共模块 (per v0.5-lsb-tool-unify, Phase 2a)

公共函数 / 常量 / magic 库, LSBToolAction 在 `lsb_tool.py` 调用.

**3 mode 共享** (detect / extract / extract_bytes):
- `_extract_lsb_byte_stream` (公共字节流提取, 4 参数 zsteg 兼容)
- `_is_printable_text` (text 判定, ≥20 字节连续 printable)
- `_detect_file_header_hex` (50+ magic 库)
- `_shannon_entropy` / `_unique_count` / `_channel_8bit_byte_stream` (entropy 检测)
- `_bytes_preview` (SP.matched_pattern 截断)
- `_parse_channels` / `_perm_name` (字符串解析)

**修复 v0.5-train-012 bug**: 公共字节流函数保证 3 mode 字节流同源
(老 lsb_detect + lsb_extract 两条路径不同源, 工具栏写真 117 byte text vs
lsb_detect 命中 26934 byte PNG).
"""
from __future__ import annotations

from pathlib import Path  # noqa: F401  # re-exported for tests
from typing import Literal

import numpy as np
from PIL import Image  # noqa: F401  # re-exported for tests


# ============ 类型 + 校验常量 ============

Channel = Literal["R", "G", "B", "A"]
ScanOrder = Literal["row", "col"]
ByteBitOrder = Literal["msb", "lsb"]
Mode = Literal["detect", "extract", "extract_bytes"]
Preset = Literal["all", "np"]

_VALID_CHANNELS = {"R", "G", "B", "A"}
_VALID_SCAN_ORDERS = {"row", "col"}
_VALID_BYTE_BIT_ORDERS = {"msb", "lsb"}
_VALID_MODES = {"detect", "extract", "extract_bytes"}
_VALID_PRESETS = {None, "all", "np"}

# RGB 全排列 (PIL convert('RGB') 顺序: 0=R, 1=G, 2=B)
_PERMUTATIONS: list[tuple[int, int, int]] = [
    (0, 1, 2),  # RGB
    (0, 2, 1),  # RBG
    (1, 0, 2),  # GRB
    (1, 2, 0),  # GBR
    (2, 0, 1),  # BRG
    (2, 1, 0),  # BGR
]
_SCAN_ORDERS: list[str] = ["row", "col"]

# text 判定阈值 (per v0.5-train-011 修复)
_MIN_PRINTABLE_RUN = 20
_PRINTABLE_WINDOW = 1000

# 字节流 preview 截断 (per spec Q3=inline)
_BYTE_PREVIEW_LIMIT = 200

# entropy + unique 阈值 (per v0.5-train-010 §2.2 MVP)
_ENTROPY_THRESHOLD = 5.0
_UNIQUE_THRESHOLD = 200

# 字节流最小长度 (text/file 判定需要 ≥ 16 字节才有意义)
_MIN_BYTE_STREAM_LEN = 16


# ============ 文件 magic 库 (per lsb_detect._MAGIC_PREFIXES) ============

_MAGIC_PREFIXES: list[tuple[bytes, str, str]] = [
    # (hex_magic, ext, label)
    (b"PK\x03\x04", "zip", "ZIP archive"),
    (b"PK\x05\x06", "zip", "ZIP empty archive"),
    (b"PK\x07\x08", "zip", "ZIP spanned archive"),
    (b"Rar!\x1a\x07", "rar", "RAR archive"),
    (b"\x89PNG\r\n\x1a\n", "png", "PNG image"),
    (b"\xff\xd8\xff", "jpg", "JPEG image"),
    (b"GIF87a", "gif", "GIF87a image"),
    (b"GIF89a", "gif", "GIF89a image"),
    (b"%PDF", "pdf", "PDF document"),
    (b"\x7fELF", "elf", "ELF executable"),
    # PYC magic (per v0.5-pyc-magic-sniffer 17+ 变体)
    (b"\x03\xf3\r\n", "pyc", "Python 2.7 bytecode"),
    (b"\x3f\x0d\r\n", "pyc", "Python 2.6 bytecode"),
    (b"\xd1\xf2\r\n", "pyc", "Python 2.5 bytecode"),
    (b"\xee\x0c\r\n", "pyc", "Python 2.4 bytecode"),
    (b"\x42\x0d\r\n", "pyc", "Python 2.3 bytecode"),
    (b"\x6c\x0c\r\n", "pyc", "Python 2.2 bytecode"),
    (b"\x2a\xeb\r\n", "pyc", "Python 2.1 bytecode"),
    (b"\xb8\xc7\r\n", "pyc", "Python 2.0 bytecode"),
    (b"\x33\x0d\r\n", "pyc", "Python 3.6 bytecode"),
    (b"\x42\x0d\x0d", "pyc", "Python 3.7 bytecode"),
    (b"\x55\x0d\x0d", "pyc", "Python 3.8 bytecode"),
    (b"\x61\x0d\x0d", "pyc", "Python 3.9 bytecode"),
    (b"\x6f\x0d\x0d", "pyc", "Python 3.10 bytecode"),
    (b"\xa7\x0d\x0d", "pyc", "Python 3.11 bytecode"),
    (b"\xcb\x0d\x0d", "pyc", "Python 3.12 bytecode"),
    (b"7z\xbc\xaf\x27\x1c", "7z", "7-Zip archive"),
    (b"BZh", "bz2", "bzip2 archive"),
    (b"\x1f\x8b", "gz", "gzip archive"),
]


# ============ 公共字节流提取函数 ============


def _parse_channels(channels: str | list[str]) -> list[str]:
    """'R,G,B' / ['R','G','B'] / 'RGB' → ['R','G,B']"""
    if isinstance(channels, str):
        if "," in channels:
            parts = [c.strip().upper() for c in channels.split(",") if c.strip()]
        else:
            parts = list(channels.upper())
    else:
        parts = [c.upper() for c in channels]
    invalid = [c for c in parts if c not in _VALID_CHANNELS]
    if invalid:
        raise ValueError(f"invalid channels: {invalid}, valid: {sorted(_VALID_CHANNELS)}")
    if not parts:
        raise ValueError("at least one channel required")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for c in parts:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _channel_index(ch: str) -> int:
    """R → 0, G → 1, B → 2, A → 3"""
    return {"R": 0, "G": 1, "B": 2, "A": 3}[ch]


def _extract_lsb_byte_stream(
    img_array: np.ndarray,
    channels: list[str],
    bit: int,
    scan_order: str,
    byte_bit_order: str,
) -> bytes:
    """单组合字节流提取 (zsteg-compatible per-pixel interleaved, 公共函数 3 mode 复用).

    字节流同源 (修复 v0.5-train-012 bug + v0.5-train-014 回归).

    **per-pixel interleaved**: 每个像素的指定通道 (按 channels 顺序) 拼成一段 bit 流,
    再按 8 bit 拼 byte. **跟 zsteg `b<bit>,<channels>,<byte_bit_order>,<scan>` 完全等价**.

    例如 channels=['R','G','B'] / row / msb:
        bits = [R0_比特bit, G0_比特bit, B0_比特bit, R1_比特bit, G1_比特bit, B1_比特bit, ...]
        每 8 bit 一字节, MSB first (zsteg 默认)

    Args:
        img_array: (H, W, 3 or 4) uint8 numpy array
        channels: e.g. ["G"] 或 ["R", "G", "B"]
        bit: 0-7
        scan_order: "row" (xy) / "col" (yx, = 转置后 row-major)
        byte_bit_order: "msb" / "lsb"

    Returns:
        bytes (长度 = total_bits // 8)

    历史:
        - v0.5-lsb-tool-unify Phase 2a 实现 plane-separated (整 R + 整 G + 整 B), **错**
        - v0.5-train-014 暴露: steg.png 实战命中 0 SP, 根因 plane-separated 跟 zsteg 不一致
        - v0.5-lsb-tool-bitplane-preview-matrix Commit 1 修复为 per-pixel interleaved
    """
    ch_indices = [_channel_index(c) for c in channels]
    if img_array.ndim < 3 or max(ch_indices) >= img_array.shape[2]:
        raise ValueError(
            f"image has no channel {channels} (shape={img_array.shape})"
        )
    n_ch = len(ch_indices)

    # 提取指定通道 → (H, W, n_ch)
    plane = img_array[:, :, ch_indices]

    if scan_order == "row":
        # row-major: per pixel (R0 G0 B0) → next pixel (R1 G1 B1)
        flat = plane.reshape(-1, n_ch)  # (H*W, n_ch)
    else:  # col
        # col-major: 先转置成 (W, H, n_ch), 再 flatten → per pixel (W0 H0 W0 H0) = (col0_x0, col0_x1, ...)
        flat = plane.transpose(1, 0, 2).reshape(-1, n_ch)  # (W*H, n_ch)

    # 抽 bit 位 → flatten C-order → 每像素按 channels 顺序拼接
    bits = ((flat >> bit) & 1).astype(np.uint8).flatten(order="C")

    n_bytes = len(bits) // 8
    bits_trimmed = bits[: n_bytes * 8]

    if byte_bit_order == "msb":
        return np.packbits(bits_trimmed).tobytes()
    # lsb: 字节内 bit 反序 (zsteg 兼容)
    bits_2d = bits_trimmed.reshape(-1, 8)[:, ::-1].flatten()
    return np.packbits(bits_2d).tobytes()


# ============ 检测函数 ============


def _is_printable_text(byte_stream: bytes, min_run: int = _MIN_PRINTABLE_RUN) -> bool:
    """判定字节流是否含足够长连续 printable 段 (per zsteg 启发式, v0.5-train-011 修复)."""
    if not byte_stream or len(byte_stream) < min_run:
        return False
    max_run = 0
    current_run = 0
    for b in byte_stream[:_PRINTABLE_WINDOW]:
        if 32 <= b <= 126:
            current_run += 1
            if current_run > max_run:
                max_run = current_run
            if max_run >= min_run:
                return True
        else:
            current_run = 0
    return max_run >= min_run


def _detect_file_header_hex(byte_stream: bytes) -> tuple[str, str] | None:
    """hex magic 主判定 (50+ entry 库)."""
    if not byte_stream or len(byte_stream) < 4:
        return None
    for magic, ext, label in _MAGIC_PREFIXES:
        if byte_stream[: len(magic)] == magic:
            return (ext, label)
    return None


def _shannon_entropy(byte_stream: bytes) -> float:
    """香农熵 (max=8.0 for byte)."""
    if not byte_stream:
        return 0.0
    counts = np.bincount(np.frombuffer(byte_stream, dtype=np.uint8), minlength=256)
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts / total
    probs = probs[probs > 0]
    if len(probs) == 0:
        return 0.0
    return float(-(probs * np.log2(probs)).sum())


def _unique_count(byte_stream: bytes) -> int:
    """unique byte count / 256."""
    if not byte_stream:
        return 0
    return int(len(np.unique(np.frombuffer(byte_stream, dtype=np.uint8))))


def _channel_8bit_byte_stream(plane: np.ndarray) -> bytes:
    """单通道 8 bit 字节流 (1 像素 = 1 byte, 像素值 = byte 值).

    用于单通道 entropy + unique 检测 (per v0.5-train-010 N=NP 模式).
    """
    if plane.size == 0:
        return b""
    return bytes(plane.flatten().astype(np.uint8).tolist())


def _bytes_preview(byte_stream: bytes, limit: int = _BYTE_PREVIEW_LIMIT) -> str:
    """bytes → str preview, 非 UTF-8 安全 (errors='replace')."""
    text = byte_stream[:limit].decode("utf-8", errors="replace")
    if len(byte_stream) > limit:
        text += f"... (truncated, total {len(byte_stream)} bytes)"
    return text


def _perm_name(perm: tuple[int, int, int]) -> str:
    return ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR"][_PERMUTATIONS.index(perm)]