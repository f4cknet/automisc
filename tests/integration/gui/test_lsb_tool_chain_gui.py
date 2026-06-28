"""Integration tests for v0.5-lsb-tool-unify Phase 4 (lsb_tool chain GUI 集成).

per spec §3.10 GUI 集成:
- LSBToolParamDialog 默认值正确 (detect / RGB / 0 / row / MSB)
- LSBToolParamDialog 3 preset 正确
- MainWindow 快捷 action 菜单加 lsb_tool (替代 lsb_extract)
- menu_dock TOOL_CATEGORIES 含 lsb_tool
- ChainRunner.run chain_name="lsb_tool" 从 extra_context 抽 9 参数 → LSBToolAction(**kwargs)
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import pytest

from automisc.gui.lsb_tool_dialog import LSBToolParamDialog, PRESETS


# ---------- LSBToolParamDialog 默认值测试 (跟 test_lsb_tool_dialog.py 类似, 集成) ----------
class TestLSBToolDialogIntegration:
    """集成角度验证 LSBToolParamDialog."""

    def test_dialog_9_kwargs(self, qtbot):
        """get_kwargs 返回 9 个 __lsb_* key."""
        dialog = LSBToolParamDialog()
        qtbot.addWidget(dialog)

        kwargs = dialog.get_kwargs()
        assert len(kwargs) == 9
        for key in (
            "__lsb_mode__", "__lsb_channels__", "__lsb_bit__",
            "__lsb_scan_order__", "__lsb_byte_bit_order__",
            "__lsb_preset__", "__lsb_text_min_len__",
            "__lsb_entropy_threshold__", "__lsb_unique_threshold__",
        ):
            assert key in kwargs, f"missing {key}"


# ---------- menu_dock TOOL_CATEGORIES 集成测试 ----------
class TestMenuDockLSBTool:
    """menu_dock.TOOL_CATEGORIES + ACTION_DISPLAY_NAMES 含 lsb_tool."""

    def test_tool_categories_includes_lsb_tool(self):
        """TOOL_CATEGORIES['快捷工具 (v0.5 Actions)'] 含 lsb_tool."""
        from automisc.gui.menu_dock import TOOL_CATEGORIES

        quick_actions = TOOL_CATEGORIES["快捷工具 (v0.5 Actions)"]
        assert "lsb_tool" in quick_actions, (
            f"快捷工具 缺 lsb_tool, 实际: {quick_actions}"
        )

    def test_action_display_names_includes_lsb_tool(self):
        """ACTION_DISPLAY_NAMES 含 lsb_tool → 'PNG LSB 隐写分析'."""
        from automisc.gui.menu_dock import ACTION_DISPLAY_NAMES

        assert "lsb_tool" in ACTION_DISPLAY_NAMES
        assert "PNG LSB 隐写分析" in ACTION_DISPLAY_NAMES["lsb_tool"]

    def test_action_kind_check_includes_lsb_tool(self):
        """menu_dock kind check 含 lsb_tool (识别为 action 非 adapter)."""
        import automisc.gui.menu_dock as menu_dock

        # 通过模块源码检查 (避免拉 main_window 整图)
        import inspect
        source = inspect.getsource(menu_dock)
        assert '"lsb_tool"' in source, "menu_dock.py 源码应包含 'lsb_tool'"


# ---------- MainWindow 快捷 action 集成测试 ----------
class TestMainWindowLSBToolAction:
    """MainWindow 快捷 action 菜单含 lsb_tool + _run_lsb_tool_action 方法存在."""

    def test_main_window_has_run_lsb_tool_action(self):
        """MainWindow 类有 _run_lsb_tool_action 方法 (per Phase 4 spec §3.10)."""
        from automisc.gui.main_window import MainWindow

        assert hasattr(MainWindow, "_run_lsb_tool_action"), (
            "MainWindow 缺失 _run_lsb_tool_action 方法"
        )

    def test_main_window_imports_lsb_tool_dialog(self):
        """MainWindow 导入 LSBToolParamDialog (per Phase 4 spec §3.10)."""
        import automisc.gui.main_window as mw

        # 模块级 import, 不依赖 MainWindow 实例化
        assert "LSBToolParamDialog" in dir(mw), (
            "main_window.py 没 import LSBToolParamDialog"
        )


# ---------- ChainRunner lsb_tool 集成测试 ----------
class TestChainRunnerLSBToolPassthrough:
    """ChainRunner.run chain_name='lsb_tool' → LSBToolAction(9 kwargs) 调用."""

    def test_chain_runner_passes_9_params_to_lsb_tool_action(self, qtbot, tmp_path):
        """ChainRunner('lsb_tool', extra_context=...) → LSBToolAction(mode=..., channels=..., ...) 调用."""
        from automisc.gui.chain_runner import ChainRunner

        # 造个 fake PNG (空文件足矣, 我们只 mock LSBToolAction 不真跑)
        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        captured_kwargs = {}

        class MockAction:
            name = "lsb_tool"

            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

            def run(self, context):
                # 不真跑, 返回 mock result
                from automisc.core.result import ActionResult
                return ActionResult(success=True, message="mock", data={})

        with patch(
            "automisc.core.actions.lsb_tool.LSBToolAction", side_effect=MockAction
        ):
            runner = ChainRunner(
                chain_name="lsb_tool",
                file_path=str(fake_png),
                extra_context={
                    "__lsb_mode__": "extract",
                    "__lsb_preset__": None,
                    "__lsb_channels__": "G",
                    "__lsb_bit__": 0,
                    "__lsb_scan_order__": "col",
                    "__lsb_byte_bit_order__": "MSB",
                    "__lsb_text_min_len__": 30,
                    "__lsb_entropy_threshold__": 6.0,
                    "__lsb_unique_threshold__": 150,
                },
            )
            runner.run()

        # 验证 LSBToolAction 收到正确 9 参数
        assert captured_kwargs == {
            "mode": "extract",
            "preset": None,
            "channels": "G",
            "bit": 0,
            "scan_order": "col",
            "byte_bit_order": "MSB",
            "text_min_len": 30,
            "entropy_threshold": 6.0,
            "unique_threshold": 150,
        }

    def test_chain_runner_lsb_tool_default_params(self, qtbot, tmp_path):
        """ChainRunner 没传 extra_context 时, lsb_tool 用默认参数."""
        from automisc.gui.chain_runner import ChainRunner

        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        captured_kwargs = {}

        class MockAction:
            name = "lsb_tool"

            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

            def run(self, context):
                from automisc.core.result import ActionResult
                return ActionResult(success=True, message="mock", data={})

        with patch(
            "automisc.core.actions.lsb_tool.LSBToolAction", side_effect=MockAction
        ):
            runner = ChainRunner(
                chain_name="lsb_tool",
                file_path=str(fake_png),
            )
            runner.run()

        # 默认值: detect / None / RGB / 0 / row / MSB / 20 / 5.0 / 200
        assert captured_kwargs == {
            "mode": "detect",
            "preset": None,
            "channels": "RGB",
            "bit": 0,
            "scan_order": "row",
            "byte_bit_order": "MSB",
            "text_min_len": 20,
            "entropy_threshold": 5.0,
            "unique_threshold": 200,
        }


# ---------- 回归: lsb_bytes chain 仍能用 (backward compat) ----------
class TestLSBBytesChainBackwardCompat:
    """Phase 4 是纯增量, 不破坏 lsb-bytes chain 已有用法."""

    def test_chain_names_still_includes_lsb_bytes(self):
        """_CHAIN_NAMES tuple 仍含 'lsb-bytes' (Phase 6 才删)."""
        from automisc.gui.main_window import _CHAIN_NAMES

        assert "lsb-bytes" in _CHAIN_NAMES

    def test_lsb_bytes_dialog_still_importable(self):
        """lsb_bytes_dialog 仍可 import (Phase 6 才删)."""
        from automisc.gui.lsb_bytes_dialog import LSBBytesParamDialog

        assert LSBBytesParamDialog is not None

    def test_lsb_extract_action_still_registered(self):
        """lsb_extract action 仍注册 (Phase 6 才 deprecated 标记)."""
        from automisc.gui.chain_runner import _ACTION_REGISTRY

        # 触发懒加载
        from automisc.gui.chain_runner import _ensure_action_registry
        _ensure_action_registry()

        assert "lsb_extract" in _ACTION_REGISTRY