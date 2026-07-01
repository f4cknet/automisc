"""Integration tests for v0.5-pyc-decompiler-gui + v0.5-pyc-decompiler-buttons.

**v0.5-pyc-decompiler-gui (per Owner 06-21 11:54)**:
- ToolMenuDock._populate() 渲染 "🐍 反编译工具" 分类
- "🐍 Pyc 反编译 (默认 Python 2)" 显示名正确 (v0.5-pyc-decompiler-buttons 后改为 "🐍 Pyc 反编译 (自动判版本)")
- tool name = "decoder:pyc_decompiler", click 触发 on_tool_selected callback

**v0.5-pyc-decompiler-buttons (per Owner 2026-07-01 09:02)**:
- 加 2 强制版本按钮: "decoder:pyc_decompiler:py2" / "decoder:pyc_decompiler:py3"
- 显示名: "🐍 Pyc 反编译 (强制 Python 2)" / "🐍 Pyc 反编译 (强制 Python 3)"
- click dispatch: on_tool_selected 收到 name 含 `:py2` / `:py3` 后缀 (main_window 解析)

**TestPycDecompilerRun 是 owner-specific smoke 测试**:
- 依赖 `/tmp/writeup_literal.pyc` (Owner 06-21 11:24 smoke 生成) 或 v0.5-train-019 实战 flag.pyc
- 默认 skip (env RUN_PYC_SMOKE=1 启用)
- pytest 全套跑时跟其他 GUI 集成测试有资源竞争风险 (触发 SIGABRT)
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path


# opt-in 环境变量: 默认 skip,避免 pytest tests/ 全套跑时触发 SIGABRT
RUN_PYC_SMOKE = os.environ.get("RUN_PYC_SMOKE") == "1"


# v0.5-pyc-decompiler-buttons: 多路径找真实 Py2.7 pyc (跟 unit test 同步)
def _find_real_py27_pyc() -> Path | None:
    candidates = [
        Path("/tmp/writeup_literal.pyc"),
        Path(r"C:\Users\zmzsg\Downloads\flag\C!_Users_zmzsg_Downloads_flag_flag.txt!flag.pyc"),
        Path(__file__).parent.parent.parent / "unit" / "core" / "decoders" / "fixtures" / "challenges" / "flag_755b_py27.pyc",  # fallback
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


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
        """'🐍 Pyc 反编译 (自动判版本)' 工具必须在菜单中 (v0.5-pyc-decompiler-buttons 改显示名)."""
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

    def test_pyc_decompiler_display_name_indicates_auto(self, qtbot):
        """显示名必须标明 '自动判版本' (v0.5-pyc-decompiler-buttons 改默认显示名).

        v0.5-pyc-decompiler-gui 旧显示名 "(默认 Python 2)" 已废弃, 跟新 2 强制按钮语义冲突.
        """
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
        # v0.5-pyc-decompiler-buttons: 显示名改为 "自动判版本"
        assert "自动判版本" in pyc_display, f"显示名应标明 '自动判版本', 实际: {pyc_display}"
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

        # 验证 callback 触发 (无后缀, kind=decoder)
        assert clicked == [("pyc_decompiler", "decoder")], f"callback 异常: {clicked}"


# ---------- v0.5-pyc-decompiler-buttons: 3 按钮 + click dispatch 解析后缀 ----------
class TestPycDecompilerButtons:
    """v0.5-pyc-decompiler-buttons: 工具栏 3 按钮 (auto / py2 / py3) + click dispatch."""

    def test_three_pyc_buttons_in_menu(self, qtbot):
        """'🐍 反编译工具' 分类必须有 3 个 entry: auto / py2 / py3."""
        from automisc.gui.menu_dock import ToolMenuDock

        # 触发 pyc_decompiler 注册
        from automisc.core.decoders import pyc_decompiler  # noqa: F401

        dock = ToolMenuDock(on_tool_selected=lambda n, k: None)
        qtbot.addWidget(dock)

        # 找 "🐍 反编译工具" 分类下所有 tool
        pyc_tools = []
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            if "反编译工具" not in cat_item.text(0):
                continue
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                tool_name = child.data(0, 0x0100)
                pyc_tools.append((tool_name, child.text(0)))

        # 3 按钮都在
        expected = {
            "decoder:pyc_decompiler",
            "decoder:pyc_decompiler:py2",
            "decoder:pyc_decompiler:py3",
        }
        actual = {t[0] for t in pyc_tools}
        assert expected == actual, (
            f"pyc 按钮不全, 期望 {expected}, 实际 {actual}, 详情 {pyc_tools}"
        )

    def test_py2_button_display_name(self, qtbot):
        """强制 py2 按钮显示名 '🐍 Pyc 反编译 (强制 Python 2)'."""
        from automisc.gui.menu_dock import ToolMenuDock

        from automisc.core.decoders import pyc_decompiler  # noqa: F401
        dock = ToolMenuDock(on_tool_selected=lambda n, k: None)
        qtbot.addWidget(dock)

        # 找 "decoder:pyc_decompiler:py2" 的显示名
        display = None
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            if "反编译工具" not in cat_item.text(0):
                continue
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler:py2":
                    display = child.text(0)
                    break

        assert display is not None, "强制 py2 按钮缺失"
        assert "强制 Python 2" in display, f"显示名应含 '强制 Python 2', 实际: {display}"
        assert "🐍" in display

    def test_py3_button_display_name(self, qtbot):
        """强制 py3 按钮显示名 '🐍 Pyc 反编译 (强制 Python 3)'."""
        from automisc.gui.menu_dock import ToolMenuDock

        from automisc.core.decoders import pyc_decompiler  # noqa: F401
        dock = ToolMenuDock(on_tool_selected=lambda n, k: None)
        qtbot.addWidget(dock)

        display = None
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            if "反编译工具" not in cat_item.text(0):
                continue
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler:py3":
                    display = child.text(0)
                    break

        assert display is not None, "强制 py3 按钮缺失"
        assert "强制 Python 3" in display, f"显示名应含 '强制 Python 3', 实际: {display}"
        assert "🐍" in display

    def test_click_py2_button_keeps_suffix_in_callback(self, qtbot):
        """点击强制 py2 按钮 → callback 收到 name='pyc_decompiler:py2' (后缀保留).

        main_window._run_decoder 负责解析后缀 → force_version=2 → DecodeRunner.
        menu_dock 只负责 entry + click, 解析后缀不在 menu_dock 范围内.
        """
        from automisc.gui.menu_dock import ToolMenuDock

        clicked = []

        def on_select(name, kind):
            clicked.append((name, kind))

        from automisc.core.decoders import pyc_decompiler  # noqa: F401
        dock = ToolMenuDock(on_tool_selected=on_select)
        qtbot.addWidget(dock)

        # 模拟点击 "decoder:pyc_decompiler:py2"
        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            if "反编译工具" not in cat_item.text(0):
                continue
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler:py2":
                    dock._on_item_clicked(child, 0)
                    break

        # 验证: callback name 包含 :py2 后缀 (per v0.5-pyc-decompiler-buttons 设计)
        assert clicked == [("pyc_decompiler:py2", "decoder")], (
            f"callback 异常: {clicked}, 期望 [('pyc_decompiler:py2', 'decoder')]"
        )

    def test_click_py3_button_keeps_suffix_in_callback(self, qtbot):
        """点击强制 py3 按钮 → callback 收到 name='pyc_decompiler:py3'."""
        from automisc.gui.menu_dock import ToolMenuDock

        clicked = []

        def on_select(name, kind):
            clicked.append((name, kind))

        from automisc.core.decoders import pyc_decompiler  # noqa: F401
        dock = ToolMenuDock(on_tool_selected=on_select)
        qtbot.addWidget(dock)

        for i in range(dock.tree.topLevelItemCount()):
            cat_item = dock.tree.topLevelItem(i)
            if "反编译工具" not in cat_item.text(0):
                continue
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child.data(0, 0x0100) == "decoder:pyc_decompiler:py3":
                    dock._on_item_clicked(child, 0)
                    break

        assert clicked == [("pyc_decompiler:py3", "decoder")], (
            f"callback 异常: {clicked}, 期望 [('pyc_decompiler:py3', 'decoder')]"
        )


# ---------- decoder run 集成测试 ----------
@pytest.mark.skipif(
    not RUN_PYC_SMOKE,
    reason=(
        "Owner-specific smoke 测试: 依赖真实 Py2.7 pyc + 在 GUI 测试全套跑时"
        " 会触发 SIGABRT (PySide6 + uncompyle6 资源竞争). opt-in via env RUN_PYC_SMOKE=1"
    ),
)
class TestPycDecompilerRun:
    """pyc_decompiler 跑 .pyc 文件反编译 (smoke)."""

    def test_run_on_real_py27_pyc(self, qtbot):
        """v0.5-train-019 实战 flag.pyc / 旧 N=NP writeup_literal.pyc 任一存在即可."""
        pyc_path = _find_real_py27_pyc()
        if pyc_path is None:
            pytest.skip("找不到真实 Py2.7 pyc (flag.pyc / writeup_literal.pyc)")

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        result = run_pyc_decompiler(str(pyc_path))
        assert result.success
        assert result.method == "uncompyle6"  # 默认走 Py2.x
        assert result.version == (2, 7)
        # flag.pyc 反编译出 def encode + ciphertext, N=NP 反编译出 def encrypt + KEY1
        assert (
            "def encrypt" in result.source_code
            or "def encode" in result.source_code
        )

    def test_run_with_force_version_2_writes_py2_suffix(self, qtbot):
        """v0.5-pyc-decompiler-buttons: force_version=2 + 写盘 <stem>__pyc_py2.py."""
        pyc_path = _find_real_py27_pyc()
        if pyc_path is None:
            pytest.skip("找不到真实 Py2.7 pyc")

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        result = run_pyc_decompiler(str(pyc_path), force_version=2)
        assert result.success
        assert result.method == "uncompyle6"
        assert result.force_version == 2
        # 写盘路径含 _py2 后缀
        assert result.output_path is not None
        assert "__pyc_py2.py" in result.output_path, (
            f"output_path 应含 __pyc_py2.py 后缀, 实际: {result.output_path}"
        )

    def test_run_with_force_version_3_falls_back_to_dis(self, qtbot):
        """v0.5-pyc-decompiler-buttons: force_version=3 在 Py2.7 pyc 上 decompyle3 失败 → dis fallback.

        关键: dis fallback 不写盘 (per Owner "成功后输出" = 真正源码).
        """
        pyc_path = _find_real_py27_pyc()
        if pyc_path is None:
            pytest.skip("找不到真实 Py2.7 pyc")

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        result = run_pyc_decompiler(str(pyc_path), force_version=3)
        # 强制 py3 解 Py2.7 pyc → decompyle3 失败 → dis fallback
        assert result.method == "dis", (
            f"force_version=3 跑 Py2.7 pyc, 应该走 dis fallback, 实际 method={result.method}"
        )
        # dis fallback 是字节码不是真源码, 不写盘
        assert result.output_path is None
        assert result.success is False
