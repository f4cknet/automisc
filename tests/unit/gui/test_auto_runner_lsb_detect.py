"""Tests for auto_runner + lsb_tool integration (per v0.5-lsb-tool-unify spec §3.9).

auto_run 池 (FIND_SUSPICIOUS_PICTURE_TOOLS) lsb_detect → lsb_tool 后的整合测试:
- 池里含 lsb_tool 不含 lsb_detect (per spec §3.9)
- 池大小仍 6 tools (per 铁律 7 auto-run 池不扩张)
- lsb_tool adapter 已双注册 (per automisc-tool-registration 铁律)
- .png 后缀走 picture pool (per EXTENSION_TO_POOL)
- pool 跟 lsb_tool 集成 (run 6 tools 含 lsb_tool)
- zsteg adapter **已彻底删** (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4, Owner Q4=b 拍板)
- 老 lsb_detect adapter 仍 get_tool('lsb_detect') 可访问 (Phase 6 deprecated 但未删)
"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool, list_tools
from automisc.gui.auto_runner import (
    FIND_SUSPICIOUS_PICTURE_TOOLS,
    pick_suspicious_pool,
)


class TestFindSuspiciousPictureTools:
    """FIND_SUSPICIOUS_PICTURE_TOOLS 6 tools 池整合 (per spec §3.9)."""

    def test_pool_contains_lsb_tool(self):
        """池里含 lsb_tool (per spec §3.9 替代 lsb_detect)."""
        assert "lsb_tool" in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"lsb_tool should be in pool, got: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_not_contain_lsb_detect(self):
        """池里**不**含 lsb_detect (per spec §3.9 替代)."""
        assert "lsb_detect" not in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"lsb_detect should NOT be in pool, got: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_not_contain_zsteg(self):
        """池里**不**含 zsteg (per Q1=A 历史替代, 保留文件但不上 auto-run)."""
        assert "zsteg" not in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"zsteg should NOT be in pool, got: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_size_six_tools(self):
        """池大小仍 6 (per 铁律 7 '不抢下一步' 隐含: 池不扩张, 替代不增)."""
        assert len(FIND_SUSPICIOUS_PICTURE_TOOLS) == 6, (
            f"pool size should be 6, got {len(FIND_SUSPICIOUS_PICTURE_TOOLS)}: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_six_specific_tools(self):
        """池 6 工具具体: lsb_tool / stegseek / exiftool / binwalk / strings / file."""
        expected = {"lsb_tool", "stegseek", "exiftool", "binwalk", "strings", "file"}
        actual = set(FIND_SUSPICIOUS_PICTURE_TOOLS)
        assert actual == expected, (
            f"pool mismatch, expected {expected}, got {actual}"
        )


class TestLsbToolAdapterRegistered:
    """lsb_tool adapter 双注册 verify (per automisc-tool-registration 铁律)."""

    def test_get_tool_lsb_tool(self):
        """get_tool('lsb_tool') 不报 ToolNotFoundError."""
        tool = get_tool("lsb_tool")
        assert tool is not None
        assert tool.name == "lsb_tool"

    def test_lsb_tool_in_list_tools(self):
        """list_tools() 含 lsb_tool (双注册触发链验证)."""
        tools = list_tools()
        assert "lsb_tool" in tools, (
            f"lsb_tool should be in list_tools, got: {[t for t in tools if 'lsb' in t.lower()]}"
        )

    def test_lsb_tool_category(self):
        """lsb_tool category = 'steganography_image' (跟 zsteg 同类)."""
        tool = get_tool("lsb_tool")
        assert tool.category == "steganography_image"

    def test_lsb_tool_description_mentions_alternative(self):
        """lsb_tool description 含 '替代 lsb_detect' (per spec §3.9)."""
        tool = get_tool("lsb_tool")
        assert "替代" in tool.description or "lsb_detect" in tool.description.lower()

    def test_lsb_tool_default_mode_is_detect(self):
        """lsb_tool 默认 mode='detect' (per spec §3.1 readonly 优先)."""
        tool = get_tool("lsb_tool")
        # adapter 内部 _action.mode 默认是 'detect'
        assert tool._action.mode == "detect"


class TestPickSuspiciousPool:
    """pick_suspicious_pool 按扩展名选 pool + 跟 lsb_tool 集成."""

    def test_png_picks_picture_pool_with_lsb_tool(self):
        """PNG 后缀 → picture pool + 含 lsb_tool."""
        pool_name, tools = pick_suspicious_pool("test.png")
        assert pool_name == "picture"
        assert "lsb_tool" in tools

    def test_jpg_picks_picture_pool_with_lsb_tool(self):
        """JPG 后缀 → picture pool + 含 lsb_tool."""
        pool_name, tools = pick_suspicious_pool("test.jpg")
        assert pool_name == "picture"
        assert "lsb_tool" in tools

    def test_picture_pool_size_six(self):
        """picture pool 仍 6 tools (per 铁律 7)."""
        _, tools = pick_suspicious_pool("test.png")
        assert len(tools) == 6

    def test_non_picture_picks_other_pool(self):
        """非图片扩展名 → 走其他 pool (traffic/archive/binary), 不含 lsb_tool."""
        pool_name, tools = pick_suspicious_pool("test.pcap")
        assert pool_name == "traffic"
        assert "lsb_tool" not in tools

        pool_name, tools = pick_suspicious_pool("test.zip")
        assert pool_name == "archive"
        assert "lsb_tool" not in tools

        pool_name, tools = pick_suspicious_pool("test.bin")
        assert pool_name == "binary"
        assert "lsb_tool" not in tools


class TestBackwardCompatLegacyTools:
    """老 LSB 工具 (lsb_detect) backward compat 保留 (Phase 6 deprecated 但未删).

    zsteg: 已彻底删 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4, Owner Q4=b 拍板)
    lsb_detect: Phase 6 后删, 当前保留 backward compat
    """

    def test_zsteg_no_longer_in_list_tools(self):
        """zsteg adapter 已删 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4), list_tools() 不含 zsteg."""
        tools = list_tools()
        assert "zsteg" not in tools, (
            "zsteg adapter deleted (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4), "
            f"should NOT be in list_tools(), got: {tools}"
        )

    def test_get_tool_zsteg_raises(self):
        """get_tool('zsteg') 应抛 ToolNotFoundError (adapter 已删)."""
        from automisc.core.registry import ToolNotFoundError
        with pytest.raises(ToolNotFoundError):
            get_tool("zsteg")

    def test_lsb_detect_still_in_list_tools(self):
        """lsb_detect adapter Phase 6 deprecated 但未删, list_tools() 仍含."""
        tools = list_tools()
        assert "lsb_detect" in tools, (
            "lsb_detect adapter deprecated but not deleted (Phase 6 留 backward compat)"
        )

    def test_get_tool_lsb_detect_still_works(self):
        """get_tool('lsb_detect') 仍能找到 (Phase 6 deprecated 但未删)."""
        tool = get_tool("lsb_detect")
        assert tool is not None
        assert tool.name == "lsb_detect"