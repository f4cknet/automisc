"""LSB extract / extract_bytes mode (v0.5-lsb-tool-unify, Phase 2b)

替代:
- LSBExtractAction (`core/actions/lsb_extract.py` 356 LOC) - zsteg subprocess 抽 raw
- LSBBytesExtractAction (`core/actions/lsb_bytes_extract.py` 312 LOC) - chain lsb-bytes

**核心改进**:
- 字节流提取走 `_extract_lsb_byte_stream` (公共函数, 跟 detect mode 同源)
- 修复 v0.5-train-012 bug: 工具栏写真字节流跟 detect mode 命中字节流一致
- 4 参数 zsteg 兼容 (channels/bit/scan_order/byte_bit_order)
- detect mode 命中 text/magic → 自动提取 raw bytes 写文件 (extract mode 默认 preset="all")
- extract_bytes mode 单组合 (chain lsb-bytes 入口)

**写文件** (per v0.5-output-samedir):
- 文件名: `<stem>__lsb_<channel>_b<bit>_<order>_<byteord>.<ext>`
  - `<ext>` = magic 命中时取 ext (e.g. "zip"/"png"/"pyc"), 否则 "bin"
  - 路径 = input 同目录 (`output_path_for` 逻辑)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from automisc.core.actions.lsb_tool_common import (
    _MIN_BYTE_STREAM_LEN,
    _PERMUTATIONS,
    _SCAN_ORDERS,
    _detect_file_header_hex,
    _extract_lsb_byte_stream,
    _perm_name,
)
from automisc.core.utils.output_path import output_path_for


def _combo_filename_part(channels: list[str], bit: int, scan_order: str, byte_bit_order: str) -> str:
    """生成 `<channel>_b<bit>_<order>_<byteord>` 文件名片段.

    Examples:
        [G], 0, col, msb → "lsb_g_b0_col_msb"
        [R,G,B], 7, row, msb → "lsb_rgb_b7_row_msb"
    """
    ch_part = "".join(c.lower() for c in channels)
    return f"lsb_{ch_part}_b{bit}_{scan_order.lower()}_{byte_bit_order.lower()}"


def _decide_extension(byte_stream: bytes, default_ext: str = "bin") -> tuple[str, str]:
    """根据 magic 决定输出文件扩展名.

    Returns:
        (ext, label) - ext 用于文件名, label 用于 SP.matched_pattern
    """
    magic_hit = _detect_file_header_hex(byte_stream)
    if magic_hit:
        return magic_hit  # (ext, label)
    return (default_ext, "raw bytes")


def _extract_and_write(
    arr: np.ndarray,
    channels: list[str],
    bit: int,
    scan_order: str,
    byte_bit_order: str,
    file_path: str,
) -> tuple[bytes, str, str, str]:
    """单组合字节流提取 + 写文件.

    Returns:
        (byte_stream, output_path, ext, label)
    """
    byte_stream = _extract_lsb_byte_stream(
        arr, channels=channels, bit=bit, scan_order=scan_order, byte_bit_order=byte_bit_order
    )
    ext, label = _decide_extension(byte_stream)
    purpose = _combo_filename_part(channels, bit, scan_order, byte_bit_order)
    out_path = output_path_for(file_path, suffix=f".{ext}", purpose=purpose)
    out_path.write_bytes(byte_stream)
    return (byte_stream, str(out_path), ext, label)


# ============ extract mode ============


def run_extract(
    arr: np.ndarray,
    file_path: str,
    bit: int = 0,
    byte_bit_order: str = "msb",
    min_byte_len: int = _MIN_BYTE_STREAM_LEN,
) -> dict[str, Any]:
    """extract mode 主函数 (preset="all" 12 组合 + magic 检测 + 写文件).

    替代 LSBExtractAction zsteg subprocess 路径 (Win 上坏) → PIL/numpy 字节流.

    Args:
        arr: (H, W, 3) uint8 numpy array (RGB)
        file_path: 输入图片路径 (写文件目录)
        bit: 默认 0 (LSB), preset="all" 固定
        byte_bit_order: 默认 "msb"
        min_byte_len: 字节流最小长度 (低于不写文件)

    Returns:
        dict with:
            - "extracted_files": [str] - 写出的文件路径列表
            - "extracted_count": int - 命中 + 写出数
            - "combos_scanned": int - 跑的组合数
            - "hits": list[dict] - 每个 hit 的 (channel, scan_order, ext, label, path)
    """
    channel_names = ["R", "G", "B"]
    extracted_files: list[str] = []
    hits: list[dict[str, Any]] = []
    combos_scanned = 0

    for perm in _PERMUTATIONS:
        perm_n = _perm_name(perm)
        ch_list = [channel_names[i] for i in perm]
        for scan in _SCAN_ORDERS:
            combos_scanned += 1
            try:
                byte_stream = _extract_lsb_byte_stream(
                    arr, channels=ch_list, bit=bit, scan_order=scan, byte_bit_order=byte_bit_order
                )
            except ValueError:
                continue

            if len(byte_stream) < min_byte_len:
                continue

            # 只有 magic 命中才写文件 (text 不写, 避免噪声)
            magic_hit = _detect_file_header_hex(byte_stream)
            if not magic_hit:
                continue

            ext, label = magic_hit
            purpose = _combo_filename_part(ch_list, bit, scan, byte_bit_order)
            out_path = output_path_for(file_path, suffix=f".{ext}", purpose=purpose)
            out_path.write_bytes(byte_stream)
            extracted_files.append(str(out_path))
            hits.append({
                "channels": ch_list,
                "perm_name": perm_n,
                "scan_order": scan,
                "ext": ext,
                "label": label,
                "path": str(out_path),
                "size": len(byte_stream),
            })

    return {
        "extracted_files": extracted_files,
        "extracted_count": len(extracted_files),
        "combos_scanned": combos_scanned,
        "hits": hits,
    }


# ============ extract_bytes mode ============


def run_extract_bytes(
    arr: np.ndarray,
    file_path: str,
    channels: list[str],
    bit: int,
    scan_order: str,
    byte_bit_order: str,
    min_byte_len: int = _MIN_BYTE_STREAM_LEN,
) -> dict[str, Any]:
    """extract_bytes mode 主函数 (单组合 + 写文件).

    替代 LSBBytesExtractAction - 同样的 4 参数接口, 但走公共字节流函数.

    Returns:
        dict with:
            - "lsb_bytes": {channels, bit, scan_order, byte_bit_order, extracted_path, raw_size}
            - "extracted_files": [str]
            - "ext": str - 输出文件扩展名 (magic 命中时)
            - "label": str - magic label
    """
    try:
        byte_stream = _extract_lsb_byte_stream(
            arr, channels=channels, bit=bit, scan_order=scan_order, byte_bit_order=byte_bit_order
        )
    except ValueError as e:
        return {
            "error": str(e),
            "extracted_files": [],
        }

    if len(byte_stream) < min_byte_len:
        return {
            "error": f"byte stream too short: {len(byte_stream)} < {min_byte_len}",
            "extracted_files": [],
        }

    ext, label = _decide_extension(byte_stream)
    purpose = _combo_filename_part(channels, bit, scan_order, byte_bit_order)
    out_path = output_path_for(file_path, suffix=f".{ext}", purpose=purpose)
    out_path.write_bytes(byte_stream)

    return {
        "lsb_bytes": {
            "channels": channels,
            "bit": bit,
            "scan_order": scan_order,
            "byte_bit_order": byte_bit_order,
            "extracted_path": str(out_path),
            "raw_size": len(byte_stream),
            "ext": ext,
            "label": label,
        },
        "extracted_files": [str(out_path)],
    }


# ============ LSBToolAction adapter (Phase 2b) ============

from automisc.core.dag import ActionResult  # noqa: E402  # circular avoid
from automisc.core.suspicious import SuspiciousPoint  # noqa: E402


def _build_sps_from_hits(tool_name: str, file_path: str, hits: list[dict]) -> list[SuspiciousPoint]:
    """extract mode: 每个 magic hit 一个 SP."""
    return [SuspiciousPoint(
        id="",
        tool_name=tool_name,
        file_path=file_path,
        category="lsb_extracted_file",
        offset=None,
        matched_pattern=(
            f"lsb_tool extract 命中 magic: {hit['ext']} "
            f"(channels={hit['channels']} scan={hit['scan_order']}, {hit['size']} bytes)"
        ),
        severity=5,
        suggested_action=f"已写文件 {hit['path']}, 可 foremost / binwalk 进一步分离",
        context={
            "channels": hit["channels"],
            "scan_order": hit["scan_order"],
            "ext": hit["ext"],
            "label": hit["label"],
            "extracted_path": hit["path"],
        },
    ) for hit in hits]


def _sp_to_dict(sp: SuspiciousPoint) -> dict:
    """SP → dict (for ActionResult.data 序列化)."""
    return {
        "category": sp.category,
        "matched_pattern": sp.matched_pattern,
        "severity": sp.severity,
        "context": sp.context,
    }


def run_extract_mode(
    action_self,
    arr: np.ndarray,
    file_path: str,
    bit: int,
    byte_bit_order: str,
) -> ActionResult:
    """LSBToolAction._run_extract 的实际工作 (走 run_extract + build SP + ActionResult)."""
    try:
        result_data = run_extract(
            arr, file_path, bit=bit, byte_bit_order=byte_bit_order
        )
    except Exception as e:  # noqa: BLE001
        return ActionResult(success=False, message=f"lsb_tool extract 失败: {e}")

    hits = result_data.get("hits", [])
    sps = _build_sps_from_hits(action_self.name, file_path, hits)

    return ActionResult(
        success=True,
        data={
            "suspicious_points": [_sp_to_dict(sp) for sp in sps],
            "n_sps": len(sps),
            "extracted_files": result_data.get("extracted_files", []),
            "extracted_count": result_data.get("extracted_count", 0),
            "combos_scanned": result_data.get("combos_scanned", 0),
        },
        message=(
            f"lsb_tool extract: 跑 {result_data.get('combos_scanned', 0)} 组合, "
            f"命中 {result_data.get('extracted_count', 0)} magic, "
            f"写 {len(result_data.get('extracted_files', []))} 文件"
        ),
    )


def run_extract_bytes_mode(
    action_self,
    arr: np.ndarray,
    file_path: str,
) -> ActionResult:
    """LSBToolAction._run_extract_bytes 的实际工作."""
    try:
        result_data = run_extract_bytes(
            arr,
            file_path,
            channels=action_self.channels,
            bit=action_self.bit,
            scan_order=action_self.scan_order,
            byte_bit_order=action_self.byte_bit_order,
        )
    except Exception as e:  # noqa: BLE001
        return ActionResult(success=False, message=f"lsb_tool extract_bytes 失败: {e}")

    if "error" in result_data:
        return ActionResult(
            success=False, message=f"lsb_tool extract_bytes: {result_data['error']}"
        )

    lsb_bytes_info = result_data.get("lsb_bytes", {})
    ext = lsb_bytes_info.get("ext", "bin")
    label = lsb_bytes_info.get("label", "raw bytes")
    sps = [SuspiciousPoint(
        id="",
        tool_name=action_self.name,
        file_path=file_path,
        category="lsb_extracted_bytes",
        offset=None,
        matched_pattern=(
            f"lsb_tool extract_bytes 写出 {ext} ({lsb_bytes_info.get('raw_size', 0)} bytes): "
            f"{lsb_bytes_info.get('extracted_path', '')}"
        ),
        severity=5,
        suggested_action=f"已写文件, magic={label}, 可后续 foremost / binwalk 分离",
        context=lsb_bytes_info,
    )]

    return ActionResult(
        success=True,
        data={
            "suspicious_points": [_sp_to_dict(sp) for sp in sps],
            "n_sps": len(sps),
            "extracted_files": result_data.get("extracted_files", []),
            "lsb_bytes": lsb_bytes_info,
        },
        message=(
            f"lsb_tool extract_bytes: channels={','.join(action_self.channels)} "
            f"bit={action_self.bit} scan={action_self.scan_order} "
            f"byte_order={action_self.byte_bit_order} → "
            f"{lsb_bytes_info.get('extracted_path', '?')} "
            f"({lsb_bytes_info.get('raw_size', 0)} bytes, ext={ext})"
        ),
    )