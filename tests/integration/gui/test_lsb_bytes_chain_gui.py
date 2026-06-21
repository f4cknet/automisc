"""Integration tests for v0.5-lsb-bytes-gui (lsb-bytes chain GUI 集成).

- LSBBytesParamDialog 默认值正确 (RGB / 0 / row / MSB)
- LSBBytesParamDialog "N=NP 默认" preset → G 通道 bit 0 col MSB
- LSBBytesParamDialog "全通道默认" preset → RGB bit 0 row MSB
- MainWindow._CHAIN_NAMES 含 "lsb-bytes"
- ChainRunner.run 透传 4 参数到 build_lsb_bytes_chain
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import pytest

from automisc.gui.lsb_bytes_dialog import LSBBytesParamDialog, PRESETS


# ---------- LSBBytesParamDialog 单元测试 ----------
class TestLSBBytesParamDialogDefaults:
    """dialog 默认值跟 LSBBytesExtractAction 默认值一致."""

    def test_dialog_default_values(self, qtbot):
        """dialog 默认 = RGB / 0 / row / MSB (per LSBBytesExtractAction 默认)."""
        dialog = LSBBytesParamDialog()
        qtbot.addWidget(dialog)

        # get_kwargs 不依赖 exec, 直接读控件当前值
        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_channels__"] == "RGB"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "row"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"


class TestLSBBytesParamDialogPresets:
    """preset 一键填实战常用组合 (per Owner 06-21 实战)."""

    def test_np_preset(self, qtbot):
        """'N=NP 默认' → G 通道 bit 0 col MSB (Owner 实战触发需求)."""
        dialog = LSBBytesParamDialog()
        qtbot.addWidget(dialog)

        # 模拟点 preset 菜单
        dialog._apply_preset(*PRESETS["N=NP 默认 (G 通道 bit 0 col MSB)"])

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_channels__"] == "G"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "col"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"

    def test_all_channels_preset(self, qtbot):
        """'全通道默认' → RGB bit 0 row MSB (per LSBBytesExtractAction 默认)."""
        dialog = LSBBytesParamDialog()
        qtbot.addWidget(dialog)

        dialog._apply_preset(*PRESETS["全通道默认 (RGB bit 0 row MSB)"])

        kwargs = dialog.get_kwargs()
        assert kwargs["__lsb_channels__"] == "RGB"
        assert kwargs["__lsb_bit__"] == 0
        assert kwargs["__lsb_scan_order__"] == "row"
        assert kwargs["__lsb_byte_bit_order__"] == "MSB"


# ---------- MainWindow._CHAIN_NAMES 集成测试 ----------
class TestMainWindowChainMenu:
    """MainWindow _CHAIN_NAMES 包含 lsb-bytes (per v0.5-lsb-bytes-gui Q3=A 拍板)."""

    def test_chain_names_includes_lsb_bytes(self):
        """_CHAIN_NAMES tuple 必须含 'lsb-bytes'."""
        from automisc.gui.main_window import _CHAIN_NAMES

        assert "lsb-bytes" in _CHAIN_NAMES, (
            f"_CHAIN_NAMES 缺失 lsb-bytes, 实际: {_CHAIN_NAMES}"
        )

    def test_lsb_bytes_comes_after_lsb(self):
        """lsb-bytes 排在 lsb 后面 (跟 spec §4.2 OUT 一致)."""
        from automisc.gui.main_window import _CHAIN_NAMES

        assert _CHAIN_NAMES.index("lsb-bytes") > _CHAIN_NAMES.index("lsb")


# ---------- ChainRunner.run 透传测试 ----------
class TestChainRunnerLSBBytesPassthrough:
    """ChainRunner.run 把 extra_context 4 参数透传给 build_lsb_bytes_chain."""

    def test_chain_runner_passes_4_params_to_builder(self, qtbot, tmp_path):
        """ChainRunner(chain_name='lsb-bytes', extra_context=...) → build_lsb_bytes_chain(channels=..., ...) 调用."""
        from automisc.gui.chain_runner import ChainRunner

        # 造个 fake PNG (空文件足矣, 我们只 mock builder 不真跑)
        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        captured_kwargs = {}

        def mock_builder(channels=None, bit=0, scan_order="row", byte_bit_order="MSB"):
            captured_kwargs["channels"] = channels
            captured_kwargs["bit"] = bit
            captured_kwargs["scan_order"] = scan_order
            captured_kwargs["byte_bit_order"] = byte_bit_order
            # 返回一个不会真执行的 mock DAG
            from unittest.mock import MagicMock
            dag = MagicMock()
            dag.execute = lambda ctx: ctx
            return dag

        with patch(
            "automisc.core.chains.build_lsb_bytes_chain", side_effect=mock_builder
        ):
            runner = ChainRunner(
                chain_name="lsb-bytes",
                file_path=str(fake_png),
                extra_context={
                    "__lsb_channels__": "G",
                    "__lsb_bit__": 0,
                    "__lsb_scan_order__": "col",
                    "__lsb_byte_bit_order__": "MSB",
                },
            )
            runner.run()

        # 验证 build_lsb_bytes_chain 收到正确参数
        assert captured_kwargs == {
            "channels": "G",
            "bit": 0,
            "scan_order": "col",
            "byte_bit_order": "MSB",
        }

    def test_chain_runner_lsb_bytes_default_params(self, qtbot, tmp_path):
        """ChainRunner 没传 extra_context 时, lsb-bytes 用默认参数 (RGB / 0 / row / MSB)."""
        from automisc.gui.chain_runner import ChainRunner

        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        captured_kwargs = {}

        def mock_builder(channels=None, bit=0, scan_order="row", byte_bit_order="MSB"):
            captured_kwargs["channels"] = channels
            captured_kwargs["bit"] = bit
            captured_kwargs["scan_order"] = scan_order
            captured_kwargs["byte_bit_order"] = byte_bit_order
            from unittest.mock import MagicMock
            dag = MagicMock()
            dag.execute = lambda ctx: ctx
            return dag

        with patch(
            "automisc.core.chains.build_lsb_bytes_chain", side_effect=mock_builder
        ):
            runner = ChainRunner(
                chain_name="lsb-bytes",
                file_path=str(fake_png),
                # 不传 extra_context → 默认
            )
            runner.run()

        # 默认值
        assert captured_kwargs["channels"] is None
        assert captured_kwargs["bit"] == 0
        assert captured_kwargs["scan_order"] == "row"
        assert captured_kwargs["byte_bit_order"] == "MSB"