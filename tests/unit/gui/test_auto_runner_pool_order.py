"""验证 FIND_SUSPICIOUS_PICTURE_TOOLS 顺序 (per v0.5-auto-run-pool-steghide-last).

核心验证:
- steghide 在 file 之前 (慢路径 fallback 顺序)
- 快速工具 (lsb_tool/exiftool/binwalk/strings) 在 steghide 之前
- 池大小仍 6 (per §1 铁律 7: auto-run 池不扩张)

Owner 实战反馈 (per v0.5-train-015, 2026-06-28 16:46):
- steghide auto-run 30s 超时噪音
- "通常在其他工具没发现可疑信息后才会尝试 steghide"
- 决策: steghide 顺序从 [1] 移到 [5] (file 之前)
"""
from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS


class TestAutoRunPoolOrder:
    """auto-run 池顺序验证 (per v0.5-auto-run-pool-steghide-last)."""

    def test_pool_size_still_6(self):
        """池大小仍 6 (per §1 铁律 7: auto-run 池不扩张)."""
        assert len(FIND_SUSPICIOUS_PICTURE_TOOLS) == 6, (
            f"pool size must be 6, got {len(FIND_SUSPICIOUS_PICTURE_TOOLS)}: "
            f"{FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_order_steghide_last_before_file(self):
        """steghide 在 file 之前 (慢路径 fallback 顺序).

        per Owner 实战经验 "通常在其他工具没发现可疑信息后才会尝试 steghide".
        file 是兜底, 永远最后.
        """
        assert "steghide" in FIND_SUSPICIOUS_PICTURE_TOOLS
        assert "file" in FIND_SUSPICIOUS_PICTURE_TOOLS
        steghide_idx = FIND_SUSPICIOUS_PICTURE_TOOLS.index("steghide")
        file_idx = FIND_SUSPICIOUS_PICTURE_TOOLS.index("file")
        assert steghide_idx < file_idx, (
            f"steghide should be before file (slow fallback before 兜底), "
            f"got steghide={steghide_idx}, file={file_idx}, "
            f"pool={FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )

    def test_pool_order_fast_tools_first(self):
        """快速工具 (lsb_tool/exiftool/binwalk/strings) 在 steghide 之前.

        快速工具先跑出可疑点 → steghide 作为最后 fallback.
        """
        fast_tools = ["lsb_tool", "exiftool", "binwalk", "strings"]
        steghide_idx = FIND_SUSPICIOUS_PICTURE_TOOLS.index("steghide")
        for tool in fast_tools:
            assert tool in FIND_SUSPICIOUS_PICTURE_TOOLS, (
                f"{tool} should be in pool, got {FIND_SUSPICIOUS_PICTURE_TOOLS}"
            )
            tool_idx = FIND_SUSPICIOUS_PICTURE_TOOLS.index(tool)
            assert tool_idx < steghide_idx, (
                f"{tool} (fast) should be before steghide (slow fallback), "
                f"got {tool}={tool_idx}, steghide={steghide_idx}"
            )

    def test_pool_order_specific_sequence(self):
        """完整顺序验证: lsb_tool → exiftool → binwalk → strings → steghide → file."""
        expected = [
            "lsb_tool",   # 1
            "exiftool",   # 2
            "binwalk",    # 3
            "strings",    # 4
            "steghide",   # 5
            "file",       # 6
        ]
        assert FIND_SUSPICIOUS_PICTURE_TOOLS == expected, (
            f"pool order mismatch:\n"
            f"  expected: {expected}\n"
            f"  actual:   {FIND_SUSPICIOUS_PICTURE_TOOLS}"
        )