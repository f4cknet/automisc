"""GUI 测试: menu_dock 包含 v0.5-cipher-decoders 的 解密工具1/2/3 一级目录

覆盖:
- menu_dock 渲染 "🔤 解密工具1" / "📦 解密工具2" / "📦 解密工具3" 3 个分类
- 解密工具1 含 12 个 cipher (凯撒/培根/...)
- 解密工具2/3 含占位 spec
- tree 控件正确展开 + 点击 dispatch 到 callback kind='decoder'
"""
from __future__ import annotations

import pytest

# 强制 offscreen (CI / 无显示器环境)
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def cipher_menu_dock(qtbot):
    from automisc.gui.menu_dock import ToolMenuDock
    dock = ToolMenuDock()
    qtbot.addWidget(dock)
    return dock


# === 静态分类注册检查 ===

def test_cipher_categories_defined():
    """menu_dock 模块定义了 3 个 cipher 分类元数据."""
    from automisc.gui.menu_dock import CIPHER_DOCK_CATEGORIES
    assert ("解密工具1", "🔤") in CIPHER_DOCK_CATEGORIES
    assert ("解密工具2", "📦") in CIPHER_DOCK_CATEGORIES
    assert ("解密工具3", "📦") in CIPHER_DOCK_CATEGORIES


def test_cipher_categories_from_registry_helper():
    """_get_cipher_categories_from_registry() 返回 3 个分类 (含 12+1+1 items)."""
    from automisc.gui.menu_dock import _get_cipher_categories_from_registry
    cats = _get_cipher_categories_from_registry()
    # 3 个分类都应出现 (因为 cipher_decoders.py 注册了 12+1+1=14 spec)
    titles = list(cats.keys())
    assert any("解密工具1" in t for t in titles), titles
    assert any("解密工具2" in t for t in titles), titles
    assert any("解密工具3" in t for t in titles), titles
    # 解密工具1 = 12 items (12 cipher)
    g1 = next(t for t in titles if "解密工具1" in t)
    assert len(cats[g1]) == 12, f"解密工具1 期望 12 cipher, got {len(cats[g1])}: {cats[g1]}"
    # 解密工具2 = 1 (占位)
    g2 = next(t for t in titles if "解密工具2" in t)
    assert len(cats[g2]) == 1, f"解密工具2 期望 1 占位, got {len(cats[g2])}"
    # 解密工具3 = 1 (占位)
    g3 = next(t for t in titles if "解密工具3" in t)
    assert len(cats[g3]) == 1, f"解密工具3 期望 1 占位, got {len(cats[g3])}"


def test_cipher_categories_contain_12_cipher_names():
    """解密工具1 含全部 12 个 cipher decoder name."""
    from automisc.gui.menu_dock import _get_cipher_categories_from_registry
    cats = _get_cipher_categories_from_registry()
    g1 = next(v for k, v in cats.items() if "解密工具1" in k)
    expected = {
        "decoder:caesar", "decoder:bacon", "decoder:rail-fence", "decoder:pigpen",
        "decoder:morse", "decoder:xxencode", "decoder:uuencode", "decoder:jsfuck",
        "decoder:jjencode", "decoder:quoted-printable", "decoder:brainfuck",
        "decoder:bubblebabble",
    }
    assert set(g1) == expected, f"got {g1}, expected {expected}"


def test_cipher_display_names_helper_returns_12_plus_2():
    """_get_cipher_display_names() 返回 12+2=14 display name."""
    from automisc.gui.menu_dock import _get_cipher_display_names
    names = _get_cipher_display_names()
    assert len(names) == 14, f"expected 14, got {len(names)}"
    # 占位的 display 是 "（占位 — TBD）"
    placeholder_keys = [k for k in names if "placeholder" in k]
    assert len(placeholder_keys) == 2
    for k in placeholder_keys:
        assert names[k] == "（占位 — TBD）", f"{k} → {names[k]}"


# === Tree 渲染测试 ===

def test_menu_dock_renders_cipher_groups(cipher_menu_dock):
    """menu_dock tree 含 '解密工具1/2/3' 3 个一级分类."""
    dock = cipher_menu_dock
    titles = []
    for i in range(dock.tree.topLevelItemCount()):
        item = dock.tree.topLevelItem(i)
        titles.append(item.text(0))
    assert any("解密工具1" in t for t in titles), f"missing 解密工具1: {titles}"
    assert any("解密工具2" in t for t in titles), f"missing 解密工具2: {titles}"
    assert any("解密工具3" in t for t in titles), f"missing 解密工具3: {titles}"


