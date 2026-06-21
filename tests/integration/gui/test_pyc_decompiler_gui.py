"""Integration tests for v0.5-pyc-decompiler-gui (pyc_decompiler 显示在 GUI 工具栏).

- ToolMenuDock._populate() 渲染 "🐍 反编译工具" 分类
- "🐍 Pyc 反编译 (默认 Python 2)" 显示名正确
- tool name = "decoder:pyc_decompiler", click 触发 on_tool_selected callback
- 解码流程跑通 (mock .pyc 输入)
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path


# ---------- ToolMenuDock 渲染测试 ----------
class TestPycDecompilerInMenuDock:
    """v0.5-pyc-decompiler-gui: pyc_decompiler 必须在 GUI 工具栏显示."""

    def test_pyc_decompiler_category_exists(self, qtbot):
        """ToolMenuDock 必须有 '🐍 反编译工具' 分类."""
        from automisc.gui.menu_dock import ToolMenuDock

        clicked = []

        def on_select(name, kind):
            clicked.append((name, kind))

        # 触发 pyc_decompiler 注册 (import side effect)
        from automisc.core.decoders import pyc_decompiler  # noqa: F401

        dock = ToolMenuDock(on_tool_selected=on_select)
        qtbot.addWidget(dock)

        # 验证 "🐍 反编译工具" 分类存在
        categories_text = []
        for i in range(dock.tree.topLevelItemCount()):
            categories_text.append(dock.tree.topLevelItem(i).text(0))

        assert any("反编译工具" in cat for cat in categories_text), (
            f"'🐍 反编译工具' 分类缺失, 实际分类: {categories_text}"
        )

    def test_pyc_decompiler_tool_exists(self, qtbot):
        """'🐍 Pyc 反编译 (默认 Python 2)' 工具必须在菜单中."""
        from automisc.gui.menu_dock import ToolMenuDock

        # 触发 pyc_decompiler 注册
        from automisc.core.decoders import pyc_decompiler  # noqa: F401

        dock = ToolMenuDock(on_tool_selected=lambda n, k: None)
        qtbot.addWidget(dock)

        # 找 pyc_decompiler tool name
        all_tools = []
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                tool_name = child.data(0, 0x0100)  # Qt.UserRole
                all_tools.append((cat_item.text(0), tool_name, child.text(0)))

        # 验证 "decoder:pyc_decompiler" 在列表里
        assert any(
            t[1] == "decoder:pyc_decompiler" for t in all_tools
        ), f"pyc_decompiler 缺失, 实际工具: {all_tools}"

    def test_pyc_decompiler_display_name_indicates_py2(self, qtbot):
        """显示名必须标明 '默认 Python 2' (per Owner 06-21 11:54 决策)."""
        from automisc.gui.menu_dock import ToolMenuDock

        # 触发 pyc_decompiler 注册
        from automisc.core.decoders import pyc_decompiler  # noqa: F401

        dock = ToolMenuDock(on_tool_selected=lambda n, k: None)
        qtbot.addWidget(dock)

        # 找 pyc_decompiler 显示名
        pyc_display = None
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler":
                    pyc_display = child.text(0)
                    break

        assert pyc_display is not None
        # 显示名应该标明 "Python 2" 默认 (per Owner 决策)
        assert "Python 2" in pyc_display, f"显示名应标明 'Python 2', 实际: {pyc_display}"
        assert "🐍" in pyc_display, f"显示名应该有 🐍 emoji, 实际: {pyc_display}"

    def test_pyc_decompiler_click_triggers_callback(self, qtbot):
        """点击 pyc_decompiler 工具触发 on_tool_selected callback."""
        from automisc.gui.menu_dock import ToolMenuDock

        clicked = []

        def on_select(name, kind):
            clicked.append((name, kind))

        # 触发 pyc_decompiler 注册
        from automisc.core.decoders import pyc_decompiler  # noqa: F401

        dock = ToolMenuDock(on_tool_selected=on_select)
        qtbot.addWidget(dock)

        # 模拟点击 pyc_decompiler tool
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler":
                    dock._on_item_clicked(child, 0)
                    break

        # 验证 callback 触发
        assert clicked == [("pyc_decompiler", "decoder")], f"callback 异常: {clicked}"


# ---------- decoder run 集成测试 ----------
class TestPycDecompilerRun:
    """pyc_decompiler 跑 .pyc 文件反编译."""

    def test_run_on_real_writeup_literal_pyc(self, qtbot):
        """Owner 06-21 11:24 smoke 阶段生成的 writeup 字面 .pyc (115745 bytes).

        如果文件不存在, 跳过 (fixture 依赖 Owner 之前跑过 smoke).
        """
        pyc_path = Path("/tmp/writeup_literal.pyc")
        if not pyc_path.exists():
            pytest.skip("/tmp/writeup_literal.pyc 不存在, Owner 06-21 11:24 smoke 阶段生成过")

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        result = run_pyc_decompiler(str(pyc_path))
        assert result.success
        assert result.method == "uncompyle6"  # 默认走 Py2.x
        assert result.version == (2, 7)
        assert "def encrypt" in result.source_code
        assert "KEY1" in result.source_code
        assert "KEY2" in result.source_code
