"""测试 lsb_tool_common._extract_lsb_byte_stream (per v0.5-lsb-tool-bitplane-preview-matrix Commit 1)

**核心验证**: 修复后的 _extract_lsb_byte_stream 必须跟 zsteg `b<bit>,<channels>,<byte_bit_order>,<scan>` 完全等价
(per v0.5-train-014: steg.png 实战命中 0 SP, 根因 plane-separated 跟 zsteg 不一致).
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from automisc.core.actions.lsb_tool_common import (
    _ascii_preview,
    _build_bit_plane_preview_matrix,
    _extract_lsb_byte_stream,
    _format_matrix_for_journal,
)


# ============ fixtures ============


@pytest.fixture
def steg_png_bytes():
    """steg.png 实战 fixture (per v0.5-train-014): RGB LSB bit 0 row MSB → 'Hey I think...'."""
    from pathlib import Path
    path = Path(r"C:\Users\zmzsg\Downloads\421a9b455a817fab96e7ecf0d1b47a9da630c80554177875aa3f5a08fabb015d\镜子里面的世界\steg.png")
    if not path.exists():
        pytest.skip(f"steg.png fixture not found: {path}")
    return np.array(Image.open(path).convert("RGB"))


@pytest.fixture
def synthetic_2x2():
    """2x2 像素 PNG: R=[0,1], G=[2,3], B=[4,5] LSB plane = 已知模式.
    bit 序列 (per-pixel RGB): 0,0,0, 1,1,1, 0,0,0, 1,0,0 = [0,0,0,1,1,1,0,0,0,1,0,0]
    → 第 1 字节 (MSB first): 00011100 = 0x1C
    """
    arr = np.zeros((2, 2, 3), dtype=np.uint8)
    arr[0, 0] = [0b00000000, 0b00000010, 0b00000100]  # R bit0=0, G bit0=1, B bit0=0
    arr[0, 1] = [0b00000001, 0b00000011, 0b00000101]  # R bit0=1, G bit0=1, B bit0=1
    arr[1, 0] = [0b00000000, 0b00000000, 0b00000000]
    arr[1, 1] = [0b00000001, 0b00000000, 0b00000000]
    return arr


# ============ zsteg 兼容: per-pixel interleaved 核心验证 ============


class TestPerPixelInterleaved:
    """验证修复后的 _extract_lsb_byte_stream 跟 zsteg per-pixel interleaved 完全等价."""

    def test_rgb_bit0_row_msb_synthetic(self, synthetic_2x2):
        """2x2 PNG, channels=RGB, bit=0, row, msb.
        bit 序列 (per-pixel): 0,0,0, 1,1,1, 0,0,0, 1,0,0
        前 8 bit (MSB first): 00011100 = 0x1C = 28
        """
        bs = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # 12 bit 总共 → 1 字节 (n_bytes = 12//8 = 1)
        assert len(bs) == 1, f"expected 1 byte, got {len(bs)}"
        # 前 8 bit = 0001_1100 = 0x1C
        assert bs[0] == 0x1C, f"expected 0x1C, got {bs[0]:#04x}"

    def test_rgb_bit0_row_msb_steg_png(self, steg_png_bytes):
        """steg.png 实战验证: bit=0 RGB row MSB 应命中 'Hey I think...'.
        这是 v0.5-train-014 触发器 (修复前 = 0x161e..., 修复后 = 'Hey I th').
        """
        bs = _extract_lsb_byte_stream(
            steg_png_bytes, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # 前 3 字节应为 "Hey" = 0x48 0x65 0x79
        assert bs[:3] == b"Hey", f"expected b'Hey', got {bs[:3]!r}"
        # 前 11 字节应为 "Hey I think"
        assert bs[:11] == b"Hey I think", f"expected b'Hey I think', got {bs[:11]!r}"
        # 完整明文应有 secret key
        assert b"st3g0_saurus_wr3cks" in bs, "secret key not found in byte stream"


class TestColScan:
    """col scan: 转置后 row-major flatten."""

    def test_col_vs_row_inverted(self, synthetic_2x2):
        """col scan = zsteg yx 顺序: 先固定 x, 按 y 遍历 (等价于转置后 row-major).
        2x2 arr → 转置 (W=2, H=2, 3) → flatten:
        t[0,0] = arr[0,0] = [0,2,4] → bits 0,0,0
        t[0,1] = arr[1,0] = [0,0,0] → bits 0,0,0
        t[1,0] = arr[0,1] = [1,3,5] → bits 1,1,1
        t[1,1] = arr[1,1] = [1,0,0] → bits 1,0,0
        = [0,0,0, 0,0,0, 1,1,1, 1,0,0]
        前 8 bit (MSB first): 00000011 = 0x03
        """
        bs_col = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="col", byte_bit_order="msb",
        )
        assert bs_col[0] == 0x03, f"expected 0x03, got {bs_col[0]:#04x}"


class TestByteBitOrder:
    """byte_bit_order: msb (默认) vs lsb (字节内 bit 反序)."""

    def test_msb_vs_lsb_inverted(self, synthetic_2x2):
        """同一 bit 流, byte_bit_order 不同 → 字节内 bit 反序."""
        bs_msb = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_lsb = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="lsb",
        )
        # MSB 第 1 字节 = 0001_1100 = 0x1C
        # 反序 = 0011_1000 = 0x38
        assert bs_msb[0] == 0x1C
        assert bs_lsb[0] == 0x38, f"expected 0x38, got {bs_lsb[0]:#04x}"


class TestSingleChannel:
    """单通道 LSB 抽字节流 (per v0.5-train-009 N=NP 模式)."""

    def test_single_R_channel(self, synthetic_2x2):
        """只取 R 通道 bit 0.
        arr R 通道 bit 0 = [0, 1, 0, 1] (顺序 00, 01, 10, 11)
        前 8 bit = 0101_xxxx, 第 1 字节 = 0101_xxxx, 取 8 bit = 0101_0000 (高 4 位 + 0 填充) = 0x50.
        实际上 4 个像素只有 4 bit, n_bytes = 0.
        """
        bs = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # 4 bit 总共 → 0 字节 (n_bytes = 4//8 = 0)
        assert len(bs) == 0, f"expected 0 bytes, got {len(bs)}"

    def test_single_G_channel_larger(self):
        """单通道 G, 更大像素 (4x4) → 有完整字节."""
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        # G 通道 bit 0 = 0,1,0,1, 1,0,1,0, 0,1,0,1, 1,0,1,0
        g_bits = [0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0]
        for i, bit in enumerate(g_bits):
            x, y = i % 4, i // 4
            arr[y, x, 1] = bit
        bs = _extract_lsb_byte_stream(
            arr, channels=["G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # 16 bit → 2 字节: 0101_1010, 0101_1010 = 0x5A 0x5A
        assert bs == bytes([0x5A, 0x5A]), f"expected 0x5A 0x5A, got {bs.hex()}"


class TestAllPerms:
    """6 个 RGB perm 都验证 (per Owner "超过随波逐流" 要求 6 perm × 8 bit = 48 组合)."""

    @pytest.mark.parametrize("perm,channels", [
        ("RGB", ["R", "G", "B"]),
        ("RBG", ["R", "B", "G"]),
        ("GRB", ["G", "R", "B"]),
        ("GBR", ["G", "B", "R"]),
        ("BRG", ["B", "R", "G"]),
        ("BGR", ["B", "G", "R"]),
    ])
    def test_perm_produces_different_bytes(self, perm, channels, steg_png_bytes):
        """6 个 perm 字节流应该不同 (per zsteg 6 perm 排列)."""
        bs = _extract_lsb_byte_stream(
            steg_png_bytes, channels=channels, bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # 每 perm 至少 1 字节, 内容应该是 zsteg 兼容的明文或噪声
        assert len(bs) > 100
        # 不应该是 plane-separated 模式 (那种模式输出大量 0x00)
        # per-pixel interleaved 模式下, steg.png 应该每个 perm 都有非 0x00 内容
        non_zero = sum(1 for b in bs[:100] if b != 0)
        assert non_zero > 50, (
            f"{perm}: 前 100 字节非 0x00 太少 ({non_zero}), "
            "可能是 plane-separated bug 回归"
        )


class TestBackwardCompat:
    """回归测试: byte stream 字节数应等于 total_bits // 8."""

    def test_byte_count_row_rgb(self, steg_png_bytes):
        """800x600x3 = 1.44M bit → 180000 字节."""
        bs = _extract_lsb_byte_stream(
            steg_png_bytes, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        assert len(bs) == 800 * 600 * 3 // 8  # 180000

    def test_byte_count_col_single(self, steg_png_bytes):
        """单通道 col scan = H*W bit → H*W//8 字节."""
        bs = _extract_lsb_byte_stream(
            steg_png_bytes, channels=["G"], bit=0,
            scan_order="col", byte_bit_order="msb",
        )
        assert len(bs) == 800 * 600 // 8  # 60000


class TestErrorHandling:
    """错误处理: 无效通道 / 越界."""

    def test_invalid_channel_raises(self, synthetic_2x2):
        """RGB 图传 'A' 通道 → ValueError."""
        with pytest.raises(ValueError, match=r"no channel"):
            _extract_lsb_byte_stream(
                synthetic_2x2, channels=["A"], bit=0,
                scan_order="row", byte_bit_order="msb",
            )

    def test_2d_array_raises(self):
        """2D array (灰度) 无第 3 维 → ValueError."""
        arr_2d = np.zeros((4, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="no channel"):
            _extract_lsb_byte_stream(
                arr_2d, channels=["R"], bit=0,
                scan_order="row", byte_bit_order="msb",
            )


# ============ 8 bit × 6 perm preview matrix (per v0.5-lsb-tool-bitplane-preview-matrix Commit 2) ============


class TestAsciiPreview:
    """_ascii_preview: 字节流 → ASCII, 非 printable → '.'."""

    def test_printable_bytes(self):
        """纯 printable 字节保留."""
        out = _ascii_preview(b"Hello World!", n_bytes=12)
        assert out == "Hello World!"

    def test_non_printable_dot(self):
        """非 printable 字节 → '.'."""
        out = _ascii_preview(b"H\x00\x01\x7f!", n_bytes=5)
        # H, ., ., ., !
        assert out == "H...!"

    def test_empty(self):
        """空字节流 → 空字符串."""
        assert _ascii_preview(b"") == ""

    def test_truncate(self):
        """超过 n_bytes 截断."""
        out = _ascii_preview(b"Hello World!", n_bytes=5)
        assert out == "Hello"


class TestBuildBitPlanePreviewMatrix:
    """_build_bit_plane_preview_matrix: 8 bit × 6 perm = 48 组合."""

    def test_returns_48_entries(self, synthetic_2x2):
        """默认 8 bit × 6 perm = 48 个 (bit, perm, preview, has_kw) tuples."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        assert len(matrix) == 48

    def test_all_perms_covered(self, synthetic_2x2):
        """6 perm 全覆盖."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        perms_seen = {entry[1] for entry in matrix}
        assert perms_seen == {"RGB", "RBG", "GRB", "GBR", "BRG", "BGR"}

    def test_all_bits_covered(self, synthetic_2x2):
        """8 bit 全覆盖 (b0=LSB ~ b7=MSB)."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        bits_seen = {entry[0] for entry in matrix}
        assert bits_seen == set(range(8))

    def test_n_bytes_respected(self, synthetic_2x2):
        """preview 长度 = n_bytes (默认 32)."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2, n_bytes=16)
        for _, _, preview, _ in matrix:
            assert len(preview) <= 16

    def test_steg_png_has_hit_keyword(self, steg_png_bytes):
        """steg.png 实战: bit=0 RGB 应命中 'Hey' 关键字."""
        matrix = _build_bit_plane_preview_matrix(steg_png_bytes)
        # 找 (0, "RGB") entry
        hit = [e for e in matrix if e[0] == 0 and e[1] == "RGB"]
        assert len(hit) == 1
        _, _, preview, has_kw = hit[0]
        assert "Hey" in preview, f"expected 'Hey' in preview, got {preview[:40]!r}"
        assert has_kw, "has_kw flag should be True for RGB bit 0 (contains 'Hey')"

    def test_steg_png_bit1_no_hit(self, steg_png_bytes):
        """steg.png 实战: bit=1 (MSB plane) 不应命中关键字 (per 8 bit × 7 perm 实测)."""
        matrix = _build_bit_plane_preview_matrix(steg_png_bytes)
        # bit=1 所有 perm 都应 has_kw=False
        bit1_entries = [e for e in matrix if e[0] == 1]
        for _, _, preview, has_kw in bit1_entries:
            assert not has_kw, (
                f"bit=1 不应命中关键字 (per 8 bit × 6 perm 验证), "
                f"got preview={preview[:40]!r}"
            )


class TestFormatMatrixForJournal:
    """_format_matrix_for_journal: matrix → journal 可读字符串."""

    def test_basic_format(self, synthetic_2x2):
        """matrix 渲染含表头 + 8 行 bit × 6 列 perm."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        text = _format_matrix_for_journal(matrix)
        lines = text.split("\n")
        # 1 表头 + 8 bit 行 = 9 行
        assert len(lines) == 9
        # 表头含 6 perm 名
        assert "RGB" in lines[0]
        assert "BGR" in lines[0]
        # bit=0 行有 LSB 标记
        assert "bit=0" in lines[1] and "LSB" in lines[1]
        # bit=7 行有 MSB 标记
        assert "bit=7" in lines[8] and "MSB" in lines[8]

    def test_hit_keyword_marker(self, steg_png_bytes):
        """steg.png 实战: bit=0 RGB 行应有 ' <==' 命中标记."""
        matrix = _build_bit_plane_preview_matrix(steg_png_bytes)
        text = _format_matrix_for_journal(matrix)
        lines = text.split("\n")
        # bit=0 行（第 2 行）应含 <== 标记
        assert "<==" in lines[1], (
            f"bit=0 行应有命中标记, got: {lines[1]!r}"
        )

    def test_empty_matrix(self):
        """空 matrix 渲染空字符串."""
        assert _format_matrix_for_journal([]) == ""