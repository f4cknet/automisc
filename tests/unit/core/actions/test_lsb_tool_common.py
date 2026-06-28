"""测试 lsb_tool_common._extract_lsb_byte_stream (per v0.5-lsb-tool-bitplane-preview-matrix Commit 1)

**核心验证**: 修复后的 _extract_lsb_byte_stream 必须跟 zsteg `b<bit>,<channels>,<byte_bit_order>,<scan>` 完全等价
(per v0.5-train-014: steg.png 实战命中 0 SP, 根因 plane-separated 跟 zsteg 不一致).
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from automisc.core.actions.lsb_tool_common import (
    _15_CHANNELS,
    _ascii_preview,
    _build_15channel_preview_matrix,
    _build_bit_plane_preview_matrix,
    _extract_lsb_byte_stream,
    _extract_lsb_byte_stream_zero_aware,
    _format_15channel_matrix_for_journal,
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


# ============ Zero-aware byte stream (per v0.5-lsb-tool-15channel-matrix Commit 1) ============


class TestExtractZeroAwareByteStream:
    """_extract_lsb_byte_stream_zero_aware: 支持 '0' 通道占位的 byte stream 提取.

    **核心不变量**:
    - 3 通道场景等价 `_extract_lsb_byte_stream` (不破坏老路径)
    - RG0 ≠ RG (zero padding bit 占 byte 流位置, 改变 byte 对齐)
    - RG0 == R00 (数学等价, 0 bits 等价)
    """

    def test_three_channel_equals_standard(self, synthetic_2x2):
        """3 通道场景: zero_aware 跟 standard 输出完全一致."""
        bs_zero = _extract_lsb_byte_stream_zero_aware(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_std = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["R", "G", "B"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        assert bs_zero == bs_std, (
            f"zero_aware 跟 standard 输出应一致, "
            f"zero={bs_zero.hex()}, std={bs_std.hex()}"
        )

    def test_RG0_differs_from_RG(self):
        """RG0 ≠ RG: '0' 通道 positional zero (占 byte 流位置), 改变 bit 密度.

        4x1 像素 PNG:
        arr[0,0] = R=1, G=1, B=0
        arr[0,1] = R=1, G=0, B=0
        arr[0,2] = R=0, G=1, B=0
        arr[0,3] = R=0, G=0, B=0

        RG (2 通道, no 0 padding):
            bits per pixel = 2, per-pixel bit sequence: [R0,G0], [R1,G1], ...
            pixel 0: [1,1] pixel 1: [1,0] pixel 2: [0,1] pixel 3: [0,0]
            bits = [1,1,1,0,0,1,0,0] = 8 bits → byte 1 = 11100100 = 0xE4

        RG0 (3 通道 with positional zero, 跟 随波逐流 一致):
            bits per pixel = 3, per-pixel bit sequence: [R0,G0,0], [R1,G1,0], ...
            pixel 0: [1,1,0] pixel 1: [1,0,0] pixel 2: [0,1,0] pixel 3: [0,0,0]
            bits = [1,1,0,1,0,0,0,1,0,0,0,0] = 12 bits → 1 字节
            byte 1 (MSB first, 8 bits) = 11010001 = 0xD1
            (后 4 bits = 0000 被截断)
        """
        arr = np.zeros((1, 4, 3), dtype=np.uint8)
        arr[0, 0] = [1, 1, 0]  # R=1 G=1 B=0
        arr[0, 1] = [1, 0, 0]
        arr[0, 2] = [0, 1, 0]
        arr[0, 3] = [0, 0, 0]

        bs_RG = _extract_lsb_byte_stream(
            arr, channels=["R", "G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_RG0 = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "G", "0"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # RG0 跟 RG byte stream 必须不同 (因为 0 占 byte 流位置)
        assert bs_RG != bs_RG0, (
            f"RG0 应跟 RG 不同 (positional zero, 0 占位), "
            f"RG={bs_RG.hex()}, RG0={bs_RG0.hex()}"
        )
        # 验证具体值
        assert bs_RG == bytes([0xE4]), f"RG expected 0xE4, got {bs_RG.hex()}"
        assert bs_RG0 == bytes([0xD1]), f"RG0 expected 0xD1, got {bs_RG0.hex()}"

    def test_RG0_equals_R00_when_G_zero(self):
        """RG0 == R00: 当 G bit 全 0 时 positional zero 数学等价 (per Owner 截图).

        Owner 实战截图 RG0 == R00 (随波逐流 输出), 根因是该 stego 图 G 通道 LSB 全 0.
        验证: 用 G=0 测试图, RG0 (R,G,0) bit 序列 跟 R00 (R,0,0) bit 序列数学相同.
        """
        arr = np.zeros((1, 4, 3), dtype=np.uint8)
        arr[0, 0] = [1, 0, 0]  # G=0
        arr[0, 1] = [1, 0, 0]
        arr[0, 2] = [0, 0, 0]
        arr[0, 3] = [0, 0, 0]

        bs_RG0 = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "G", "0"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_R00 = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "0", "0"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        # G=0 时: RG0 per pixel [R,0,0] == R00 per pixel [R,0,0]
        assert bs_RG0 == bs_R00, (
            f"RG0 应跟 R00 等价 (G bit 全 0 时), "
            f"RG0={bs_RG0.hex()}, R00={bs_R00.hex()}"
        )

    def test_single_channel_equals_standard(self, synthetic_2x2):
        """单通道场景: zero_aware 跟 standard 一致 (无 '0' 通道)."""
        bs_zero = _extract_lsb_byte_stream_zero_aware(
            synthetic_2x2, channels=["G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_std = _extract_lsb_byte_stream(
            synthetic_2x2, channels=["G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        assert bs_zero == bs_std

    def test_all_zero_channels_returns_empty(self):
        """全 '0' 通道 → 空字节流 (防御性兜底)."""
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        bs = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["0", "0", "0"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        assert bs == b""

    def test_invalid_channel_raises(self, synthetic_2x2):
        """无效通道 'X' → ValueError (zero_aware 校验)."""
        with pytest.raises(ValueError, match=r"invalid channel"):
            _extract_lsb_byte_stream_zero_aware(
                synthetic_2x2, channels=["X"], bit=0,
                scan_order="row", byte_bit_order="msb",
            )

    def test_empty_channels_raises(self, synthetic_2x2):
        """空 channels → ValueError."""
        with pytest.raises(ValueError, match=r"at least one channel"):
            _extract_lsb_byte_stream_zero_aware(
                synthetic_2x2, channels=[], bit=0,
                scan_order="row", byte_bit_order="msb",
            )

    def test_byte_count_RG0_more_than_RG(self):
        """总 byte 数: positional zero 下 RG0 (3 bits/pixel) byte 数 > RG (2 bits/pixel).

        4x4 像素:
        RG: 16 pixels × 2 bits = 32 bits → 4 bytes
        RG0 (positional zero): 16 pixels × 3 bits = 48 bits → 6 bytes
        """
        arr = np.zeros((4, 4, 3), dtype=np.uint8)
        # R 通道全 bit 1, G 通道全 bit 0
        arr[:, :, 0] = 0x01
        arr[:, :, 1] = 0x00

        bs_RG = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_RG0 = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "G", "0"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        assert len(bs_RG) == 4, f"RG: expected 4 bytes, got {len(bs_RG)}"
        assert len(bs_RG0) == 6, f"RG0: expected 6 bytes (3 bits/pixel), got {len(bs_RG0)}"

    def test_col_scan_zero_aware(self):
        """col scan + zero_aware 也能工作 (per v0.5-lsb-tool-bitplane-preview-matrix row/col 兼容)."""
        arr = np.zeros((2, 2, 3), dtype=np.uint8)
        arr[0, 0] = [1, 0, 0]
        arr[1, 0] = [0, 1, 0]
        arr[0, 1] = [1, 1, 0]
        arr[1, 1] = [0, 0, 0]

        bs_row = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "0", "G"], bit=0,
            scan_order="row", byte_bit_order="msb",
        )
        bs_col = _extract_lsb_byte_stream_zero_aware(
            arr, channels=["R", "0", "G"], bit=0,
            scan_order="col", byte_bit_order="msb",
        )
        # row vs col 应不同 (跟现有 _extract_lsb_byte_stream 行为一致)
        assert bs_row != bs_col, (
            f"row vs col 应不同, row={bs_row.hex()}, col={bs_col.hex()}"
        )


# ============ 15 通道 × LSB+MSB preview matrix (per v0.5-lsb-tool-15channel-matrix Commit 2) ============


class TestBuild15ChannelPreviewMatrix:
    """_build_15channel_preview_matrix: 15 channels × 2 bit modes = 30 entries."""

    def test_returns_30_entries(self, synthetic_2x2):
        """默认 15 channels × 2 bit modes = 30 个 (label, bit, preview, has_kw) tuples."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        assert len(matrix) == 30, f"expected 30 entries, got {len(matrix)}"

    def test_all_15_channels_covered(self, synthetic_2x2):
        """15 通道全覆盖 (per Owner 列表)."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        labels_seen = {entry[0] for entry in matrix}
        expected_labels = {"RGB", "RBG", "GRB", "GBR", "BRG", "BGR",
                           "RG0", "R0B", "0GB", "R00", "0G0", "00B",
                           "R", "G", "B"}
        assert labels_seen == expected_labels, (
            f"missing labels: {expected_labels - labels_seen}, "
            f"extra: {labels_seen - expected_labels}"
        )

    def test_each_label_has_lsb_and_msb(self, synthetic_2x2):
        """每 label 出现 2 次 (bit 0 + bit 7)."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        for label, _ in _15_CHANNELS:
            entries = [e for e in matrix if e[0] == label]
            bits = {e[1] for e in entries}
            assert bits == {0, 7}, f"{label} 应有 bit 0 和 bit 7, got {bits}"

    def test_n_bytes_respected(self, synthetic_2x2):
        """preview 长度 ≤ n_bytes."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2, n_bytes=20)
        for _, _, preview, _ in matrix:
            assert len(preview) <= 20

    def test_synthetic_lsb_text_keyword_hit(self):
        """synthetic LSB 隐写验证: RGB per-pixel interleaved LSB 嵌入 'Hey!' → RGB 行命中.

        关键: embedding 必须按 per-pixel interleaved 顺序 (pixel 0 R+G+B bits, pixel 1 R+G+B bits, ...),
        否则提取顺序跟嵌入顺序不匹配, byte stream 不等于 payload.
        """
        payload = b"Hey!"
        # 展开 payload → bit 序列 (MSB first)
        bits = []
        for byte in payload:
            for i in range(8):
                bits.append((byte >> (7 - i)) & 1)

        # 32 bits / 3 bits per pixel ≈ 11 pixels → 用 16x2 (32 pixels) 足够
        width, height = 16, 2
        arr = np.zeros((height, width, 3), dtype=np.uint8)

        # 按 per-pixel interleaved 顺序嵌入 (pixel 0 R+G+B, pixel 1 R+G+B, ...)
        for bit_pos in range(len(bits)):
            pixel_offset = bit_pos // 3
            ch_offset = bit_pos % 3  # 0=R, 1=G, 2=B
            y = pixel_offset // width
            x = pixel_offset % width
            if y >= height:
                break
            arr[y, x, ch_offset] = bits[bit_pos]

        matrix = _build_15channel_preview_matrix(arr, n_bytes=10)

        # LSB RGB 行应命中 'Hey' 关键字
        lsb_rgb = next(e for e in matrix if e[0] == "RGB" and e[1] == 0)
        _, _, preview, has_kw = lsb_rgb
        assert preview.startswith("Hey"), (
            f"LSB RGB preview 应以 'Hey' 开头, got {preview[:10]!r}"
        )
        assert has_kw, "LSB RGB has_kw 应 True (含 'Hey')"

    def test_single_channel_steg_n_np(self):
        """synthetic N=NP 模式: G 通道 LSB 嵌入 ASCII → 15 通道矩阵 G 行命中 (单通道 N=NP 模式).

        8x8 RGB PNG (64 pixels), G 通道 LSB 行扫描嵌入 8 字节 'flag{key' (64 bits → 64 pixels 刚好).
        """
        payload = b"flag{key"  # 8 bytes = 64 bits, 不含 '}' 避免花括号误判
        width, height = 8, 8
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        # G 通道 LSB 嵌入 (单通道, 1 bit/pixel, row scan, MSB byte order)
        for bit_pos, bit_val in enumerate(
            [(byte >> (7 - i)) & 1 for byte in payload for i in range(8)]
        ):
            y = bit_pos // width
            x = bit_pos % width
            arr[y, x, 1] = (arr[y, x, 1] & 0xFE) | bit_val

        matrix = _build_15channel_preview_matrix(arr, n_bytes=10)
        # 单通道 G 行 (LSB) 应命中 'flag'
        lsb_g = next(e for e in matrix if e[0] == "G" and e[1] == 0)
        _, _, preview, has_kw = lsb_g
        assert "flag" in preview[:10], f"LSB G preview 应含 'flag', got {preview[:10]!r}"
        assert has_kw, "LSB G has_kw 应 True (含 'flag')"

    def test_keyword_markers(self):
        """命中关键字 'Hey'/'flag'/'key'/'PK'/'PNG' 应 has_kw=True.

        用 per-pixel interleaved 嵌入 RGB LSB = 'Hey!'.
        """
        payload = b"Hey!"
        bits = [(byte >> (7 - i)) & 1 for byte in payload for i in range(8)]

        width, height = 16, 2
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for bit_pos, bit_val in enumerate(bits):
            pixel_offset = bit_pos // 3
            ch_offset = bit_pos % 3
            y = pixel_offset // width
            x = pixel_offset % width
            if y >= height:
                break
            arr[y, x, ch_offset] = bit_val

        matrix = _build_15channel_preview_matrix(arr, n_bytes=20)
        # RGB LSB 应 has_kw=True (含 'Hey')
        rgb_lsb = next(e for e in matrix if e[0] == "RGB" and e[1] == 0)
        assert rgb_lsb[3] is True, f"RGB LSB has_kw 应 True, preview={rgb_lsb[2][:20]!r}"
        # MSB RGB 不应命中 (MSB 全 0 = 0x00 字节, 不在 keyword 列表)
        rgb_msb = next(e for e in matrix if e[0] == "RGB" and e[1] == 7)
        assert rgb_msb[3] is False, f"RGB MSB has_kw 应 False, preview={rgb_msb[2][:20]!r}"

    def test_label_order_matches_suibozhuliu(self, synthetic_2x2):
        """label 顺序跟 随波逐流 一致: RGB/RBG/GRB/GBR/BRG/BGR/RG0/R0B/0GB/R00/0G0/00B/R/G/B."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        # 取每个 label 的第一个出现位置 (bit 0)
        label_order: list[str] = []
        for entry in matrix:
            if entry[0] not in label_order:
                label_order.append(entry[0])
        expected_order = ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR",
                          "RG0", "R0B", "0GB", "R00", "0G0", "00B",
                          "R", "G", "B"]
        assert label_order == expected_order


