# --- DEPRECATED dialog (per v0.5-lsb-tool-unify, 2026-06-29) ---
# 本 dialog 已被 LSBToolParamDialog (gui/lsb_tool_dialog.py, Phase 4) 替代。
# 本 dialog 仍可用 (backward compat for chain lsb-bytes), 但 v0.6+ 删除。
# GUI 工具栏新入口请用 "PNG LSB 隐写分析" → LSBToolParamDialog (9 参数 + 3 mode)。
# 详见 upgrade/v0.5-lsb-tool-unify.md。
# --- /DEPRECATED ---

"""LSB 字节流参数 dialog (v0.5-lsb-bytes-gui)

GUI 第一个带参数的 chain (lsb-bytes),所以单独抽 dialog 模块。

**用法**::

    from automisc.gui.lsb_bytes_dialog import LSBBytesParamDialog

    dialog = LSBBytesParamDialog(parent)
    if dialog.exec() == QDialog.Accepted:
        kwargs = dialog.get_kwargs()  # {__lsb_channels__, __lsb_bit__, ...}
        runner = ChainRunner(chain_name="lsb-bytes", extra_context=kwargs)

**4 个控件**:
- channels: QComboBox (R / G / B / A / RG / RB / GB / RGB / RGBA, 默认 RGB)
- bit: QSpinBox 0..7 (默认 0)
- scan_order: QComboBox (row / col, 默认 row)
- byte_bit_order: QComboBox (MSB / LSB, 默认 MSB)

**Preset 按钮**: 一键填实战常用组合
- "N=NP 默认" → G 通道 / bit 0 / col / MSB (per Owner 06-21 实战)
- "全通道默认" → RGB / bit 0 / row / MSB (per v0.5-lsb-byte-stream-extract 默认)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


# ComboBox items — 跟 lsb_bytes_extract._VALID_CHANNELS 兼容
_CHANNEL_OPTIONS = [
    "R",      # 单通道
    "G",      # N=NP 默认
    "B",
    "A",      # RGBA 用
    "RG",
    "RB",
    "GB",
    "RGB",    # 全通道默认 (per LSBBytesExtractAction 默认)
    "RGBA",
]

_SCAN_ORDER_OPTIONS = ["row", "col"]

_BYTE_BIT_ORDER_OPTIONS = ["MSB", "LSB"]


# Preset 定义 — 一键填实战常用组合
# preset name → (channels, bit, scan_order, byte_bit_order)
PRESETS: dict[str, tuple[str, int, str, str]] = {
    "N=NP 默认 (G 通道 bit 0 col MSB)": ("G", 0, "col", "MSB"),
    "全通道默认 (RGB bit 0 row MSB)": ("RGB", 0, "row", "MSB"),
}


class LSBBytesParamDialog(QDialog):
    """lsb-bytes chain 4 参数 dialog (per v0.5-lsb-bytes-gui Q1=A 拍板).

    Args:
        parent: 父 widget (通常是 main_window)

    Returns (after exec() == Accepted):
        get_kwargs() → {
            "__lsb_channels__": str,
            "__lsb_bit__": int,
            "__lsb_scan_order__": str,
            "__lsb_byte_bit_order__": str,
        }
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LSB 字节流抽取参数 (lsb-bytes)")
        self.setModal(True)
        self.setMinimumWidth(380)

        # ---------- 4 个控件 ----------
        self.channels_combo = QComboBox()
        self.channels_combo.addItems(_CHANNEL_OPTIONS)
        self.channels_combo.setCurrentText("RGB")  # per LSBBytesExtractAction 默认

        self.bit_spin = QSpinBox()
        self.bit_spin.setRange(0, 7)
        self.bit_spin.setValue(0)  # 默认 LSB

        self.scan_order_combo = QComboBox()
        self.scan_order_combo.addItems(_SCAN_ORDER_OPTIONS)
        self.scan_order_combo.setCurrentText("row")

        self.byte_bit_order_combo = QComboBox()
        self.byte_bit_order_combo.addItems(_BYTE_BIT_ORDER_OPTIONS)
        self.byte_bit_order_combo.setCurrentText("MSB")

        # ---------- Preset 按钮 (per Q2=A 拍板) ----------
        self.preset_button = QPushButton("📌 Preset 一键填")
        self.preset_button.setMenu(self._build_preset_menu())

        # ---------- OK / Cancel ----------
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # ---------- 布局 ----------
        form = QFormLayout()
        form.addRow("通道 (channels):", self.channels_combo)
        form.addRow("bit 位 (0=LSB):", self.bit_spin)
        form.addRow("扫描顺序 (scan_order):", self.scan_order_combo)
        form.addRow("字节内 bit 序:", self.byte_bit_order_combo)

        layout = QVBoxLayout()
        layout.addLayout(form)

        # preset 行
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("实战预设:"))
        preset_row.addWidget(self.preset_button)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def _build_preset_menu(self) -> QMenu:
        """构造 preset 下拉菜单 (per Q2=A 拍板, 2 个实战 preset)."""
        menu = QMenu(self)
        for preset_name, (channels, bit, scan_order, byte_bit_order) in PRESETS.items():
            action = menu.addAction(preset_name)
            # 用闭包捕获 preset 值,避免 lambda 循环变量坑
            action.triggered.connect(
                lambda checked=False,
                c=channels, b=bit, s=scan_order, bbo=byte_bit_order: self._apply_preset(
                    c, b, s, bbo
                )
            )
        return menu

    def _apply_preset(
        self, channels: str, bit: int, scan_order: str, byte_bit_order: str
    ) -> None:
        """应用 preset → 填 4 个控件."""
        self.channels_combo.setCurrentText(channels)
        self.bit_spin.setValue(bit)
        self.scan_order_combo.setCurrentText(scan_order)
        self.byte_bit_order_combo.setCurrentText(byte_bit_order)

    def get_kwargs(self) -> dict[str, Any]:
        """收 4 参数 → chain_runner extra_context.

        Returns:
            dict with __lsb_channels__ / __lsb_bit__ / __lsb_scan_order__ / __lsb_byte_bit_order__
            (per v0.5-steghide-GUI __wordlist__/__password__ 风格带 __ 前缀)
        """
        return {
            "__lsb_channels__": self.channels_combo.currentText(),
            "__lsb_bit__": self.bit_spin.value(),
            "__lsb_scan_order__": self.scan_order_combo.currentText(),
            "__lsb_byte_bit_order__": self.byte_bit_order_combo.currentText(),
        }


__all__ = ["LSBBytesParamDialog", "PRESETS"]