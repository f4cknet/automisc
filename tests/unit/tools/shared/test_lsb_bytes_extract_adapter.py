"""Tests for LsbBytesExtractAdapter (per v0.5-lsb-bytes-auto-run).

auto-run 兜底 zsteg 漏报: 12 组合 (RGB × bit 0/7 × row/col × MSB), ~5s/张图。

覆盖:
- adapter 注册 (per automisc-tool-registration memory)
- 默认 12 组合跑通 (mock LSBBytesExtractAction)
- SP 累积 (severity=5, 不中断)
- 文件不存在 graceful (severity=2)
- 全部组合失败 graceful (severity=2 不中断 auto-run)
- 在 FIND_SUSPICIOUS_PICTURE_TOOLS 池里
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automisc.core.dag import ActionResult
from automisc.core.registry import get_tool
from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS
from automisc.tools.shared.lsb_bytes_extract_adapter import (
    DEFAULT_COMBOS,
    LsbBytesExtractAdapter,
)


# ---------- 注册测试 (per automisc-tool-registration memory) ----------
class TestAdapterRegistration:
    """adapter 必须在 registry 找到 (per v0.5-lsb-bytes-auto-run spec §3.1)."""

    def test_adapter_is_registered(self):
        """get_tool('lsb_bytes_extract') 必须返回 LsbBytesExtractAdapter 实例."""
        adapter = get_tool("lsb_bytes_extract")
        assert isinstance(adapter, LsbBytesExtractAdapter)

    def test_adapter_in_find_suspicious_picture_pool(self):
        """FIND_SUSPICIOUS_PICTURE_TOOLS 必须含 'lsb_bytes_extract' (auto-run 兜底入口)."""
        assert "lsb_bytes_extract" in FIND_SUSPICIOUS_PICTURE_TOOLS, (
            f"FIND_SUSPICIOUS_PICTURE_TOOLS 缺失 lsb_bytes_extract, "
            f"实际: {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_default_combos_count(self):
        """默认 12 组合 (per spec §3.3.2 Q1=A 拍板)."""
        assert len(DEFAULT_COMBOS) == 12


# ---------- 跑默认 12 组合测试 ----------
class TestLsbBytesExtractAdapterRun:
    """adapter.run 跑默认 12 组合, 写 SP."""

    def _mock_action_result(self, success: bool = True, extracted_path: str = None, message: str = None):
        """构造 mock ActionResult."""
        return ActionResult(
            success=success,
            message=message or "",
            data={
                "lsb_bytes": {
                    "extracted_path": extracted_path or "/tmp/np__lsb_rgb_b0_row_msb.bin",
                    "raw_size": 1000,
                    "channels": ["R", "G", "B"],
                    "bit": 0,
                    "scan_order": "row",
                    "byte_bit_order": "MSB",
                }
            } if success else {},
        )

    def test_run_writes_sp_to_journal(self, tmp_path):
        """12 组合全成功 → 12 个 SP severity=5 累积 (per v0.5-auto-run-discipline 铁律 '可疑点越多越好')."""
        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        adapter = LsbBytesExtractAdapter()

        with patch(
            "automisc.tools.shared.lsb_bytes_extract_adapter.LSBBytesExtractAction"
        ) as mock_action_cls:
            # 每个组合都返 success
            mock_action_cls.return_value.run.return_value = self._mock_action_result(success=True)

            result = adapter.run(str(fake_png))

        # 12 组合 → 12 个 SP
        assert len(result.suspicious_points) == 12
        # 所有 SP severity=5 (可疑, 需要二次分析)
        assert all(sp.severity == 5 for sp in result.suspicious_points)
        # 全部 category=lsb_bytes_extracted
        assert all(sp.category == "lsb_bytes_extracted" for sp in result.suspicious_points)

    def test_run_handles_file_not_found(self, tmp_path):
        """文件不存在 → SP severity=2 (不中断 auto-run, per v0.5-auto-run-discipline)."""
        missing = tmp_path / "does_not_exist.png"

        adapter = LsbBytesExtractAdapter()
        result = adapter.run(str(missing))

        assert result.exit_code == 1
        assert len(result.suspicious_points) == 1
        sp = result.suspicious_points[0]
        assert sp.severity == 2  # usage_hint
        assert sp.category == "usage_hint"
        assert "file not found" in sp.matched_pattern

    def test_run_handles_all_combos_fail_gracefully(self, tmp_path):
        """12 组合全失败 → 不中断, 返 SP severity=2 提示格式可能不支持."""
        fake_png = tmp_path / "fake.jpg"  # JPEG LSB 不支持
        fake_png.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        adapter = LsbBytesExtractAdapter()

        with patch(
            "automisc.tools.shared.lsb_bytes_extract_adapter.LSBBytesExtractAction"
        ) as mock_action_cls:
            # 每个组合都返 fail
            mock_action_cls.return_value.run.return_value = self._mock_action_result(
                success=False, message="format not supported"
            )

            result = adapter.run(str(fake_png))

        # 不中断 (没有 raise)
        assert result.exit_code == 1
        # 12 组合全失败 → 整体 SP severity=2 提示
        assert any(
            sp.severity == 2 and "格式不支持" in sp.matched_pattern
            for sp in result.suspicious_points
        )

    def test_run_skips_failed_combo_without_sp(self, tmp_path):
        """个别组合失败 → 跳过, 不累积 SP (per auto-run discipline '不抢分支, 让成功路径走')."""
        fake_png = tmp_path / "fake.png"
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        adapter = LsbBytesExtractAdapter()

        # 模拟: 12 组合里 8 个成功, 4 个失败
        call_count = [0]

        def mock_run(context):
            call_count[0] += 1
            # 前 8 个成功, 后 4 个失败
            if call_count[0] <= 8:
                return self._mock_action_result(success=True)
            else:
                return self._mock_action_result(success=False, message="JPEG not supported")

        with patch(
            "automisc.tools.shared.lsb_bytes_extract_adapter.LSBBytesExtractAction"
        ) as mock_action_cls:
            mock_action_cls.return_value.run.side_effect = mock_run

            result = adapter.run(str(fake_png))

        # 8 个成功 → 8 个 SP (severity=5)
        success_sps = [sp for sp in result.suspicious_points if sp.severity == 5]
        assert len(success_sps) == 8
        # 4 个失败, 但失败率 < 半数 → 不加整体 SP severity=2
        assert not any(
            sp.severity == 2 and "格式不支持" in sp.matched_pattern
            for sp in result.suspicious_points
        )


# ---------- adapter 跟 GUI 集成测试 ----------
class TestLsbBytesExtractAdapterGUI:
    """adapter 跟 auto_run + menu_dock 集成."""

    def test_adapter_in_menu_dock(self):
        """ADAPTER_TOOLS 必须含 'lsb_bytes_extract' (per automisc-tool-registration)."""
        from automisc.gui.menu_dock import ADAPTER_TOOLS
        assert "lsb_bytes_extract" in ADAPTER_TOOLS

    def test_adapter_in_shared_category(self):
        """TOOL_CATEGORIES['共享基础工具 (PR1)'] 必须含 'lsb_bytes_extract'."""
        from automisc.gui.menu_dock import TOOL_CATEGORIES
        assert "lsb_bytes_extract" in TOOL_CATEGORIES["共享基础工具 (PR1)"]