"""GUI 测试: menu_dock 包含 v0.5-base-rot-decoders PR3 的 Base/ROT 解码分类

覆盖:
- menu_dock 渲染 "🔐 Base/ROT 解码" 分类
- 18 个 decoder 全部挂上去（12 base + 4 rot + 1 custom + 1 stego）
- ACTION_DISPLAY_NAMES 包含所有 18 个显示名
"""
from __future__ import annotations

import pytest

# 强制 offscreen (CI / 无显示器环境)
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def menu_dock(qtbot):
    from automisc.gui.menu_dock import ToolMenuDock, TOOL_CATEGORIES, ACTION_DISPLAY_NAMES
    dock = ToolMenuDock()
    qtbot.addWidget(dock)
    return dock, TOOL_CATEGORIES, ACTION_DISPLAY_NAMES


def test_menu_dock_has_base_rot_category(menu_dock):
    """🔐 Base/ROT 解码 二级分类存在"""
    dock, TOOL_CATEGORIES, _ = menu_dock
    assert "🔐 Base/ROT 解码 (v0.5+ Decoders)" in TOOL_CATEGORIES


def test_menu_dock_base_rot_has_18_decoders(menu_dock):
    """18 个 decoder 全部挂在 Base/ROT 解码分类下"""
    dock, TOOL_CATEGORIES, _ = menu_dock
    tools = TOOL_CATEGORIES["🔐 Base/ROT 解码 (v0.5+ Decoders)"]
    assert len(tools) == 18, f"expected 18, got {len(tools)}: {tools}"

    # 12 base
    base_names = [f"decoder:{n}" for n in [
        "base16", "base32", "base36", "base58", "base62", "base64",
        "base85", "base91", "base92", "base100", "base32768", "base65536",
    ]]
    for name in base_names:
        assert name in tools, f"{name} missing"

    # 4 rot
    rot_names = [f"decoder:{n}" for n in ["rot5", "rot13", "rot18", "rot47"]]
    for name in rot_names:
        assert name in tools, f"{name} missing"

    # 2 special
    assert "decoder:base64-custom" in tools
    assert "decoder:base64-stego" in tools


def test_menu_dock_display_names_have_all_18(menu_dock):
    """ACTION_DISPLAY_NAMES 含 18 个显示名"""
    dock, _, ACTION_DISPLAY_NAMES = menu_dock
    required = [
        "decoder:base16", "decoder:base32", "decoder:base36", "decoder:base58",
        "decoder:base62", "decoder:base64", "decoder:base85", "decoder:base91",
        "decoder:base92", "decoder:base100", "decoder:base32768", "decoder:base65536",
        "decoder:rot5", "decoder:rot13", "decoder:rot18", "decoder:rot47",
        "decoder:base64-custom", "decoder:base64-stego",
    ]
    for name in required:
        assert name in ACTION_DISPLAY_NAMES, f"{name} missing in ACTION_DISPLAY_NAMES"
        # 显示名不能为空字符串
        assert ACTION_DISPLAY_NAMES[name] != "", f"{name} has empty display"


def test_menu_dock_tree_renders_base_rot(qtbot):
    """menu_dock 树形控件正确渲染 Base/ROT 分类"""
    from automisc.gui.menu_dock import ToolMenuDock
    dock = ToolMenuDock()
    qtbot.addWidget(dock)

    # 找分类节点
    cat_item = None
    for i in range(dock.tree.topLevelItemCount()):
        item = dock.tree.topLevelItem(i)
        if "Base/ROT" in item.text(0):
            cat_item = item
            break
    assert cat_item is not None, "Base/ROT 分类节点未渲染"

    # 应该展开（per _populate）
    assert cat_item.isExpanded()

    # 子项数量 = 18
    assert cat_item.childCount() == 18, f"expected 18 children, got {cat_item.childCount()}"


def test_menu_dock_tree_children_have_correct_kind(qtbot):
    """18 个子项点击后 callback 应得到 kind='decoder'"""
    from automisc.gui.menu_dock import ToolMenuDock
    from automisc.core.decoders.registry import REGISTRY

    captured = []
    dock = ToolMenuDock(on_tool_selected=lambda name, kind: captured.append((name, kind)))
    qtbot.addWidget(dock)

    # 找所有 "decoder:base_rot_xxx" 子项并模拟点击
    for i in range(dock.tree.topLevelItemCount()):
        cat = dock.tree.topLevelItem(i)
        if "Base/ROT" not in cat.text(0):
            continue
        for j in range(cat.childCount()):
            child = cat.child(j)
            tool_name = child.data(0, 2)  # Qt.UserRole = 2
            # 模拟点击
            dock._on_item_clicked(child, 0)

    # 检查所有都是 kind='decoder'
    decoder_clicks = [(n, k) for n, k in captured if k == "decoder"]
    assert len(decoder_clicks) == 18, f"expected 18 decoder clicks, got {len(decoder_clicks)}"

    # 检查名字都在 REGISTRY
    reg_names = {s.name for s in REGISTRY}
    for name, _ in decoder_clicks:
        assert name in reg_names, f"{name} not in REGISTRY"


# === v0.5-zbar-rename (per Owner 22:17) ===

def test_zbar_display_name_renamed_to_qr_parse():
    """v0.5-zbar-rename: zbar 工具栏显示 '二维码解析'."""
    from automisc.gui.menu_dock import ZBAR_DISPLAY_NAME
    assert ZBAR_DISPLAY_NAME == "🔳 二维码解析"


def test_zbar_renders_with_new_display_name_in_tree(qtbot):
    """v0.5-zbar-rename: tree 渲染 zbar 时用新名 '🔳 二维码解析'."""
    from automisc.gui.menu_dock import ToolMenuDock
    from PySide6.QtCore import Qt
    dock = ToolMenuDock()
    qtbot.addWidget(dock)

    # 找 Misc/Brainteaser 分类
    for i in range(dock.tree.topLevelItemCount()):
        cat = dock.tree.topLevelItem(i)
        if "Brainteaser" not in cat.text(0):
            continue
        # 应该 1 个 zbar 子项, 显示为 "✓ 🔳 二维码解析" (✓ 是注册标记)
        assert cat.childCount() == 1
        text = cat.child(0).text(0)
        assert "二维码解析" in text, f"zbar 没显示为'二维码解析': {text!r}"
        # user role data 保持原 tool name (用于 callback dispatch)
        tool_name = cat.child(0).data(0, Qt.UserRole)
        assert tool_name == "zbar", f"zbar tool name 改掉了: {tool_name!r}"


# === v0.5-more-converts: 进制转换分类下 7 个新工具 ===

def test_convert_category_has_7_decoders_in_tree(qtbot):
    """v0.5-more-converts: 进制转换分类下应有 7 个 (1 老 + 6 新)."""
    from automisc.gui.menu_dock import ToolMenuDock
    dock = ToolMenuDock()
    qtbot.addWidget(dock)

    for i in range(dock.tree.topLevelItemCount()):
        cat = dock.tree.topLevelItem(i)
        if "进制转换" not in cat.text(0):
            continue
        # 7 个子项
        assert cat.childCount() == 7, (
            f"进制转换分类应 7 个子项, got {cat.childCount()}"
        )
        # 名字应包含 6 个新工具
        names = [cat.child(j).text(0) for j in range(cat.childCount())]
        for expected_display in [
            "Hex → ASCII", "Bin → ASCII", "Dec → Bin", "Bin → Dec",
            "Dec → Hex", "Hex → Dec", "ASCII → Bin",
        ]:
            assert any(expected_display in n for n in names), (
                f"进制转换分类缺 {expected_display!r}: {names}"
            )
