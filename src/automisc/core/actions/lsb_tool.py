"""Action: 统一 LSB 隐写工具 - LSBToolAction (per v0.5-lsb-tool-unify)

**Phase 2a** 实现 detect mode:
- preset=None (默认): 单组合 (按 4 参数), 跑 1 个字节流 + text/magic 检测
- preset="all": 12 组合 (RGB 6 perm × row/col) + 3 通道 8 bit entropy 异常
- preset="np": N=NP 模式 (G channel bit 0 col MSB, per v0.5-train-009)

**Phase 2b** 实现 extract / extract_bytes mode.

公共函数 (_extract_lsb_byte_stream / _is_printable_text / _detect_file_header_hex
/ _shannon_entropy / _unique_count / _MAGIC_PREFIXES) 在 lsb_tool_common.py,
3 mode 共享 (per v0.5-train-012 修复: 字节流同源).

Args:
    channels: "RGB"/"R"/"G,B"/..., 默认 "RGB"
    bit: 0-7, 默认 0 (LSB)
    scan_order: "row"/"col", 默认 "row"
    byte_bit_order: "msb"/"lsb", 默认 "msb"
    mode: "detect"/"extract"/"extract_bytes", 默认 "detect"
    preset: None/"all"/"np", 默认 None (单组合)
    text_min_len: printable 段最小长度, 默认 20
    entropy_threshold: entropy 阈值, 默认 5.0
    unique_threshold: unique count 阈值, 默认 200
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from automisc.core.actions.lsb_tool_common import (
    _BYTE_PREVIEW_LIMIT,  # noqa: F401  # re-exported for tests
    _ENTROPY_THRESHOLD,
    _MAGIC_PREFIXES,  # noqa: F401  # re-exported for tests
    _MIN_BYTE_STREAM_LEN,
    _MIN_PRINTABLE_RUN,
    _PERMUTATIONS,
    _PRINTABLE_WINDOW,  # noqa: F401  # re-exported for tests
    _SCAN_ORDERS,
    _UNIQUE_THRESHOLD,
    _VALID_BYTE_BIT_ORDERS,
    _VALID_MODES,
    _VALID_PRESETS,
    _VALID_SCAN_ORDERS,
    _build_bit_plane_preview_matrix,
    _channel_8bit_byte_stream,
    _bytes_preview,
    _detect_file_header_hex,
    _extract_lsb_byte_stream,
    _format_matrix_for_journal,
    _is_printable_text,
    _parse_channels,
    _perm_name,
    _shannon_entropy,
    _unique_count,
)
from automisc.core.dag import Action, ActionResult
from automisc.core.suspicious import SuspiciousPoint


class LSBToolAction(Action):
    """统一 LSB 隐写工具 (per v0.5-lsb-tool-unify).

    **核心约束 (per AGENTS.md §1 铁律 7)**: detect mode 不写文件 + 不触发下一步.
    3 维检测: text (≥20 字节连续 printable → sev=5) / magic (50+ hex → sev=5)
    / entropy + unique count (跨通道 → sev=4, 仅 preset="all"/"np")."""

    name = "lsb_tool"

    def __init__(
        self,
        *,
        channels: str = "rgb",
        bit: int = 0,
        scan_order: str = "row",
        byte_bit_order: str = "msb",
        mode: str = "detect",
        preset: str | None = None,
        text_min_len: int = _MIN_PRINTABLE_RUN,
        entropy_threshold: float = _ENTROPY_THRESHOLD,
        unique_threshold: int = _UNIQUE_THRESHOLD,
    ):
        # 参数校验 (per spec §3.1)
        if mode not in _VALID_MODES:
            raise ValueError(f"invalid mode: {mode}, valid: {sorted(_VALID_MODES)}")
        if not 0 <= bit <= 7:
            raise ValueError(f"bit must be 0-7, got {bit}")
        if scan_order not in _VALID_SCAN_ORDERS:
            raise ValueError(f"scan_order must be row/col, got {scan_order}")
        if byte_bit_order not in _VALID_BYTE_BIT_ORDERS:
            raise ValueError(
                f"byte_bit_order must be msb/lsb, got {byte_bit_order}"
            )
        if preset not in _VALID_PRESETS:
            raise ValueError(f"preset must be None/'all'/'np', got {preset}")

        self.channels_str = channels
        self.bit = bit
        self.scan_order = scan_order
        self.byte_bit_order = byte_bit_order
        self.mode = mode
        self.preset = preset
        self.text_min_len = text_min_len
        self.entropy_threshold = entropy_threshold
        self.unique_threshold = unique_threshold
        # 延迟解析 channels (校验后再解析)
        self.channels = _parse_channels(channels)

    def run(self, context: dict[str, Any]) -> ActionResult:
        """主入口: 加载图片 → dispatch 到 mode (Phase 2a 只 detect 落地)."""
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(
                success=False, message="lsb_tool: missing 'file_path' in context"
            )
        if not Path(file_path).exists():
            return ActionResult(
                success=False, message=f"lsb_tool: file not found: {file_path}"
            )

        try:
            img = Image.open(file_path).convert("RGB")
        except Exception as e:
            return ActionResult(
                success=False, message=f"lsb_tool: PIL open failed: {e}"
            )
        arr = np.array(img)

        if self.mode == "detect":
            return self._run_detect(arr, file_path)
        if self.mode == "extract":
            return self._run_extract(arr, file_path)
        # extract_bytes
        return self._run_extract_bytes(arr, file_path)

    # ----- detect mode (Phase 2a 完整实现) -----

    def _run_detect(
        self, arr: np.ndarray, file_path: str
    ) -> ActionResult:
        """readonly 探测 (per AGENTS §1 铁律 7)."""
        sps: list[SuspiciousPoint] = []
        if self.preset is None:
            sps.extend(self._detect_single_combo(arr, file_path))
        elif self.preset == "all":
            sps.extend(self._detect_all_combos(arr, file_path))
            sps.extend(self._detect_channel_anomaly(arr, file_path))
        elif self.preset == "np":
            sps.extend(self._detect_np_mode(arr, file_path))

        # per Owner "超过随波逐流" 拍板: 每张图都打 8 bit × 6 perm preview matrix
        # (per v0.5-lsb-tool-bitplane-preview-matrix Commit 2)
        matrix = _build_bit_plane_preview_matrix(arr, n_bytes=32)
        matrix_text = _format_matrix_for_journal(matrix)

        return ActionResult(
            success=True,
            data={
                "suspicious_points": [
                    {
                        "category": sp.category,
                        "matched_pattern": sp.matched_pattern,
                        "severity": sp.severity,
                        "context": sp.context,
                    }
                    for sp in sps
                ],
                "n_sps": len(sps),
                "preset": self.preset or "single",
                "channels": self.channels_str,
                "bit": self.bit,
                "scan_order": self.scan_order,
                "byte_bit_order": self.byte_bit_order,
            },
            message=(
                f"lsb_tool detect: preset={self.preset or 'single'}, "
                f"命中 {len(sps)} SP "
                f"({sum(1 for sp in sps if sp.severity == 5)} sev=5 真可疑, "
                f"{sum(1 for sp in sps if sp.severity == 4)} sev=4 概率)\n"
                f"\n[bit-plane preview matrix 8 bit × 6 perm, 每行 32 字节 ASCII preview, "
                f"<== 标 hit-keyword]\n"
                f"{matrix_text}"
            ),
        )

    def _detect_single_combo(
        self, arr: np.ndarray, file_path: str
    ) -> list[SuspiciousPoint]:
        """单组合检测 (按 self.channels/bit/scan_order/byte_bit_order)."""
        sps: list[SuspiciousPoint] = []
        try:
            byte_stream = _extract_lsb_byte_stream(
                arr,
                channels=self.channels,
                bit=self.bit,
                scan_order=self.scan_order,
                byte_bit_order=self.byte_bit_order,
            )
        except ValueError as e:
            return [SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="lsb_error",
                offset=None,
                matched_pattern=f"lsb_tool single combo 失败: {e}",
                severity=1,
                suggested_action="检查 channels 参数",
                context={"error": str(e)},
            )]

        if len(byte_stream) < _MIN_BYTE_STREAM_LEN:
            return sps

        sps.extend(self._detect_text_magic(
            byte_stream, file_path, combo_label=self._combo_label()
        ))
        return sps

    def _detect_all_combos(
        self, arr: np.ndarray, file_path: str
    ) -> list[SuspiciousPoint]:
        """12 组合检测 (RGB 6 perm × row/col, bit 0 MSB, per lsb_detect 已有实现)."""
        sps: list[SuspiciousPoint] = []
        channel_names = ["R", "G", "B"]
        for perm in _PERMUTATIONS:
            perm_n = _perm_name(perm)
            ch_list = [channel_names[i] for i in perm]
            for scan in _SCAN_ORDERS:
                byte_stream = _extract_lsb_byte_stream(
                    arr,
                    channels=ch_list,
                    bit=0,  # preset="all" 固定 bit 0 (LSB)
                    scan_order=scan,
                    byte_bit_order="msb",
                )
                if len(byte_stream) < _MIN_BYTE_STREAM_LEN:
                    continue
                combo_label = f"lsb {perm_n} {scan}"
                sps.extend(self._detect_text_magic(
                    byte_stream, file_path, combo_label=combo_label
                ))
        return sps

    def _detect_channel_anomaly(
        self, arr: np.ndarray, file_path: str
    ) -> list[SuspiciousPoint]:
        """单通道 8 bit entropy + unique count 异常检测 (per v0.5-train-010 N=NP 模式).

        R/G/B 各自完整 8 bit plane 拼 byte stream, 算 entropy + unique,
        跟阈值比 → sev=4 (per Owner "没有绝对性").
        """
        sps: list[SuspiciousPoint] = []
        all_ents: list[float] = []
        all_uniques: list[int] = []
        for ch_idx in range(3):
            plane = arr[:, :, ch_idx]
            bs = _channel_8bit_byte_stream(plane)
            all_ents.append(_shannon_entropy(bs))
            all_uniques.append(_unique_count(bs))

        max_diff = max(all_ents) - min(all_ents)
        for ch_idx, ch_name in enumerate(["R", "G", "B"]):
            ent = all_ents[ch_idx]
            uniq = all_uniques[ch_idx]
            if ent > self.entropy_threshold and uniq >= self.unique_threshold:
                sps.append(SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="lsb_channel_anomaly",
                    offset=None,
                    matched_pattern=(
                        f"lsb_tool 发现 {ch_name} plane 存在可疑隐藏信息 "
                        f"(entropy={ent:.2f} unique={uniq}/256, 跨通道差 {max_diff:.2f})"
                    ),
                    severity=4,
                    suggested_action=(
                        f"{ch_name} 通道 8 bit byte stream entropy 异常高, "
                        f"建议手工跑 lsb-bytes chain 抽字节流"
                    ),
                    context={
                        "channel": ch_name,
                        "entropy": ent,
                        "unique": uniq,
                        "max_diff": max_diff,
                    },
                ))
        return sps

    def _detect_np_mode(
        self, arr: np.ndarray, file_path: str
    ) -> list[SuspiciousPoint]:
        """N=NP 模式: G channel bit 0 col MSB (per v0.5-train-009 默认 preset).

        entropy > threshold + unique >= threshold → sev=5 (比 preset="all" 严重,
        因为 N=NP 模式是经过实战验证的强信号).
        """
        sps: list[SuspiciousPoint] = []
        try:
            byte_stream = _extract_lsb_byte_stream(
                arr,
                channels=["G"],
                bit=0,
                scan_order="col",
                byte_bit_order="msb",
            )
        except ValueError as e:
            return [SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="lsb_error",
                offset=None,
                matched_pattern=f"lsb_tool np mode 失败: {e}",
                severity=1,
                suggested_action="检查图片是否有 G 通道",
                context={"error": str(e)},
            )]

        ent = _shannon_entropy(byte_stream)
        uniq = _unique_count(byte_stream)
        if ent > self.entropy_threshold and uniq >= self.unique_threshold:
            sps.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="lsb_channel_anomaly",
                offset=None,
                matched_pattern=(
                    f"lsb_tool N=NP 模式命中 G 通道 LSB 异常 "
                    f"(entropy={ent:.2f} unique={uniq}/256)"
                ),
                severity=5,
                suggested_action="N=NP 模式命中, 建议手工验证 (G 通道 bit 0 列扫描)",
                context={"entropy": ent, "unique": uniq, "mode": "np"},
            ))
        return sps

    def _detect_text_magic(
        self,
        byte_stream: bytes,
        file_path: str,
        combo_label: str,
    ) -> list[SuspiciousPoint]:
        """3 维检测共用 text + magic (entropy 异常由 channel_anomaly / np_mode 单独跑).

        命中 text → return (不重复走 magic).
        命中 magic → return.
        都不命中 → return [].
        """
        sps: list[SuspiciousPoint] = []

        # 1. text 判定
        if _is_printable_text(byte_stream, min_run=self.text_min_len):
            sps.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="lsb_text",
                offset=None,
                matched_pattern=(
                    f"lsb_tool 发现 {combo_label} 存在可疑内容: "
                    f"{_bytes_preview(byte_stream)}"
                ),
                severity=5,
                suggested_action=f"{combo_label} 命中 printable text, 建议手工验证",
            ))
            return sps  # 命中 text, 不再走文件头判定

        # 2. file magic 判定
        magic_hit = _detect_file_header_hex(byte_stream)
        if magic_hit:
            ext, label = magic_hit
            sps.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="lsb_file_header",
                offset=None,
                matched_pattern=(
                    f"lsb_tool 发现 {combo_label} 存在可疑 {ext} 文件: "
                    f"{_bytes_preview(byte_stream)}"
                ),
                severity=5,
                suggested_action=f"{combo_label} 命中 {label}, 建议 foremost 分离",
                context={"file_type": ext, "magic_label": label},
            ))
        return sps

    def _combo_label(self) -> str:
        """生成当前 combo 的描述 (用于 SP.matched_pattern)."""
        ch_str = ",".join(self.channels)
        return (
            f"lsb {ch_str} bit={self.bit} "
            f"scan={self.scan_order} byte_bit_order={self.byte_bit_order}"
        )

    # ----- extract / extract_bytes mode (Phase 2b, 走 lsb_tool_extract 模块) -----

    def _run_extract(self, arr, file_path):
        """extract mode: preset='all' 12 组合 + magic 命中写文件 (替代 zsteg subprocess)."""
        from automisc.core.actions.lsb_tool_extract import run_extract_mode
        return run_extract_mode(self, arr, file_path, self.bit, self.byte_bit_order)

    def _run_extract_bytes(self, arr, file_path):
        """extract_bytes mode: 单组合 + 写文件 (chain lsb-bytes 入口)."""
        from automisc.core.actions.lsb_tool_extract import run_extract_bytes_mode
        return run_extract_bytes_mode(self, arr, file_path)