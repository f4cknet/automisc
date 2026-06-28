"""GUI menu 不含 zsteg 测试 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 3)

验证:
- TOOL_CATEGORIES["Stego/Image (PR2)"] 不含 zsteg
- ADAPTER_TOOLS 不含 zsteg (per Commit 4 还要再删 zsteg adapter, Commit 3 只删 GUI/Router 入口)
- core.registry.list_tools() 仍含 zsteg (Commit 4 才删 adapter 文件)
- core.registry.get_tool("zsteg") 仍能找到 (adapter 文件保留, CLI 仍可用)

Owner Q4=b 拍板 Commit 4 彻底删 zsteg adapter + import; Commit 3 范围 = GUI/Router/auto-run 入口清理.
"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool, list_tools
from automisc.gui.menu_dock import ADAPTER_TOOLS, TOOL_CATEGORIES


class TestGuiMenuNoZsteg:
    """GUI menu 不显示 zsteg (per Owner "用 LSB 分析代替 zsteg")."""

    def test_stego_image_category_no_zsteg(self):
        """Stego/Image (PR2) 不含 zsteg."""
        stego_cats = [
            tools for cat, tools in TOOL_CATEGORIES.items()
            if "Stego/Image" in cat
        ]
        assert len(stego_cats) == 1, f"expected 1 Stego/Image category, got {len(stego_cats)}"
        stego_tools = stego_cats[0]
        assert "zsteg" not in stego_tools, (
            f"zsteg should NOT be in Stego/Image menu (per v0.5-lsb-tool-bitplane-preview-matrix), "
            f"got: {stego_tools}"
        )
        # stegseek 仍保留 (per v0.5-windows-tool-compat, Win unavailable but GUI menu 仍标)
        assert "stegseek" in stego_tools

    def test_adapter_tools_no_zsteg(self):
        """ADAPTER_TOOLS 不含 zsteg (GUI 工具栏不再列出 zsteg)."""
        assert "zsteg" not in ADAPTER_TOOLS, (
            f"zsteg should NOT be in ADAPTER_TOOLS, got: {ADAPTER_TOOLS}"
        )


class TestRegistryStillHasZsteg:
    """core.registry 仍含 zsteg (Commit 4 才删 adapter, Commit 3 范围 = GUI 入口)."""

    def test_list_tools_contains_zsteg(self):
        """list_tools() 仍含 zsteg (adapter 文件未删)."""
        tools = list_tools()
        assert "zsteg" in tools, (
            f"zsteg should still be in list_tools() (Commit 4 才删 adapter), got: {tools}"
        )

    def test_get_tool_zsteg_still_works(self):
        """get_tool('zsteg') 仍能找到 (CLI 显式调用可用)."""
        tool = get_tool("zsteg")
        assert tool is not None
        assert tool.name == "zsteg"