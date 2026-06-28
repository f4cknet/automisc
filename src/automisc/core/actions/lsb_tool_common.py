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

_VALID_CHANNELS = {"R", "G", "B", "A"}  # 真实像素通道 (不含 '0', '0' 仅 zero_aware 内部用)
_VALID_SCAN_ORDERS = {"row", "col"}
_VALID_BYTE_BIT_ORDERS = {"msb", "lsb"}
_VALID_MODES = {"detect", "extract", "extract_bytes"}
_VALID_PRESETS = {None, "all", "np"}

# zero_aware 专用 (含 '0' 占位, per v0.5-lsb-tool-15channel-matrix)
_VALID_CHANNELS_ZERO_AWARE = {"R", "G", "B", "A", "0"}

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


# ============ Zero-aware byte stream (per v0.5-lsb-tool-15channel-matrix) ============


def _extract_lsb_byte_stream_zero_aware(
    img_array: np.ndarray,
    channels: list[str],
    bit: int,
    scan_order: str,
    byte_bit_order: str,
) -> bytes:
    """支持 '0' 通道的 byte stream 提取 (per v0.5-lsb-tool-15channel-matrix).

    **'0' 通道语义** (per Owner 截图验证, 跟 随波逐流 一致):
    - '0' 表示 **positional zero**: 占 byte 流位置, 贡献固定 0 bit
    - per pixel: [R_bit, G_bit, 0_bit] 跟 [R_bit, 0_bit, B_bit] 产生不同 byte stream
    - 但当 G_bit 全 0 时, RG0 跟 R00 byte stream 等价 (Owner 截图验证)

    **vs `_extract_lsb_byte_stream`**:
    - channels 可含 '0' 字符 (e.g. ``["R", "G", "0"]``)
    - '0' 通道不抽像素 bit,贡献固定 0 bit,但占 byte 流位置
    - 用于 15 通道矩阵 zero-padded 组合 (RG0/R0B/0GB/R00/0G0/00B)

    **数学约束**:
    - ``_extract_lsb_byte_stream_zero_aware(arr, ["R","G","B"], ...) ==
       _extract_lsb_byte_stream(arr, ["R","G","B"], ...)`` (无 zero 场景等价)
    - ``len(_extract_lsb_byte_stream_zero_aware(arr, ["R","G","0"], ...)) ==
       len(_extract_lsb_byte_stream(arr, ["R","G"], ...))`` (zero 占位置, total_bits 数 = 实际通道数)

    Examples:
        channels=["R","G","B"] / row / bit=0 / MSB: 等价于 _extract_lsb_byte_stream (经典 3 通道)
        channels=["R","G","0"] / row / bit=0 / MSB: R bit + G bit + 0 bit per pixel (positional zero)
        channels=["G"] / col / bit=0 / MSB: G bit per pixel (N=NP 模式)
    """
    if not channels:
        raise ValueError("at least one channel required")
    for c in channels:
        if c not in _VALID_CHANNELS_ZERO_AWARE:
            raise ValueError(f"invalid channel: {c}, valid: {sorted(_VALID_CHANNELS_ZERO_AWARE)}")

    n_ch = len(channels)
    real_channels = [c for c in channels if c != "0"]
    real_positions = [i for i, c in enumerate(channels) if c != "0"]

    if not real_channels:
        # 全 '0' 通道 → 空字节流 (理论上不会发生, 防御性兜底)
        return b""

    ch_indices = [_channel_index(c) for c in real_channels]

    if img_array.ndim < 3 or max(ch_indices) >= img_array.shape[2]:
        raise ValueError(
            f"image has no channel {real_channels} (shape={img_array.shape})"
        )

    # 抽真实通道的像素值 → (H, W, n_real)
    plane = img_array[:, :, ch_indices]

    if scan_order == "row":
        flat_real = plane.reshape(-1, len(real_channels))
    else:  # col
        flat_real = plane.transpose(1, 0, 2).reshape(-1, len(real_channels))

    # 抽 bit 位 → (H*W, n_real)
    real_bits = ((flat_real >> bit) & 1).astype(np.uint8)

    # 还原每像素 n_ch 位 (插入 '0' 通道占位) → (H*W, n_ch)
    pixel_bits = np.zeros((flat_real.shape[0], n_ch), dtype=np.uint8)
    for pos, real_idx in zip(real_positions, range(len(real_channels))):
        pixel_bits[:, pos] = real_bits[:, real_idx]

    bits = pixel_bits.flatten(order="C")
    n_bytes = len(bits) // 8
    bits_trimmed = bits[: n_bytes * 8]

    if byte_bit_order == "msb":
        return np.packbits(bits_trimmed).tobytes()
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


