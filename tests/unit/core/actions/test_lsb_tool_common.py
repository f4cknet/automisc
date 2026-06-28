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
    _build_bit_plane_preview_matrix,
    _extract_lsb_byte_stream,
    _extract_lsb_byte_stream_zero_aware,
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
    """_build_bit_plane_preview_matrix: 8 bit × 15 channel = 120 组合 (per v0.5-lsb-tool-15channel-matrix 实战修订).

    横向表头: 15 通道 (RGB/RBG/GRB/GBR/BRG/BGR + RG0/R0B/0GB/R00/0G0/00B + R/G/B)
    纵向表头: bit (b0=LSB ~ b7=MSB)
    """

    def test_returns_120_entries(self, synthetic_2x2):
        """默认 8 bit × 15 channel = 120 个 (bit, channel, preview, has_kw) tuples."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        assert len(matrix) == 120, f"expected 120 entries, got {len(matrix)}"

    def test_all_15_channels_covered(self, synthetic_2x2):
        """15 通道全覆盖."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        channels_seen = {entry[1] for entry in matrix}
        expected = {"RGB", "RBG", "GRB", "GBR", "BRG", "BGR",
                    "RG0", "R0B", "0GB", "R00", "0G0", "00B",
                    "R", "G", "B"}
        assert channels_seen == expected, (
            f"missing: {expected - channels_seen}, extra: {channels_seen - expected}"
        )

    def test_all_bits_covered(self, synthetic_2x2):
        """8 bit 全覆盖 (b0=LSB ~ b7=MSB)."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        bits_seen = {entry[0] for entry in matrix}
        assert bits_seen == set(range(8))

    def test_n_bytes_respected(self, synthetic_2x2):
        """preview 长度 = n_bytes (默认 16, 适配 15 列宽度)."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2, n_bytes=8)
        for _, _, preview, _ in matrix:
            assert len(preview) <= 8

    def test_steg_png_has_hit_keyword(self, steg_png_bytes):
        """steg.png 实战: bit=0 RGB 应命中 'Hey' 关键字 (per Owner 截图)."""
        matrix = _build_bit_plane_preview_matrix(steg_png_bytes)
        # 找 (0, "RGB") entry
        hit = [e for e in matrix if e[0] == 0 and e[1] == "RGB"]
        assert len(hit) == 1
        _, _, preview, has_kw = hit[0]
        assert "Hey" in preview, f"expected 'Hey' in preview, got {preview[:40]!r}"
        assert has_kw, "has_kw flag should be True for RGB bit 0 (contains 'Hey')"

    def test_synthetic_lsb_text_rgb_bit0_hit(self):
        """synthetic RGB per-pixel interleaved LSB = 'Hey!' → bit=0 RGB 行命中."""
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

        matrix = _build_bit_plane_preview_matrix(arr, n_bytes=8)
        # bit=0 RGB 行应命中 'Hey'
        rgb_bit0 = next(e for e in matrix if e[0] == 0 and e[1] == "RGB")
        _, _, preview, has_kw = rgb_bit0
        assert preview.startswith("Hey"), f"got {preview[:8]!r}"
        assert has_kw


class TestFormatMatrixForJournal:
    """_format_matrix_for_journal: matrix → journal 可读字符串.

    8 bit × 15 channel 矩阵 (per v0.5-lsb-tool-15channel-matrix 实战修订).
    """

    def test_basic_format(self, synthetic_2x2):
        """matrix 渲染含表头 + 8 行 bit × 15 列 channel."""
        matrix = _build_bit_plane_preview_matrix(synthetic_2x2)
        text = _format_matrix_for_journal(matrix, col_width=16)
        lines = text.split("\n")
        # 1 表头 + 8 bit 行 = 9 行
        assert len(lines) == 9
        # 表头含 15 通道名
        for ch in ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR",
                   "RG0", "R0B", "0GB", "R00", "0G0", "00B",
                   "R", "G", "B"]:
            assert ch in lines[0], f"header missing {ch}: {lines[0]!r}"
        # bit=0 行有 LSB 标记
        assert "bit=0" in lines[1] and "LSB" in lines[1]
        # bit=7 行有 MSB 标记
        assert "bit=7" in lines[8] and "MSB" in lines[8]

    def test_hit_keyword_marker(self, steg_png_bytes):
        """steg.png 实战: bit=0 RGB 行应有 ' <==' 命中标记."""
        matrix = _build_bit_plane_preview_matrix(steg_png_bytes, n_bytes=16)
        text = _format_matrix_for_journal(matrix, col_width=16)
        lines = text.split("\n")
        # bit=0 行（第 2 行）应含 <== 标记 (steg.png RGB bit 0 命中 'Hey')
        assert "<==" in lines[1], (
            f"bit=0 行应有命中标记, got: {lines[1]!r}"
        )

    def test_empty_matrix(self):
        """空 matrix 渲染空字符串."""
        assert _format_matrix_for_journal([]) == ""

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

