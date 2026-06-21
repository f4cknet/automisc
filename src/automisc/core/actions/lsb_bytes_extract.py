"""Action: LSB 字节流自定义抽取（v0.5-lsb-byte-stream-extract 能力 B）

**目的**：从 PNG/BMP/GIF 任意通道 × 任意 bit 位 × 任意扫描顺序 × 任意字节内 bit 序,
抽出 raw bytes,写到 input 同目录。

**触发**: v0.5-train-009 — N=NP 题 writeup 用 PIL `getpixel((w,h))[1] & 1` **列扫描**
抽 G 通道 LSB 字节流 → unhexlify → pyc → 执行。现有 `LSBExtractAction` 基于 zsteg 固定
通道位组合,本 action 提供 **user-controlled 4 参数** 入口,**并行不冲突**。

**4 参数**:

| 参数 | 默认 | 可选 |
|---|---|---|
| ``channel`` | RGB (三通道) | R / G / B / A (任意选择,逗号分隔) |
| ``bit`` | 0 (LSB) | 0~7 |
| ``scan_order`` | row (行扫描,外层 h 内层 w) | row / col (列扫描,外层 w 内层 h = writeup 顺序) |
| ``byte_bit_order`` | MSB | MSB (writeup 默认) / LSB (字节内 bit 反序) |

**组合数**: 3 通道 × 8 bit × 2 顺序 × 2 byte-order = **96 组合**,GUI 默认跑
3 通道 × bit 0/7 × row/col × MSB = **12 组合** (per Owner Q1)。

**输出**: `<stem>__lsb_<channel>_b<bit>_<order>_<byteord>.bin`,per v0.5-output-samedir
同目录。

**与现有 LSBExtractAction 关系**:
- LSBExtractAction (zsteg-based) = 固定通道位组合 + 固定 row 扫描 + 文本/文件自动分类
- LSBBytesExtractAction (本) = **user-controlled 4 参数** + 直接 PIL/numpy 切片 + **只抽字节流,不分类**

**用法** (DAG chain):
    binwalk_extract → LSBBytesExtractAction → magic_sniffer (decoder)
    ↑ chain `lsb-bytes` 见 core/chains.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from automisc.core.dag import Action, ActionResult
from automisc.core.utils.output_path import output_path_for


# ----- 4 参数类型 + 校验 -----
Channel = Literal["R", "G", "B", "A"]
ScanOrder = Literal["row", "col"]
ByteBitOrder = Literal["MSB", "LSB"]

_VALID_CHANNELS = {"R", "G", "B", "A"}
_VALID_BITS = set(range(8))
_VALID_SCAN_ORDERS = {"row", "col"}
_VALID_BYTE_BIT_ORDERS = {"MSB", "LSB"}


def _parse_channels(channels: str | list[str]) -> list[Channel]:
    """'R,G,B' / ['R','G','B'] / 'RGB' 三种输入 → ['R','G','B']"""
    if isinstance(channels, str):
        # 支持逗号分隔 / 连续字母 (e.g. 'RGB' = 'R,G,B')
        if "," in channels:
            parts = [c.strip().upper() for c in channels.split(",") if c.strip()]
        else:
            parts = list(channels.upper())
    else:
        parts = [c.upper() for c in channels]
    invalid = [c for c in parts if c not in _VALID_CHANNELS]
    if invalid:
        raise ValueError(
            f"invalid channels: {invalid}, valid: {sorted(_VALID_CHANNELS)}"
        )
    if not parts:
        raise ValueError("at least one channel required")
    # 去重保序
    seen: set[str] = set()
    out: list[Channel] = []
    for c in parts:
        if c not in seen:
            seen.add(c)
            out.append(c)  # type: ignore[arg-type]
    return out


def _channel_index(ch: Channel) -> int:
    """R → 0, G → 1, B → 2, A → 3"""
    return {"R": 0, "G": 1, "B": 2, "A": 3}[ch]


def _extract_bits_from_image(
    img_array: np.ndarray,
    channels: list[Channel],
    bit: int,
    scan_order: ScanOrder,
) -> np.ndarray:
    """从 image array 提取指定 channel × bit 位 的 0/1 流.

    Args:
        img_array: (H, W, 3 or 4) uint8 numpy array
        channels: e.g. ["G"]
        bit: 0~7
        scan_order: "row" = 行扫描 flatten() / "col" = 列扫描 .T.flatten()

    Returns:
        1D uint8 array, 0/1 values
    """
    bits_list = []
    for ch in channels:
        idx = _channel_index(ch)
        if idx >= img_array.shape[2]:
            raise ValueError(
                f"image has no alpha channel (shape={img_array.shape}), "
                f"can't extract channel {ch}"
            )
        channel_data = img_array[:, :, idx]
        bits = ((channel_data >> bit) & 1).astype(np.uint8)
        if scan_order == "row":
            bits = bits.flatten()  # row-major: 外层 h 内层 w
        else:
            bits = bits.T.flatten()  # column-major: 外层 w 内层 h (writeup 顺序)
        bits_list.append(bits)
    # 多通道: 按 channels 顺序拼接
    return np.concatenate(bits_list) if len(bits_list) > 1 else bits_list[0]


def _bits_to_bytes(bits: np.ndarray, byte_bit_order: ByteBitOrder) -> bytes:
    """0/1 流 → bytes.

    Args:
        bits: 1D 0/1 array
        byte_bit_order: "MSB" = np.packbits 默认 (writeup 默认)
                        "LSB" = 字节内 bit 反序

    Returns:
        bytes, 长度 = len(bits) // 8
    """
    n_bytes = len(bits) // 8
    bits_trimmed = bits[: n_bytes * 8]
    if byte_bit_order == "MSB":
        return np.packbits(bits_trimmed).tobytes()
    # LSB first: 字节内 bit 反序
    bits_2d = bits_trimmed.reshape(-1, 8)[:, ::-1].flatten()
    return np.packbits(bits_2d).tobytes()


def _output_filename(
    channels: list[Channel],
    bit: int,
    scan_order: ScanOrder,
    byte_bit_order: ByteBitOrder,
) -> str:
    """生成 `<stem>__lsb_<channel>_b<bit>_<order>_<byteord>.bin` 风格 purpose 标识.

    Examples:
        [G], 0, col, MSB → "lsb_g_b0_col_msb"
        [R,G,B], 7, row, MSB → "lsb_rgb_b7_row_msb"
    """
    ch_part = "".join(c.lower() for c in channels)
    return f"lsb_{ch_part}_b{bit}_{scan_order.lower()}_{byte_bit_order.lower()}"


# ----- 主 Action -----
class LSBBytesExtractAction(Action):
    """LSB 字节流自定义抽取（v0.5-lsb-byte-stream-extract 能力 B 核心）.

    Args:
        channels: 通道列表, 默认 ["R", "G", "B"] (RGB 全跑)
        bit: bit 位 0~7, 默认 0 (LSB)
        scan_order: "row" / "col", 默认 "row"
        byte_bit_order: "MSB" / "LSB", 默认 "MSB"
    """

    name = "lsb_bytes_extract"

    def __init__(
        self,
        channels: list[str] | str | None = None,
        bit: int = 0,
        scan_order: str = "row",
        byte_bit_order: str = "MSB",
    ):
        # 默认 RGB 三通道 (per Owner Q1 全跑 12 组合)
        self.channels: list[Channel] = (
            _parse_channels(channels) if channels else ["R", "G", "B"]
        )
        if bit not in _VALID_BITS:
            raise ValueError(f"bit must be 0..7, got {bit}")
        self.bit = bit
        if scan_order not in _VALID_SCAN_ORDERS:
            raise ValueError(f"scan_order must be row/col, got {scan_order}")
        self.scan_order = scan_order  # type: ignore[assignment]
        if byte_bit_order not in _VALID_BYTE_BIT_ORDERS:
            raise ValueError(
                f"byte_bit_order must be MSB/LSB, got {byte_bit_order}"
            )
        self.byte_bit_order = byte_bit_order  # type: ignore[assignment]

    def run(self, context: dict[str, Any]) -> ActionResult:
        """抽 LSB 字节流 → 写到 input 同目录.

        Context 输入:
            - file_path: 输入图片路径
            - (可选) channels / bit / scan_order / byte_bit_order: 覆盖 __init__ 默认值

        Returns:
            ActionResult(success=True, data={
                "lsb_bytes": {
                    "channels": [...],
                    "bit": N,
                    "scan_order": "row"|"col",
                    "byte_bit_order": "MSB"|"LSB",
                    "extracted_path": str,
                    "raw_size": int,
                },
                "extracted_files": [str],
            })
        """
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(
                success=False,
                message="lsb_bytes_extract: missing 'file_path' in context",
            )

        # context 可覆盖默认参数 (per chain 灵活配置)
        channels = _parse_channels(
            context.get("channels") or context.get("__lsb_channels__")
            or self.channels
        )
        bit = int(context.get("bit") or context.get("__lsb_bit__") or self.bit)
        if bit not in _VALID_BITS:
            return ActionResult(
                success=False, message=f"lsb_bytes_extract: bit must be 0..7, got {bit}",
            )
        scan_order = (
            context.get("scan_order") or context.get("__lsb_scan_order__")
            or self.scan_order
        )
        if scan_order not in _VALID_SCAN_ORDERS:
            return ActionResult(
                success=False,
                message=f"lsb_bytes_extract: scan_order must be row/col, got {scan_order}",
            )
        byte_bit_order = (
            context.get("byte_bit_order") or context.get("__lsb_byte_bit_order__")
            or self.byte_bit_order
        )
        if byte_bit_order not in _VALID_BYTE_BIT_ORDERS:
            return ActionResult(
                success=False,
                message=f"lsb_bytes_extract: byte_bit_order must be MSB/LSB, got {byte_bit_order}",
            )

        if not Path(file_path).exists():
            return ActionResult(
                success=False,
                message=f"lsb_bytes_extract: file not found: {file_path}",
            )

        try:
            img = Image.open(file_path).convert("RGBA" if "A" in channels else "RGB")
            img_array = np.array(img)
        except Exception as e:  # noqa: BLE001
            return ActionResult(
                success=False,
                message=f"lsb_bytes_extract: failed to read image: {e}",
                data={"error": str(e)},
            )

        try:
            bits = _extract_bits_from_image(img_array, channels, bit, scan_order)
        except ValueError as e:
            return ActionResult(
                success=False,
                message=f"lsb_bytes_extract: {e}",
                data={"error": str(e)},
            )

        raw_bytes = _bits_to_bytes(bits, byte_bit_order)

        # 写文件 (per v0.5-output-samedir + Owner Q5: 文件名带全部 4 参数)
        purpose = _output_filename(channels, bit, scan_order, byte_bit_order)
        out_path = output_path_for(file_path, suffix=".bin", purpose=purpose)
        out_path.write_bytes(raw_bytes)

        return ActionResult(
            success=True,
            data={
                "lsb_bytes": {
                    "channels": channels,
                    "bit": bit,
                    "scan_order": scan_order,
                    "byte_bit_order": byte_bit_order,
                    "extracted_path": str(out_path),
                    "raw_size": len(raw_bytes),
                },
                "extracted_files": [str(out_path)],
            },
            message=(
                f"lsb_bytes_extract: channels={','.join(channels)} "
                f"bit={bit} scan={scan_order} byte_order={byte_bit_order} "
                f"→ {out_path} ({len(raw_bytes)} bytes)"
            ),
        )


__all__ = [
    "LSBBytesExtractAction",
    "_parse_channels",
    "_channel_index",
    "_extract_bits_from_image",
    "_bits_to_bytes",
    "_output_filename",
]