# ============ 8 bit × 6 perm preview matrix (per v0.5-lsb-tool-bitplane-preview-matrix) ============


_PREVIEW_KEYWORDS = (b"Hey", b"flag", b"key", b"PK", b"PNG", b"\x89PNG", b"flag{")


def _ascii_preview(byte_stream: bytes, n_bytes: int = 32) -> str:
    """字节流 → ASCII preview 字符串, 非 printable → '.'.

    用于 _build_bit_plane_preview_matrix 渲染每行.
    """
    if not byte_stream:
        return ""
    out = []
    for b in byte_stream[:n_bytes]:
        out.append(chr(b) if 32 <= b < 127 else ".")
    return "".join(out)


def _build_bit_plane_preview_matrix(
    img_array: np.ndarray,
    n_bytes: int = 32,
    scan_order: str = "row",
    byte_bit_order: str = "msb",
) -> list[tuple[int, str, str, bool]]:
    """8 bit × 6 perm preview 矩阵 (Owner "超过随波逐流" 要求).

    遍历 8 个 bit plane (b0=LSB ~ b7=MSB) × 6 个 RGB perm 排列, 每个 combo 抽前 N 字节字节流
    转 ASCII preview + 命中关键字标注.

    Args:
        img_array: (H, W, 3 or 4) uint8 numpy array
        n_bytes: 每个 combo preview 长度 (默认 32, per Owner 拍板)
        scan_order: "row" / "col" (默认 row, zsteg 默认)
        byte_bit_order: "msb" / "lsb" (默认 msb, zsteg 默认)

    Returns:
        list of (bit, perm_name, preview_str, has_keyword) tuples
        长度 = 8 × 6 = 48
    """
    PERMS = [
        ("RGB", ["R", "G", "B"]),
        ("RBG", ["R", "B", "G"]),
        ("GRB", ["G", "R", "B"]),
        ("GBR", ["G", "B", "R"]),
        ("BRG", ["B", "R", "G"]),
        ("BGR", ["B", "G", "R"]),
    ]
    matrix: list[tuple[int, str, str, bool]] = []
    for bit in range(8):
        for perm_name, channels in PERMS:
            byte_stream = _extract_lsb_byte_stream(
                img_array, channels=channels, bit=bit,
                scan_order=scan_order, byte_bit_order=byte_bit_order,
            )
            preview = _ascii_preview(byte_stream, n_bytes=n_bytes)
            has_kw = any(kw in byte_stream[:n_bytes] for kw in _PREVIEW_KEYWORDS)
            matrix.append((bit, perm_name, preview, has_kw))
    return matrix


def _format_matrix_for_journal(
    matrix: list[tuple[int, str, str, bool]],
    col_width: int = 32,
) -> str:
    """把 preview matrix 渲染成 journal 可读字符串.

    行 = bit (b0~b7), 列 = perm (RGB~BGR).
    """
    if not matrix:
        return ""
    # 表头
    perm_names = ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR"]
    header_cells = [f"{p:>{col_width}s}" for p in perm_names]
    header = " " * 18 + "".join(header_cells)

    # 按 bit 分组
    lines = [header]
    for bit in range(8):
        label = f"bit={bit} ({'LSB' if bit == 0 else 'MSB' if bit == 7 else 'MSB'}):"
        row_cells = []
        for perm_name in perm_names:
            entry = next(
                (e for e in matrix if e[0] == bit and e[1] == perm_name),
                None,
            )
            if entry is None:
                row_cells.append(" " * col_width)
                continue
            _, _, preview, has_kw = entry
            cell = preview.ljust(col_width)
            if has_kw:
                # 命中关键字: 行末加 " <==" 标记
                cell = cell.rstrip() + " <=="
                cell = cell.ljust(col_width + 4)
            row_cells.append(cell)
        lines.append(f"{label:18s}" + "".join(row_cells))
    return "\n".join(lines)


# ============ 15 通道 × LSB+MSB preview matrix (per v0.5-lsb-tool-15channel-matrix Commit 2) ============


