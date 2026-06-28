"""Unit tests for v0.5-lsb-tool-unify Phase 4 (lsb_tool_dialog).

per spec §3.10 GUI 集成:
- 9 参数 dialog: mode + 4 LSB + preset_override + 3 detect-only
- detect-only 控件 (text_min_len / entropy_threshold / unique_threshold) 在 mode=detect 时显示
- 3 preset: N=NP 默认 / 全通道默认 / 隐写智能分析
- 默认 mode=detect, channels=RGB, bit=0, scan=row, bbo=MSB
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from automisc.gui.lsb_tool_dialog import LSBToolParamDialog, PRESETS


# ---------- 默认值测试 ----------
class TestLSBToolDialogDefaults:
    """LSBToolParamDialog 默认值跟 LSBToolAction 默认值一致."""

    def test_default_mode(self, qtbot):
        """默认 mode=detect (per spec §3.10 'PNG LSB 隐写分析' 默认 detect)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_mode__"] == "detect"

    def test_default_lsb_params(self, qtbot):
        """默认 channels=RGB / bit=0 / scan=row / bbo=MSB (per LSBToolAction)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_channels__"] == "RGB"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "row"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"

    def test_default_preset_override(self, qtbot):
        """默认 preset_override=None (单组合, 非 'all' / 'np')."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_preset__"] is None

    def test_default_detect_thresholds(self, qtbot):
        """默认 text_min_len=20 / entropy_threshold=5.0 / unique_threshold=200 (per LSBToolAction)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_text_min_len__"] == 20
        assert kwargs["__lsb_entropy_threshold__"] == 5.0
        assert kwargs["__lsb_unique_threshold__"] == 200

    def test_default_mode_constructor_param(self, qtbot):
        """default_mode='extract' 构造 → mode=extract."""
        dialog = LSBToolParamDialog(default_mode="extract")
        qtbot.addWidget(dialog)

        assert dialog.get_kwargs()["__lsb_mode__"] == "extract"

    def test_get_kwargs_has_9_keys(self, qtbot):
        """get_kwargs 返回 9 个 __lsb_* key (跟 LSBToolAction __init__ 对齐)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        expected_keys = {
            "__lsb_mode__",
            "__lsb_channels__",
            "__lsb_bit__",
            "__lsb_scan_order__",
            "__lsb_byte_bit_order__",
            "__lsb_preset__",
            "__lsb_text_min_len__",
            "__lsb_entropy_threshold__",
            "__lsb_unique_threshold__",
        }
        assert set(kwargs.keys()) == expected_keys, (
            f"expected 9 keys, got {set(kwargs.keys()) - expected_keys} extra, "
            f"{expected_keys - set(kwargs.keys())} missing"
        )


# ---------- mode 切换 / detect-only 可见性测试 ----------
class TestLSBToolDialogModeSwitch:
    """切换 mode 时 detect-only 控件 show/hide.

    注: Qt 的 isVisible() 需要 show() 后才返回 True, 测试用 isHidden() 替代
    (isHidden 反映 setVisible 调用状态, 不依赖 show 周期).
    """

    def test_detect_mode_shows_detect_group(self, qtbot):
        """mode=detect 时 detect_group 显示 (isHidden=False)."""
        dialog = LSBToolParamDialog(default_mode="detect")
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is False

    def test_extract_mode_hides_detect_group(self, qtbot):
        """mode=extract 时 detect_group 隐藏 (isHidden=True)."""
        dialog = LSBToolParamDialog(default_mode="extract")
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is True

    def test_extract_bytes_mode_hides_detect_group(self, qtbot):
        """mode=extract_bytes 时 detect_group 隐藏."""
        dialog = LSBToolParamDialog(default_mode="extract_bytes")
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is True

    def test_switch_detect_to_extract_hides(self, qtbot):
        """运行时切换 detect → extract, detect_group 隐藏."""
        dialog = LSBToolParamDialog(default_mode="detect")
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is False  # 初始 detect
        dialog.mode_combo.setCurrentText("extract")
        assert dialog.detect_group.isHidden() is True

    def test_switch_extract_to_detect_shows(self, qtbot):
        """运行时切换 extract → detect, detect_group 显示."""
        dialog = LSBToolParamDialog(default_mode="extract")
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is True  # 初始 extract
        dialog.mode_combo.setCurrentText("detect")
        assert dialog.detect_group.isHidden() is False

    def test_get_kwargs_returns_detect_thresholds_when_hidden(self, qtbot):
        """mode=extract 时 detect-only 控件隐藏, 但 get_kwargs 仍返回这些值."""
        dialog = LSBToolParamDialog(default_mode="extract")
        qtbot.addWidget(dialog)

        # detect 控件隐藏但 kwargs 仍含 (per spec §3.10 9 参数接口固定)
        kwargs = dialog.get_kwargs()
        assert "__lsb_text_min_len__" in kwargs
        assert "__lsb_entropy_threshold__" in kwargs
        assert "__lsb_unique_threshold__" in kwargs