def test_menu_dock_decrypt_tool1_has_12_children(cipher_menu_dock):
    """🔤 解密工具1 含 12 个 cipher child item."""
    dock = cipher_menu_dock
    g1 = None
    for i in range(dock.tree.topLevelItemCount()):
        item = dock.tree.topLevelItem(i)
        if "解密工具1" in item.text(0):
            g1 = item
            break
    assert g1 is not None
    # 展开
    assert g1.isExpanded()
    # 12 个 cipher
    assert g1.childCount() == 12, f"expected 12 children, got {g1.childCount()}"
    # 子项是 ✓ 标记 (因为不在 ADAPTER_TOOLS)
    for j in range(g1.childCount()):
        text = g1.child(j).text(0)
        assert text.startswith("✓ "), f"child {j}: {text!r}"


def test_menu_dock_decrypt_tool2_has_1_placeholder(cipher_menu_dock):
    """📦 解密工具2 含 1 个占位."""
    dock = cipher_menu_dock
    g2 = None
    for i in range(dock.tree.topLevelItemCount()):
        item = dock.tree.topLevelItem(i)
        if "解密工具2" in item.text(0):
            g2 = item
            break
    assert g2 is not None
    assert g2.childCount() == 1
    text = g2.child(0).text(0)
    assert "占位" in text, f"got: {text!r}"


def test_menu_dock_decrypt_tool3_has_1_placeholder(cipher_menu_dock):
    """📦 解密工具3 含 1 个占位."""
    dock = cipher_menu_dock
    g3 = None
    for i in range(dock.tree.topLevelItemCount()):
        item = dock.tree.topLevelItem(i)
        if "解密工具3" in item.text(0):
            g3 = item
            break
    assert g3 is not None
    assert g3.childCount() == 1


def test_menu_dock_cipher_children_dispatch_to_decoder_callback(cipher_menu_dock):
    """点击 cipher 子项 → callback 收到 kind='decoder' + name=<cipher>."""
    dock = cipher_menu_dock
    captured = []
    # 重新绑定 callback
    dock._on_tool_selected = lambda name, kind: captured.append((name, kind))

    # 找 解密工具1 分类 + 模拟点击每个 cipher 子项
    for i in range(dock.tree.topLevelItemCount()):
        cat = dock.tree.topLevelItem(i)
        if "解密工具1" not in cat.text(0):
            continue
        for j in range(cat.childCount()):
            child = cat.child(j)
            dock._on_item_clicked(child, 0)

    # 12 个 click 应全部 kind='decoder'
    decoder_clicks = [(n, k) for n, k in captured if k == "decoder"]
    assert len(decoder_clicks) == 12, f"expected 12, got {len(decoder_clicks)}"
    # name 应都在 cipher 列表里
    expected_names = {
        "caesar", "bacon", "rail-fence", "pigpen", "morse",
        "xxencode", "uuencode", "jsfuck", "jjencode",
        "quoted-printable", "brainfuck", "bubblebabble",
    }
    got_names = {n for n, _ in decoder_clicks}
    assert got_names == expected_names, f"got {got_names}, expected {expected_names}"


def test_menu_dock_placeholder_children_dispatch(cipher_menu_dock):
    """点击占位子项 → callback 收到 kind='decoder' + name='placeholder-...'."""
    dock = cipher_menu_dock
    captured = []
    dock._on_tool_selected = lambda name, kind: captured.append((name, kind))

    for i in range(dock.tree.topLevelItemCount()):
        cat = dock.tree.topLevelItem(i)
        if "解密工具2" not in cat.text(0) and "解密工具3" not in cat.text(0):
            continue
        for j in range(cat.childCount()):
            child = cat.child(j)
            dock._on_item_clicked(child, 0)

    assert len(captured) == 2, f"expected 2 placeholder clicks, got {len(captured)}"
    for name, kind in captured:
        assert kind == "decoder"
        assert name.startswith("placeholder-解密工具")


# === 回归: 老分类没被破坏 ===

def test_menu_dock_keeps_existing_categories(cipher_menu_dock):
    """v0.5-cipher-decoders 不能破坏老分类（PR1-PR8 + 快捷 + 解码/进制/QR/BaseROT）."""
    dock = cipher_menu_dock
    titles = []
    for i in range(dock.tree.topLevelItemCount()):
        titles.append(dock.tree.topLevelItem(i).text(0))

    # 老 12 个分类必须仍在
    expected_old = [
        "共享基础工具 (PR1)", "Stego/Image (PR2)", "Forensics/Network (PR3)",
        "Stego/Audio+Video (PR4)", "Misc/Archive (PR5)", "Forensics/Log (PR6)",
        "Forensics/Memory (PR7)", "Misc/Brainteaser (PR8)",
        "快捷工具 (v0.5 Actions)",
        "🔓 解码工具 (v0.5+ Decoders)",
        "🔢 进制转换 (v0.5+ Convert)",
        "🔳 QR 工具 (v0.5+ QR Tools)",
        "🔐 Base/ROT 解码 (v0.5+ Decoders)",
    ]
    for exp in expected_old:
        assert exp in titles, f"老分类 {exp!r} 不见了: {titles}"
