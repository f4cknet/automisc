"""LSBBytesExtractAction 单测 (v0.5-lsb-byte-stream-extract 能力 B)

不依赖真实 fixture, 自己合成 PNG 用 PIL 写入。

覆盖:
- 4 参数 user-controlled (channel × bit × scan_order × byte_bit_order)
- 文件写到 input 同目录 (per v0.5-output-samedir)
- 文件名带 4 参数 (per Owner Q5)
- context 覆盖 __init__ 默认值
- 错误处理 (文件不存在 / 格式不支持 / 无效参数)
"""
from __future__ import annotations

import pytest
from pathlib import Path
from PIL import Image
import numpy as np

from automisc.core.actions.lsb_bytes_extract import (
    LSBBytesExtractAction,
    _parse_channels,
    _channel_index,
    _extract_bits_from_image,
    _bits_to_bytes,
    _output_filename,
)


# ---------- fixtures: 合成 PNG 测试图 ----------
@pytest.fixture
def synthetic_png(tmp_path) -> Path:
    """合成 4×4 PNG, 像素值已知, 方便测 4 参数.
    
    像素布局 (R,G,B):
    Row 0: (0,0,0) (1,1,1) (2,2,2) (3,3,3)
    Row 1: (4,4,4) (5,5,5) (6,6,6) (7,7,7)
    Row 2: (8,8,8) (9,9,9) (10,10,10) (11,11,11)
    Row 3: (12,12,12) (13,13,13) (14,14,14) (15,15,15)
    """
    arr = np.arange(16, dtype=np.uint8).reshape(4, 4, 1).repeat(3, axis=2)
    img = Image.fromarray(arr, mode="RGB")
    path = tmp_path / "synthetic.png"
    img.save(path)
    return path


# ---------- _parse_channels 测试 ----------
class TestParseChannels:
    def test_string_comma(self):
        assert _parse_channels("R,G,B") == ["R", "G", "B"]

    def test_string_concat(self):
        # 'RGB' 也支持 (兼容 GUI input 区连续字母)
        assert _parse_channels("RGB") == ["R", "G", "B"]

    def test_list(self):
        assert _parse_channels(["G", "B"]) == ["G", "B"]

    def test_dedupe(self):
        assert _parse_channels("R,R,G") == ["R", "G"]

    def test_lowercase_normalize(self):
        assert _parse_channels("r,g") == ["R", "G"]

    def test_invalid_channel_raises(self):
        with pytest.raises(ValueError, match="invalid channels"):
            _parse_channels("X")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            _parse_channels("")


# ---------- _channel_index 测试 ----------
class TestChannelIndex:
    def test_r(self):
        assert _channel_index("R") == 0

    def test_g(self):
        assert _channel_index("G") == 1

    def test_b(self):
        assert _channel_index("B") == 2

    def test_a(self):
        assert _channel_index("A") == 3


# ---------- _extract_bits_from_image 测试 ----------
class TestExtractBits:
    def test_row_scan_channel_g(self, synthetic_png):
        img = np.array(Image.open(synthetic_png).convert("RGB"))
        bits = _extract_bits_from_image(img, channels=["G"], bit=0, scan_order="row")
        # G 通道 row-scan flatten = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]
        # bit 0 = LSB, 偶数 → 0, 奇数 → 1
        expected = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=np.uint8)
        np.testing.assert_array_equal(bits, expected)

    def test_col_scan_channel_g(self, synthetic_png):
        img = np.array(Image.open(synthetic_png).convert("RGB"))
        bits = _extract_bits_from_image(img, channels=["G"], bit=0, scan_order="col")
        # G 通道 col-scan = 外层 w 内层 h = [[0,4,8,12],[1,5,9,13],[2,6,10,14],[3,7,11,15]]
        # bit 0: [0,0,0,0, 1,1,1,1, 0,0,0,0, 1,1,1,1]
        expected = np.array([0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1], dtype=np.uint8)
        np.testing.assert_array_equal(bits, expected)

    def test_bit_7(self, synthetic_png):
        # 像素值都 < 128, bit 7 全是 0
        img = np.array(Image.open(synthetic_png).convert("RGB"))
        bits = _extract_bits_from_image(img, channels=["R"], bit=7, scan_order="row")
        np.testing.assert_array_equal(bits, np.zeros(16, dtype=np.uint8))

    def test_multiple_channels_concat(self, synthetic_png):
        # 3 通道拼接 = 16 * 3 = 48 bits
        img = np.array(Image.open(synthetic_png).convert("RGB"))
        bits = _extract_bits_from_image(img, channels=["R", "G", "B"], bit=0, scan_order="row")
        assert len(bits) == 48


