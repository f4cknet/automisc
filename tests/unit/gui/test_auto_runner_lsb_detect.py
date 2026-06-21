"""Tests for auto_runner + lsb_detect integration (per v0.5-lsb-detector spec §6 ②'' ③).

auto_run 池 (FIND_SUSPICIOUS_PICTURE_TOOLS) 删 zsteg 加 lsb_detect 后的整合测试:
- 池里含 lsb_detect 不含 zsteg (per Q1=A 拍板)
- 池大小仍 6 tools (per 铁律 7 '不抢下一步' 隐含: 池不扩张)
- lsb_detect adapter 已双注册 (per automisc-tool-registration 铁律)
- .png 后缀走 picture pool (per EXTENSION_TO_POOL)
- pool 跟 lsb_detect 集成 (run 6 tools 含 lsb_detect)
"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool, list_tools
from automisc.gui.auto_runner import (
    FIND_SUSPICIOUS_PICTURE_TOOLS,
    pick_suspicious_pool,
)


class TestFindSuspiciousPictureTools:
    """FIND_SUSPICIOUS_PICTURE_TOOLS 6 tools 池整合 (per spec §3.1 ③ ④)."""

    def test_pool_contains_lsb_detect(self):
        """池里含 lsb_detect (per Q1=A 替代 zsteg)."""
        assert "lsb_detect" in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"lsb_detect should be in pool, got: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_not_contain_zsteg(self):
        """池里**不**含 zsteg (per Q1=A 替代)."""
        assert "zsteg" not in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"zsteg should NOT be in pool, got: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_size_six_tools(self):
        """池大小仍 6 (per 铁律 7 '不抢下一步' 隐含: 池不扩张, 替代不增)."""
        assert len(FIND_SUSPICIOUS_PICTURE_TOOLS) == 6, (
            f"pool size should be 6, got {len(FIND_SUSPICIOUS_PICTURE_TOOLS)}: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_six_specific_tools(self):
        """池 6 工具具体: lsb_detect / stegseek / exiftool / binwalk / strings / file."""
        expected = {"lsb_detect", "stegseek", "exiftool", "binwalk", "strings", "file"}
        actual = set(FIND_SUSPICIOUS_PICTURE_TOOLS)
        assert actual == expected, (
            f"pool mismatch, expected {expected}, got {actual}"
        )


class TestLsbDetectAdapterRegistered:
    """lsb_detect adapter 双注册 verify (per automisc-tool-registration 铁律)."""

    def test_get_tool_lsb_detect(self):
        """get_tool('lsb_detect') 不报 ToolNotFoundError."""
        tool = get_tool("lsb_detect")
        assert tool is not None
        assert tool.name == "lsb_detect"

    def test_lsb_detect_in_list_tools(self):
        """list_tools() 含 lsb_detect (双注册触发链验证)."""
        tools = list_tools()
        assert "lsb_detect" in tools, (
            f"lsb_detect should be in list_tools, got: {[t for t in tools if 'lsb' in t.lower()]}"
        )

    def test_lsb_detect_category(self):
        """lsb_detect category = 'steganography_image' (跟 zsteg 同类)."""
        tool = get_tool("lsb_detect")
        assert tool.category == "steganography_image"

    def test_lsb_detect_description_mentions_alternative(self):
        """lsb_detect description 含 '替代 zsteg' (per spec §3.1)."""
        tool = get_tool("lsb_detect")
        assert "替代" in tool.description or "zsteg" in tool.description.lower()


class TestPickSuspiciousPool:
    """pick_suspicious_pool 按扩展名选 pool + 跟 lsb_detect 集成."""

    def test_png_picks_picture_pool_with_lsb_detect(self):
        """PNG 后缀 → picture pool + 含 lsb_detect."""
        pool_name, tools = pick_suspicious_pool("test.png")
        assert pool_name == "picture"
        assert "lsb_detect" in tools

    def test_jpg_picks_picture_pool_with_lsb_detect(self):
        """JPG 后缀 → picture pool + 含 lsb_detect."""
        pool_name, tools = pick_suspicious_pool("test.jpg")
        assert pool_name == "picture"
        assert "lsb_detect" in tools

    def test_picture_pool_size_six(self):
        """picture pool 仍 6 tools (per 铁律 7)."""
        _, tools = pick_suspicious_pool("test.png")
        assert len(tools) == 6

    def test_non_picture_picks_other_pool(self):
        """非图片扩展名 → 走其他 pool (traffic/archive/binary), 不含 lsb_detect."""
        # .pcap → traffic
        pool_name, tools = pick_suspicious_pool("test.pcap")
        assert pool_name == "traffic"
        assert "lsb_detect" not in tools

        # .zip → archive
        pool_name, tools = pick_suspicious_pool("test.zip")
        assert pool_name == "archive"
        assert "lsb_detect" not in tools

        # .bin → binary
        pool_name, tools = pick_suspicious_pool("test.bin")
        assert pool_name == "binary"
        assert "lsb_detect" not in tools


class TestZstegStillAvailableForManualUse:
    """zsteg adapter 文件保留 (per spec §4.1 IN), 供未来手工调用或复活用.

    不在 auto-run 池 (per Q1=A), 但 list_tools() / get_tool() 仍能找到.
    """

    def test_zsteg_still_in_list_tools(self):
        """zsteg adapter 文件保留, list_tools() 仍含 zsteg."""
        tools = list_tools()
        assert "zsteg" in tools, (
            f"zsteg should still be available for manual use, got: {[t for t in tools if 'z' in t.lower()]}"
        )

    def test_get_tool_zsteg_still_works(self):
        """get_tool('zsteg') 仍能找到 (供未来手工调用)."""
        tool = get_tool("zsteg")
        assert tool is not None
        assert tool.name == "zsteg"
