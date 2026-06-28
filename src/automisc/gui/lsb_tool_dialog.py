"""LSB 工具参数 dialog (per v0.5-lsb-tool-unify, Phase 4)

GUI 统一 LSB 入口,替代:
- `lsb_bytes_dialog.LSBBytesParamDialog` (chain `lsb-bytes` 4 参数 dialog, Phase 6 删除)
- `lsb_extract` action button (老 zsteg subprocess, Win 不可用, backward compat 保留)

**用法**::

    from automisc.gui.lsb_tool_dialog import LSBToolParamDialog

    dialog = LSBToolParamDialog(parent)
    if dialog.exec() == QDialog.Accepted:
        kwargs = dialog.get_kwargs()  # {__lsb_mode__, __lsb_channels__, ...}
        runner = ChainRunner(chain_name="lsb_tool", extra_context=kwargs)

**控件**:
- mode: QComboBox (detect / extract / extract_bytes, 默认 detect)
- channels: QComboBox (R/G/B/A/RG/RB/GB/RGB/RGBA, 默认 RGB)
- bit: QSpinBox 0..7 (默认 0)
- scan_order: QComboBox (row / col, 默认 row)
- byte_bit_order: QComboBox (MSB / LSB, 默认 MSB)
- text_min_len: QSpinBox (detect 模式, 默认 20)
- entropy_threshold: QDoubleSpinBox (detect 模式, 默认 5.0)
- unique_threshold: QSpinBox (detect 模式, 默认 200)

**Preset 按钮**: 一键填实战常用组合 (per spec §3.6):
- "N=NP 默认" → mode=extract + G/bit0/col/MSB (per v0.5-train-009)
- "全通道默认" → mode=detect + RGB/bit0/row/MSB (per spec §3.6 default)
- "隐写智能分析" → mode=detect + RGB/bit0/row/MSB + preset=all (per spec §3.5)

**detect-only 参数**: text_min_len / entropy_threshold / unique_threshold
- detect 模式显示 (3 个 QSpinBox/DoubleSpinBox)
- extract / extract_bytes 模式隐藏 (LSBToolAction 不读这些参数)
- 切换 mode 时自动 show/hide (per QStackedWidget 或 setVisible)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ComboBox items — 跟 LSBToolAction._VALID_* 兼容
_MODE_OPTIONS = ["detect", "extract", "extract_bytes"]
_CHANNEL_OPTIONS = [
    "R",
    "G",      # N=NP 默认
    "B",
    "A",      # RGBA 用
    "RG",
    "RB",
    "GB",
    "RGB",    # 全通道默认 (per LSBToolAction 默认)
    "RGBA",
]
_SCAN_ORDER_OPTIONS = ["row", "col"]
_BYTE_BIT_ORDER_OPTIONS = ["MSB", "LSB"]


# Preset 定义 — 一键填实战常用组合 (per spec §3.6)
# preset name → (mode, channels, bit, scan_order, byte_bit_order, preset_override)
PRESETS: dict[str, tuple[str, str, int, str, str, str | None]] = {
    "N=NP 默认 (extract + G/bit0/col/MSB)": (
        "extract", "G", 0, "col", "MSB", None,
    ),
    "全通道默认 (detect + RGB/bit0/row/MSB)": (
        "detect", "RGB", 0, "row", "MSB", None,
    ),
    "隐写智能分析 (detect + preset=all + RGB)": (
        "detect", "RGB", 0, "row", "MSB", "all",
    ),
}


class LSBToolParamDialog(QDialog):
    """lsb_tool action 9 参数 dialog (per v0.5-lsb-tool-unify Phase 4).

    Args:
        parent: 父 widget (通常是 main_window)
        default_mode: 初始 mode ("detect"/"extract"/"extract_bytes")

    Returns (after exec() == Accepted):
        get_kwargs() → {
            "__lsb_mode__": str,
            "__lsb_channels__": str,
            "__lsb_bit__": int,
            "__lsb_scan_order__": str,
            "__lsb_byte_bit_order__": str,
            "__lsb_preset__": str | None,  # 隐写智能分析 模式专用
            "__lsb_text_min_len__": int,
            "__lsb_entropy_threshold__": float,
            "__lsb_unique_threshold__": int,
        }
    """

    def __init__(self, parent=None, default_mode: str = "detect") -> None:
        super().__init__(parent)
        self.setWindowTitle("LSB 隐写分析参数 (lsb_tool)")
        self.setModal(True)
        self.setMinimumWidth(420)

        # ---------- mode selector ----------
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(_MODE_OPTIONS)
        self.mode_combo.setCurrentText(default_mode)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        # ---------- 4 LSB 参数 (所有 mode 共享) ----------
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(_CHANNEL_OPTIONS)
        self.channels_combo.setCurrentText("RGB")  # per LSBToolAction 默认

        self.bit_spin = QSpinBox()
        self.bit_spin.setRange(0, 7)
        self.bit_spin.setValue(0)  # 默认 LSB

        self.scan_order_combo = QComboBox()
        self.scan_order_combo.addItems(_SCAN_ORDER_OPTIONS)
        self.scan_order_combo.setCurrentText("row")

        self.byte_bit_order_combo = QComboBox()
        self.byte_bit_order_combo.addItems(_BYTE_BIT_ORDER_OPTIONS)
        self.byte_bit_order_combo.setCurrentText("MSB")

        # preset_override (隐写智能分析 模式专用)
        self.preset_override_combo = QComboBox()
        self.preset_override_combo.addItems(["None (单组合)", "all (12 组合 + entropy)", "np (G/bit0/col)"])
        self.preset_override_combo.setCurrentIndex(0)
        self.preset_override_combo_label = QLabel("preset (detect 智能):")

        # ---------- 3 detect-only 参数 ----------
        self.text_min_len_spin = QSpinBox()
        self.text_min_len_spin.setRange(1, 10000)
        self.text_min_len_spin.setValue(20)
        self.text_min_len_spin.setToolTip("printable 段最小长度 (默认 20)")

        self.entropy_threshold_spin = QDoubleSpinBox()
        self.entropy_threshold_spin.setRange(0.0, 8.0)
        self.entropy_threshold_spin.setSingleStep(0.1)
        self.entropy_threshold_spin.setValue(5.0)
        self.entropy_threshold_spin.setToolTip("Shannon entropy 阈值 (默认 5.0)")

        self.unique_threshold_spin = QSpinBox()
        self.unique_threshold_spin.setRange(1, 256)
        self.unique_threshold_spin.setValue(200)
        self.unique_threshold_spin.setToolTip("unique byte count 阈值 (默认 200)")

        # detect-only 控件组 (切换 mode 时 show/hide)
        self.detect_group = QGroupBox("detect 模式阈值参数")
        detect_form = QFormLayout()
        detect_form.addRow("text_min_len:", self.text_min_len_spin)
        detect_form.addRow("entropy_threshold:", self.entropy_threshold_spin)
        detect_form.addRow("unique_threshold:", self.unique_threshold_spin)
        detect_form.addRow(self.preset_override_combo_label, self.preset_override_combo)
        self.detect_group.setLayout(detect_form)

        # ---------- Preset 按钮 ----------
        self.preset_button = QPushButton("📌 Preset 一键填")
        self.preset_button.setMenu(self._build_preset_menu())

        # ---------- OK / Cancel ----------
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # ---------- 布局 ----------
        # 主 form (mode + 4 LSB 参数)
        main_form = QFormLayout()
        main_form.addRow("mode (detect/extract/extract_bytes):", self.mode_combo)
        main_form.addRow("通道 (channels):", self.channels_combo)
        main_form.addRow("bit 位 (0=LSB):", self.bit_spin)
        main_form.addRow("扫描顺序 (scan_order):", self.scan_order_combo)
        main_form.addRow("字节内 bit 序:", self.byte_bit_order_combo)

        layout = QVBoxLayout()
        layout.addLayout(main_form)
        layout.addWidget(self.detect_group)

        # preset 行
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("实战预设:"))
        preset_row.addWidget(self.preset_button)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        layout.addWidget(button_box)
        self.setLayout(layout)

        # 初始 mode 显示
        self._on_mode_changed(default_mode)

    # ----- mode 切换 -----

    def _on_mode_changed(self, mode: str) -> None:
        """mode 切换时 show/hide detect-only 控件组.

        detect 模式: 显示 detect_group
        extract / extract_bytes: 隐藏 detect_group
        """
        is_detect = (mode == "detect")
        self.detect_group.setVisible(is_detect)

    # ----- preset -----

    def _build_preset_menu(self) -> QMenu:
        """构造 preset 下拉菜单 (per spec §3.6, 3 个实战 preset)."""
        menu = QMenu(self)
        for preset_name, (mode, channels, bit, scan_order, bbo, preset_override) in PRESETS.items():
            action = menu.addAction(preset_name)
            # 用闭包捕获 preset 值,避免 lambda 循环变量坑
            action.triggered.connect(
                lambda checked=False,
                m=mode, c=channels, b=bit, s=scan_order, bbo=bbo, po=preset_override: self._apply_preset(
                    m, c, b, s, bbo, po
                )
            )
        return menu

    def _apply_preset(
        self,
        mode: str,
        channels: str,
        bit: int,
        scan_order: str,
        byte_bit_order: str,
        preset_override: str | None,
    ) -> None:
        """应用 preset → 填所有控件.

        Args:
            preset_override: None / "all" / "np"
        """
        self.mode_combo.setCurrentText(mode)
        self.channels_combo.setCurrentText(channels)
        self.bit_spin.setValue(bit)
        self.scan_order_combo.setCurrentText(scan_order)
        self.byte_bit_order_combo.setCurrentText(byte_bit_order)
        # preset_override → preset_override_combo index
        po_index = {
            None: 0,
            "all": 1,
            "np": 2,
        }.get(preset_override, 0)
        self.preset_override_combo.setCurrentIndex(po_index)
        # 触发 mode change 显示/隐藏 detect-only
        self._on_mode_changed(mode)

    # ----- get_kwargs -----

    def get_kwargs(self) -> dict[str, Any]:
        """收 9 参数 → chain_runner extra_context.

        Returns:
            dict with __lsb_mode__ / __lsb_channels__ / __lsb_bit__ /
            __lsb_scan_order__ / __lsb_byte_bit_order__ / __lsb_preset__ /
            __lsb_text_min_len__ / __lsb_entropy_threshold__ /
            __lsb_unique_threshold__

            preset_override mapping:
            - index 0 → None
            - index 1 → "all"
            - index 2 → "np"
        """
        po_index = self.preset_override_combo.currentIndex()
        po_map = {0: None, 1: "all", 2: "np"}
        preset_override = po_map.get(po_index)

        return {
            "__lsb_mode__": self.mode_combo.currentText(),
            "__lsb_channels__": self.channels_combo.currentText(),
            "__lsb_bit__": self.bit_spin.value(),
            "__lsb_scan_order__": self.scan_order_combo.currentText(),
            "__lsb_byte_bit_order__": self.byte_bit_order_combo.currentText(),
            "__lsb_preset__": preset_override,
            "__lsb_text_min_len__": self.text_min_len_spin.value(),
            "__lsb_entropy_threshold__": float(self.entropy_threshold_spin.value()),
            "__lsb_unique_threshold__": self.unique_threshold_spin.value(),
        }


__all__ = ["LSBToolParamDialog", "PRESETS"]