# ---------- _bits_to_bytes 测试 ----------
class TestBitsToBytes:
    def test_msb_basic(self):
        bits = np.array([0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)
        # MSB first: 01000001 = 0x41 = 'A', 10101010 = 0xaa
        result = _bits_to_bytes(bits, "MSB")
        assert result == b'\x41\xaa'

    def test_lsb_basic(self):
        bits = np.array([0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)
        # LSB first (字节内反序): 10000010 = 0x82, 01010101 = 0x55
        result = _bits_to_bytes(bits, "LSB")
        assert result == b'\x82\x55'

    def test_trim_to_byte_boundary(self):
        bits = np.array([0, 1, 0, 0, 0, 0, 0, 1, 0, 1], dtype=np.uint8)  # 10 bits
        result = _bits_to_bytes(bits, "MSB")
        assert len(result) == 1  # 10 // 8 = 1 byte


# ---------- _output_filename 测试 ----------
class TestOutputFilename:
    def test_single_channel(self):
        name = _output_filename(["G"], 0, "col", "MSB")
        assert name == "lsb_g_b0_col_msb"

    def test_multiple_channels(self):
        name = _output_filename(["R", "G", "B"], 7, "row", "MSB")
        assert name == "lsb_rgb_b7_row_msb"


# ---------- LSBBytesExtractAction.run 测试 ----------
class TestLSBBytesExtractAction:
    def test_default_rgb_row_msb(self, synthetic_png):
        """默认 RGB row MSB 抽出, 验证 raw_size + 文件路径 + 同目录."""
        action = LSBBytesExtractAction()
        result = action.run({"file_path": str(synthetic_png)})

        assert result.success is True
        assert "lsb_bytes" in result.data
        assert result.data["lsb_bytes"]["channels"] == ["R", "G", "B"]
        assert result.data["lsb_bytes"]["bit"] == 0
        assert result.data["lsb_bytes"]["scan_order"] == "row"
        assert result.data["lsb_bytes"]["byte_bit_order"] == "MSB"
        # 3 通道 × 16 像素 = 48 bits → 6 bytes
        assert result.data["lsb_bytes"]["raw_size"] == 6

        # 验证文件落到 input 同目录
        out_path = Path(result.data["lsb_bytes"]["extracted_path"])
        assert out_path.parent == synthetic_png.parent
        assert out_path.exists()
        assert out_path.name == "synthetic__lsb_rgb_b0_row_msb.bin"
        assert result.data["extracted_files"] == [str(out_path)]

    def test_single_channel_col_msb(self, synthetic_png):
        """单通道 col scan = writeup 顺序."""
        action = LSBBytesExtractAction(
            channels=["G"], bit=0, scan_order="col", byte_bit_order="MSB"
        )
        result = action.run({"file_path": str(synthetic_png)})

        assert result.success is True
        assert result.data["lsb_bytes"]["channels"] == ["G"]
        assert result.data["lsb_bytes"]["scan_order"] == "col"
        # 16 像素 / 8 = 2 bytes
        assert result.data["lsb_bytes"]["raw_size"] == 2

        out_path = Path(result.data["lsb_bytes"]["extracted_path"])
        assert out_path.name == "synthetic__lsb_g_b0_col_msb.bin"

    def test_context_override_init(self, synthetic_png):
        """context 覆盖 __init__ 默认值."""
        action = LSBBytesExtractAction()  # 默认 RGB row MSB
        result = action.run({
            "file_path": str(synthetic_png),
            "channels": "B",  # 覆盖
            "scan_order": "col",  # 覆盖
        })

        assert result.success is True
        assert result.data["lsb_bytes"]["channels"] == ["B"]
        assert result.data["lsb_bytes"]["scan_order"] == "col"

    def test_bit_7_no_data(self, synthetic_png):
        """所有像素 < 128, bit 7 全 0 → 抽到全 0 字节流."""
        action = LSBBytesExtractAction(
            channels=["R"], bit=7, scan_order="row"
        )
        result = action.run({"file_path": str(synthetic_png)})

        assert result.success is True
        # 16 bits → 2 bytes, 全 0
        assert result.data["lsb_bytes"]["raw_size"] == 2

        out_path = Path(result.data["lsb_bytes"]["extracted_path"])
        assert out_path.read_bytes() == b'\x00\x00'

    def test_missing_file_path(self):
        action = LSBBytesExtractAction()
        result = action.run({})
        assert result.success is False
        assert "missing 'file_path'" in result.message

    def test_file_not_found(self, tmp_path):
        action = LSBBytesExtractAction()
        result = action.run({"file_path": str(tmp_path / "nonexistent.png")})
        assert result.success is False
        assert "file not found" in result.message

    def test_invalid_channel_param(self):
        with pytest.raises(ValueError, match="bit must be 0..7"):
            LSBBytesExtractAction(bit=8)

    def test_invalid_scan_order_param(self):
        with pytest.raises(ValueError, match="scan_order must be row/col"):
            LSBBytesExtractAction(scan_order="diagonal")

    def test_invalid_byte_bit_order_param(self):
        with pytest.raises(ValueError, match="byte_bit_order must be MSB/LSB"):
            LSBBytesExtractAction(byte_bit_order="BE")

    def test_message_includes_4_params(self, synthetic_png):
        """message 应该包含所有 4 个参数 + 路径 + 字节数."""
        action = LSBBytesExtractAction(
            channels=["G"], bit=0, scan_order="col", byte_bit_order="MSB"
        )
        result = action.run({"file_path": str(synthetic_png)})

        assert "channels=G" in result.message
        assert "bit=0" in result.message
        assert "scan=col" in result.message
        assert "byte_order=MSB" in result.message
        assert "synthetic__lsb_g_b0_col_msb.bin" in result.message
        assert "2 bytes" in result.message