# 15 通道组合定义 (per Owner 列表 + 随波逐流 风格, v0.5-train-016 §1.2)
# ('label', channels_with_zero)
#  - 6 full perm: RGB/RBG/GRB/GBR/BRG/BGR (3 bits/pixel)
#  - 6 zero-padded: RG0/R0B/0GB/R00/0G0/00B (1~3 bits/pixel)
#  - 3 single channel: R/G/B (1 bit/pixel)
_15_CHANNELS: list[tuple[str, list[str]]] = [
    # 6 full perm
    ("RGB", ["R", "G", "B"]),
    ("RBG", ["R", "B", "G"]),
    ("GRB", ["G", "R", "B"]),
    ("GBR", ["G", "B", "R"]),
    ("BRG", ["B", "R", "G"]),
    ("BGR", ["B", "G", "R"]),
    # 6 zero-padded (positional zero 语义, 跟 随波逐流 一致)
    ("RG0", ["R", "G", "0"]),
    ("R0B", ["R", "0", "B"]),
    ("0GB", ["0", "G", "B"]),
    ("R00", ["R", "0", "0"]),
    ("0G0", ["0", "G", "0"]),
    ("00B", ["0", "0", "B"]),
    # 3 single channel
    ("R", ["R"]),
    ("G", ["G"]),
    ("B", ["B"]),
]

# LSB + MSB (per Owner "LSB+MSB 增强版")
_15CH_BIT_MODES: list[int] = [0, 7]


def _build_15channel_preview_matrix(
    img_array: np.ndarray,
    n_bytes: int = 50,
    scan_order: str = "row",
    byte_bit_order: str = "msb",
) -> list[tuple[str, int, str, bool]]:
    """15 通道 × 2 bit mode (LSB + MSB) preview 矩阵 (per v0.5-lsb-tool-15channel-matrix).

    Args:
        img_array: (H, W, 3 or 4) uint8 numpy array
        n_bytes: 每 cell preview 长度 (默认 50, per Owner 截图长度, 够识别明文)
        scan_order: "row" (随波逐流 默认)
        byte_bit_order: "msb" (随波逐流 默认)

    Returns:
        list of (label, bit, preview_str, has_keyword) tuples
        长度 = 15 × 2 = 30
    """
    matrix: list[tuple[str, int, str, bool]] = []
    for label, channels in _15_CHANNELS:
        for bit in _15CH_BIT_MODES:
            try:
                byte_stream = _extract_lsb_byte_stream_zero_aware(
                    img_array, channels=channels, bit=bit,
                    scan_order=scan_order, byte_bit_order=byte_bit_order,
                )
            except ValueError:
                byte_stream = b""
            preview = _ascii_preview(byte_stream, n_bytes=n_bytes)
            has_kw = any(kw in byte_stream[:n_bytes] for kw in _PREVIEW_KEYWORDS)
            matrix.append((label, bit, preview, has_kw))
    return matrix


def _format_15channel_matrix_for_journal(
    matrix: list[tuple[str, int, str, bool]],
    preview_width: int = 50,
) -> str:
    """15 通道矩阵渲染 (per 随波逐流 风格 + LSB+MSB 增强).

    输出格式 (2 段: LSB 段 + MSB 段, 每段 15 行):
        [15 通道 LSB (bit 0) 预览]
            preview (50 bytes):
        RGB:        Hey! I think we can write safely in this file witho  <==
        BRG:        $3..$..54<........{...y..3...4...5.;.4..2....?
        ...
        B:          .................................................

        [15 通道 MSB (bit 7) 预览]
            preview (50 bytes):
        RGB:        .....
        ...

    Args:
        matrix: 15 channels × 2 bit modes = 30 entries
        preview_width: preview 列宽 (默认 50, 跟 _build_15channel_preview_matrix n_bytes 对齐)

    Returns:
        多行字符串, journal 友好
    """
    if not matrix:
        return ""

    lines: list[str] = []

    for bit in _15CH_BIT_MODES:
        bit_label = "LSB (bit 0)" if bit == 0 else "MSB (bit 7)"
        lines.append(f"[15 通道 {bit_label} 预览]")
        lines.append(f"{'':<6}preview ({preview_width} bytes):")

        # 按 _15_CHANNELS 顺序输出 (跟 随波逐流 一致)
        for label, _ in _15_CHANNELS:
            entry = next(
                (e for e in matrix if e[0] == label and e[1] == bit),
                None,
            )
            if entry is None:
                lines.append(f"{label}:{'':<{preview_width + 5}}")
                continue
            _, _, preview, has_kw = entry
            cell = preview.ljust(preview_width)
            marker = "  <==" if has_kw else ""
            lines.append(f"{label}:{cell}{marker}")
        lines.append("")  # 段间空行

    return "\n".join(lines).rstrip()