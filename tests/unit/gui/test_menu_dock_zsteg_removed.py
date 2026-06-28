"""GUI menu 不含 zsteg 测试 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 3+4)

验证:
- TOOL_CATEGORIES["Stego/Image (PR2)"] 不含 zsteg (Commit 3)
- ADAPTER_TOOLS 不含 zsteg (Commit 3)
- core.registry.list_tools() **不**含 zsteg (Commit 4 删 adapter)
- core.registry.get_tool("zsteg") 抛 ToolNotFoundError (Commit 4 删 adapter)

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
        # steghide 替代 stegseek (per v0.5-stegseek-remove 2026-06-28, Win 端用)
        assert "steghide" in stego_tools

    def test_adapter_tools_no_zsteg(self):
        """ADAPTER_TOOLS 不含 zsteg (GUI 工具栏不再列出 zsteg)."""
        assert "zsteg" not in ADAPTER_TOOLS, (
            f"zsteg should NOT be in ADAPTER_TOOLS, got: {ADAPTER_TOOLS}"
        )


class TestRegistryZstegRemoved:
    """core.registry 已删 zsteg (per Commit 4, Owner Q4=b 拍板彻底删)."""

    def test_list_tools_not_contains_zsteg(self):
        """list_tools() 不含 zsteg (adapter 已删)."""
        tools = list_tools()
        assert "zsteg" not in tools, (
            f"zsteg should NOT be in list_tools() (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4), "
            f"got: {tools}"
        )

    def test_get_tool_zsteg_raises(self):
        """get_tool('zsteg') 抛 ToolNotFoundError (adapter 已删, 未来 Ruby 装回需重新加)."""
        from automisc.core.registry import ToolNotFoundError
        with pytest.raises(ToolNotFoundError):
            get_tool("zsteg")