# ---------- preset 测试 ----------
class TestLSBToolDialogPresets:
    """3 个实战 preset 一键填 (per spec §3.6)."""

    def test_np_preset(self, qtbot):
        """'N=NP 默认' → mode=extract + G/bit0/col/MSB (per v0.5-train-009)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog._apply_preset(*PRESETS["N=NP 默认 (extract + G/bit0/col/MSB)"])

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_mode__"] == "extract"
        assert kwargs["__lsb_channels__"] == "G"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "col"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"
        assert kwargs["__lsb_preset__"] is None

    def test_all_channels_preset(self, qtbot):
        """'全通道默认' → mode=detect + RGB/bit0/row/MSB (per spec §3.6)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog._apply_preset(*PRESETS["全通道默认 (detect + RGB/bit0/row/MSB)"])

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_mode__"] == "detect"
        assert kwargs["__lsb_channels__"] == "RGB"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "row"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"
        assert kwargs["__lsb_preset__"] is None

    def test_smart_detect_preset(self, qtbot):
        """'隐写智能分析' → mode=detect + RGB/bit0/row/MSB + preset='all' (per spec §3.5)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog._apply_preset(*PRESETS["隐写智能分析 (detect + preset=all + RGB)"])

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_mode__"] == "detect"
        assert kwargs["__lsb_channels__"] == "RGB"
        assert kwargs["__lsb_preset__"] == "all"

    def test_preset_switches_mode_shows_detect_group(self, qtbot):
        """preset 切到 detect mode 时 detect_group 显示."""
        dialog = LSBToolParamDialog(default_mode="extract")  # 初始 extract → detect_group 隐藏
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is True
        dialog._apply_preset(*PRESETS["全通道默认 (detect + RGB/bit0/row/MSB)"])
        assert dialog.detect_group.isHidden() is False

    def test_preset_switches_mode_hides_detect_group(self, qtbot):
        """preset 切到 extract mode 时 detect_group 隐藏."""
        dialog = LSBToolParamDialog(default_mode="detect")  # 初始 detect → detect_group 显示
        qtbot.addWidget(dialog)

        assert dialog.detect_group.isHidden() is False
        dialog._apply_preset(*PRESETS["N=NP 默认 (extract + G/bit0/col/MSB)"])
        assert dialog.detect_group.isHidden() is True


# ---------- preset_override combo 测试 ----------
class TestLSBToolDialogPresetOverrideCombo:
    """preset_override QComboBox → preset_override 字段映射."""

    def test_preset_override_index_0_is_none(self, qtbot):
        """index 0 (None 单组合) → preset_override=None."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.preset_override_combo.setCurrentIndex(0)
        assert dialog.get_kwargs()["__lsb_preset__"] is None

    def test_preset_override_index_1_is_all(self, qtbot):
        """index 1 (all 12 组合) → preset_override='all'."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.preset_override_combo.setCurrentIndex(1)
        assert dialog.get_kwargs()["__lsb_preset__"] == "all"

    def test_preset_override_index_2_is_np(self, qtbot):
        """index 2 (np G/bit0/col) → preset_override='np'."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.preset_override_combo.setCurrentIndex(2)
        assert dialog.get_kwargs()["__lsb_preset__"] == "np"


# ---------- 参数类型测试 ----------
class TestLSBToolDialogParamTypes:
    """get_kwargs 返回值类型必须正确 (per chain_runner.py 透传给 LSBToolAction)."""

    def test_bit_is_int(self, qtbot):
        """__lsb_bit__ 是 int (QSpinBox → int)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.bit_spin.setValue(3)
        assert isinstance(dialog.get_kwargs()["__lsb_bit__"], int)
        assert dialog.get_kwargs()["__lsb_bit__"] == 3

    def test_text_min_len_is_int(self, qtbot):
        """__lsb_text_min_len__ 是 int."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.text_min_len_spin.setValue(50)
        assert isinstance(dialog.get_kwargs()["__lsb_text_min_len__"], int)
        assert dialog.get_kwargs()["__lsb_text_min_len__"] == 50

    def test_entropy_threshold_is_float(self, qtbot):
        """__lsb_entropy_threshold__ 是 float (QDoubleSpinBox → float)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.entropy_threshold_spin.setValue(3.5)
        assert isinstance(dialog.get_kwargs()["__lsb_entropy_threshold__"], float)
        assert dialog.get_kwargs()["__lsb_entropy_threshold__"] == 3.5

    def test_unique_threshold_is_int(self, qtbot):
        """__lsb_unique_threshold__ 是 int."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.unique_threshold_spin.setValue(100)
        assert isinstance(dialog.get_kwargs()["__lsb_unique_threshold__"], int)
        assert dialog.get_kwargs()["__lsb_unique_threshold__"] == 100

    def test_preset_override_none_type(self, qtbot):
        """__lsb_preset__ None 是 NoneType (非空字符串)."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        dialog.preset_override_combo.setCurrentIndex(0)
        assert dialog.get_kwargs()["__lsb_preset__"] is None


# ---------- module-level PRESETS 常量测试 ----------
class TestLSBToolDialogPresetsConstant:
    """PRESETS dict 包含 spec §3.6 规定的 3 个 preset."""

    def test_presets_has_3_entries(self):
        """PRESETS 包含 3 个实战 preset."""
        assert len(PRESETS) == 3

    def test_presets_keys_match_spec(self):
        """PRESETS keys 跟 spec §3.6 一致."""
        expected = {
            "N=NP 默认 (extract + G/bit0/col/MSB)",
            "全通道默认 (detect + RGB/bit0/row/MSB)",
            "隐写智能分析 (detect + preset=all + RGB)",
        }
        assert set(PRESETS.keys()) == expected