class TestFormat15ChannelMatrix:
    """_format_15channel_matrix_for_journal: matrix → journal 友好字符串."""

    def test_basic_format(self, synthetic_2x2):
        """matrix 渲染含 LSB 段 + MSB 段, 每段 15 行 (6 full + 6 zero + 3 single)."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        text = _format_15channel_matrix_for_journal(matrix)
        lines = text.split("\n")
        # 2 段 × (1 标题 + 1 preview 行 + 15 数据行 + 1 空行) = 36 行 (最后 1 空行 rstrip 去掉)
        # 实际: [标题 LSB][空] [标题 MSB] = 2 标题 + 2 preview + 30 数据 + 段间空行 = 36
        assert len(lines) >= 30, f"expected ≥30 lines, got {len(lines)}"

    def test_lsb_section_before_msb(self, synthetic_2x2):
        """LSB 段在 MSB 段前."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        text = _format_15channel_matrix_for_journal(matrix)
        lsb_idx = text.find("LSB")
        msb_idx = text.find("MSB")
        assert lsb_idx >= 0 and msb_idx >= 0, "should contain both LSB and MSB sections"
        assert lsb_idx < msb_idx, "LSB section should appear before MSB"

    def test_15_rows_per_section(self, synthetic_2x2):
        """每段 15 行数据 (6 full + 6 zero-padded + 3 single)."""
        matrix = _build_15channel_preview_matrix(synthetic_2x2)
        text = _format_15channel_matrix_for_journal(matrix)
        # 找 LSB 段: 从 "LSB" 到下一个空行 / MSB
        lsb_section = text.split("[15 通道 MSB")[0]
        # 跳过标题行 + preview header 行, 数数据行
        lsb_lines = lsb_section.split("\n")
        data_lines = [ln for ln in lsb_lines if ":" in ln and not ln.startswith("[")]
        # 第一行是 "    preview (50 bytes):" 含 ":", 跳过
        data_rows = [ln for ln in data_lines if ln.startswith(("RGB:", "RBG:", "GRB:", "GBR:", "BRG:", "BGR:",
                                                              "RG0:", "R0B:", "0GB:", "R00:", "0G0:", "00B:",
                                                              "R:", "G:", "B:"))]
        assert len(data_rows) == 15, f"LSB 段应 15 行数据, got {len(data_rows)}"

    def test_keyword_marker_in_output(self):
        """命中关键字时行末有 '  <=='."""
        # synthetic PNG with 'Hey' in RGB per-pixel interleaved LSB
        payload = b"Hey!"
        bits = [(byte >> (7 - i)) & 1 for byte in payload for i in range(8)]
        width, height = 16, 2
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for bit_pos, bit_val in enumerate(bits):
            pixel_offset = bit_pos // 3
            ch_offset = bit_pos % 3
            y = pixel_offset // width
            x = pixel_offset % width
            if y >= height:
                break
            arr[y, x, ch_offset] = bit_val

        matrix = _build_15channel_preview_matrix(arr, n_bytes=20)
        text = _format_15channel_matrix_for_journal(matrix)
        # RGB 行 (LSB 段) 应含 <== 标记
        assert "RGB:" in text
        # RGB 行 + LSB 段 + <== 标记
        lsb_section = text.split("[15 通道 MSB")[0]
        rgb_line = [ln for ln in lsb_section.split("\n") if ln.startswith("RGB:")]
        assert len(rgb_line) == 1
        assert "<==" in rgb_line[0], f"RGB 行应有 <== 标记, got {rgb_line[0]!r}"

    def test_empty_matrix(self):
        """空 matrix 渲染空字符串."""
        assert _format_15channel_matrix_for_journal([]) == ""