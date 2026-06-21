"""LSBDetectAction 单测 (v0.5-lsb-detector)

不依赖真实 fixture, 自己合成 PNG 用 PIL 写入。
覆盖 (per spec §6 ②'):
- text 判定: printable ASCII 32-126 (per Owner 21:29 拍板)
- 文件头判定: hex magic (25+ entry 库) + file 命令辅 (libmagic 兜底)
- 12 组合 LSB bit 0 抽字节流 (6 排列 × 2 scan)
- 3 通道 8 bit 概率检测 (entropy + unique)
- readonly 铁律: 不写文件
- 错误处理 (文件不存在 / 缺 file_path)
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from automisc.core.actions.lsb_detect import (
    LSBDetectAction,
    _channel_8bit_byte_stream,
    _detect_file_header_hex,
    _is_printable_text,
    _perm_name,
    _shannon_entropy,
    _unique_count,
)


# ---------- fixtures: 合成 PNG 测试图 ----------
@pytest.fixture
def synthetic_text_png(tmp_path) -> Path:
    """合成 PNG, 嵌入 'Hello, World!Hello, World!' 字符串到 RGB 三通道 bit 0.

    嵌入方式:
    - 24 字节 = 192 bit, 8x8=64 像素 × 3 通道
    - 3 通道 bit 0 各自填同一 printable 字节流的 bit 模式
    - 12 组合 (6 排列 × 2 scan) 字节流都是 R+G+B 拼起来, 全 printable
    """
    arr = np.zeros((8, 8, 3), dtype=np.uint8)  # 8x8 RGB, 默认全 0
    text_bytes = b"Hello, World!Hello, World!"  # 24 byte printable
    # 写 24 byte = 192 bit 到 3 通道 (各 64 bit = 8 byte)
    bit_idx = 0
    for ch_idx in range(3):  # R / G / B
        for byte in text_bytes:
            for bit_pos in range(8):
                if bit_idx >= 64:
                    break
                row = bit_idx // 8
                col = bit_idx % 8
                b = (byte >> (7 - bit_pos)) & 1
                arr[row, col, ch_idx] = (arr[row, col, ch_idx] & 0xFE) | b
                bit_idx += 1
            if bit_idx >= 64:
                break
        bit_idx = 0  # 重置, 3 通道都写同样 8 byte
    png_path = tmp_path / "text.png"
    Image.fromarray(arr).save(png_path)
    return png_path


@pytest.fixture
def synthetic_zip_png(tmp_path) -> Path:
    """合成 PNG, 嵌入 ZIP magic (50 4B 03 04) 到 RGB 通道 bit 0.

    ZIP 头 4 字节 = 0x504B0304, 二进制:
      0x50 = 01010000
      0x4B = 01001011
      0x03 = 00000011
      0x04 = 00000100
    32 bit, 写满前 32 像素 (R 通道 bit 0)
    """
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    zip_bytes = b"PK\x03\x04" + b"\x00" * 28  # 4 字节 magic + 28 字节 padding
    bits = []
    for byte in zip_bytes:
        for bit_pos in range(8):
            bits.append((byte >> (7 - bit_pos)) & 1)
    for i, b in enumerate(bits[:64]):
        row = i // 8
        col = i % 8
        arr[row, col, 0] = (arr[row, col, 0] & 0xFE) | b
    png_path = tmp_path / "zip.png"
    Image.fromarray(arr).save(png_path)
    return png_path


@pytest.fixture
def synthetic_uniform_png(tmp_path) -> Path:
    """合成 PNG, R=0 / G=255 / B=128 (非均匀 — G 通道高 entropy).

    8 bit 字节流: R 通道 byte_stream 全 0x00 (low entropy),
                  G 通道 byte_stream 全 0xFF (low entropy 但均匀),
                  B 通道 byte_stream 全 0x80 (low entropy 但均匀).
    这种情况下 entropy 都低, 不会触发 channel_anomaly.

    真正触发 channel_anomaly 需要混合 256 个值, 需特殊合成.
    """
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    arr[..., 0] = 0
    arr[..., 1] = 255
    arr[..., 2] = 128
    png_path = tmp_path / "uniform.png"
    Image.fromarray(arr).save(png_path)
    return png_path


@pytest.fixture
def synthetic_high_entropy_png(tmp_path) -> Path:
    """合成 PNG, 制造 G 通道 8 bit 字节流 entropy > 5.0 + unique >= 200 (高).

    思路: G 通道每像素值 (x*13 + y*7) % 256 — 16x16=256 像素, 接近均匀分布.
    实测: 229 unique + entropy 7.789 (满足阈值 5.0 + 200).
    R / B 通道: 全 0 (low entropy baseline, 不触发 anomaly).
    """
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    for y in range(16):
        for x in range(16):
            arr[y, x, 0] = 0  # R 全 0
            arr[y, x, 1] = (x * 13 + y * 7) % 256  # G 高 entropy
            arr[y, x, 2] = 0  # B 全 0
    png_path = tmp_path / "high_entropy.png"
    Image.fromarray(arr).save(png_path)
    return png_path


# ============================================================
# 单元测试: 工具函数
# ============================================================

class TestIsPrintableText:
    """text 判定: printable ASCII 32-126 区间 (per Owner 21:29 拍板)."""

    def test_is_printable_text_true(self):
        """全 printable ASCII = text."""
        assert _is_printable_text(b"Hello, World!") is True

    def test_is_printable_text_with_numbers(self):
        """数字 + 字母 + 标点 = text."""
        assert _is_printable_text(b"flag{test_123}") is True

    def test_is_not_printable_text_with_null(self):
        """含 \\x00 = 不是 text."""
        assert _is_printable_text(b"Hello\x00World") is False

    def test_is_not_printable_text_with_high_bit(self):
        """含 \\x80+ 高位 = 不是 text (非 ASCII)."""
        assert _is_printable_text(b"Hello\xc0\x80World") is False

    def test_is_empty_text_false(self):
        """空字节流 = 不是 text (per implementation, return False)."""
        assert _is_printable_text(b"") is False


class TestDetectFileHeaderHex:
    """hex magic 主判定 (per spec Q3=A 双机制: hex 主 + file 辅)."""

    def test_zip_magic(self):
        """ZIP magic 0x504B0304 = ('zip', 'ZIP archive')."""
        result = _detect_file_header_hex(b"PK\x03\x04rest bytes")
        assert result == ("zip", "ZIP archive")

    def test_zip_empty_archive(self):
        """ZIP empty 0x504B0506."""
        result = _detect_file_header_hex(b"PK\x05\x06rest")
        assert result == ("zip", "ZIP empty archive")

    def test_rar_magic(self):
        """RAR magic 'Rar!\\x1a\\x07' = ('rar', 'RAR archive')."""
        result = _detect_file_header_hex(b"Rar!\x1a\x07rest")
        assert result == ("rar", "RAR archive")

    def test_png_magic(self):
        """PNG magic 0x89504E470D0A1A0A = ('png', 'PNG image')."""
        result = _detect_file_header_hex(b"\x89PNG\r\n\x1a\nrest")
        assert result == ("png", "PNG image")

    def test_pyc_27_magic(self):
        """Py 2.7 magic 0x03F30D0A = ('pyc', 'Python 2.7 bytecode')."""
        result = _detect_file_header_hex(b"\x03\xf3\r\nrest")
        assert result == ("pyc", "Python 2.7 bytecode")

    def test_pyc_38_magic(self):
        """Py 3.8 magic 0x550D0D0A = ('pyc', 'Python 3.8 bytecode')."""
        result = _detect_file_header_hex(b"\x55\x0d\r\nrest")
        assert result == ("pyc", "Python 3.8 bytecode")

    def test_elf_magic(self):
        """ELF magic 0x7F454C46 = ('elf', 'ELF executable')."""
        result = _detect_file_header_hex(b"\x7fELF\x02\x01\x01rest")
        assert result == ("elf", "ELF executable")

    def test_no_magic_match(self):
        """无 magic 匹配 = None."""
        result = _detect_file_header_hex(b"random data here without any magic")
        assert result is None

    def test_too_short(self):
        """字节流太短 (< 4 字节) = None."""
        assert _detect_file_header_hex(b"PK") is None
        assert _detect_file_header_hex(b"") is None


class TestShannonEntropy:
    """香农熵 (max=8.0 for byte)."""

    def test_entropy_uniform(self):
        """均匀分布 byte stream entropy 高."""
        # 0-255 各 1 次, 256 字节, 完全均匀
        byte_stream = bytes(range(256))
        ent = _shannon_entropy(byte_stream)
        assert ent == pytest.approx(8.0, abs=0.01)  # log2(256) = 8.0

    def test_entropy_constant(self):
        """常量 byte stream entropy = 0."""
        byte_stream = b"\x00" * 100
        assert _shannon_entropy(byte_stream) == 0.0

    def test_entropy_two_values(self):
        """2 个值各 50%, entropy = 1.0."""
        byte_stream = b"\x00" * 50 + b"\x01" * 50
        ent = _shannon_entropy(byte_stream)
        assert ent == pytest.approx(1.0, abs=0.01)

    def test_entropy_empty(self):
        """空字节流 = 0."""
        assert _shannon_entropy(b"") == 0.0


class TestUniqueCount:
    """unique byte count."""

    def test_unique_all_256(self):
        """0-255 各 1 次 = 256."""
        assert _unique_count(bytes(range(256))) == 256

    def test_unique_constant(self):
        """常量 = 1."""
        assert _unique_count(b"\x00" * 100) == 1

    def test_unique_empty(self):
        """空 = 0."""
        assert _unique_count(b"") == 0


class TestChannel8BitByteStream:
    """单通道 8 bit 字节流: 1 像素 = 1 byte (per PIL Image.getpixel() 风格)."""

    def test_basic_extraction(self):
        """基础提取: 8 像素 plane, 每像素值 0x01 → 8 字节全 0x01."""
        plane = np.full((8, 1), 0x01, dtype=np.uint8)
        result = _channel_8bit_byte_stream(plane)
        assert result == b"\x01" * 8

    def test_zero_plane(self):
        """全 0 plane = 全 0 字节流 (len = 像素数)."""
        plane = np.zeros((8, 8), dtype=np.uint8)
        result = _channel_8bit_byte_stream(plane)
        assert len(result) == 64  # 8*8 = 64 像素
        assert result == b"\x00" * 64


class TestPermName:
    """6 排列名映射."""

    def test_perm_names(self):
        """6 排列对应 6 个名字."""
        assert _perm_name((0, 1, 2)) == "RGB"
        assert _perm_name((0, 2, 1)) == "RBG"
        assert _perm_name((1, 0, 2)) == "GRB"
        assert _perm_name((1, 2, 0)) == "GBR"
        assert _perm_name((2, 0, 1)) == "BRG"
        assert _perm_name((2, 1, 0)) == "BGR"


# ============================================================
# 集成测试: LSBDetectAction.run
# ============================================================

class TestLSBDetectAction:
    """LSBDetectAction.run 端到端测试 (per spec §6 ②')."""

    def test_action_text_match(self, synthetic_text_png):
        """合成图含 'Hi' 文本 → 12 组合某组合应命中 lsb_text SP."""
        action = LSBDetectAction()
        result = action.run({"file_path": str(synthetic_text_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        # 12 组合里至少一个应命中 (具体哪组合取决于合成图的 bit 布局)
        text_sps = [sp for sp in sps if sp["category"] == "lsb_text"]
        assert len(text_sps) >= 1, f"expected ≥ 1 lsb_text SP, got {len(text_sps)}"
        # 验证 severity=5
        for sp in text_sps:
            assert sp["severity"] == 5
            # 验证 SP 格式 per Owner 例子
            assert "lsb_detect 发现 lsb" in sp["matched_pattern"]
            assert "存在可疑内容:" in sp["matched_pattern"]

    def test_action_zip_match(self, synthetic_zip_png):
        """合成图含 ZIP magic → 12 组合某组合应命中 lsb_file_header SP."""
        action = LSBDetectAction()
        result = action.run({"file_path": str(synthetic_zip_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        file_sps = [sp for sp in sps if sp["category"] == "lsb_file_header"]
        assert len(file_sps) >= 1, f"expected ≥ 1 lsb_file_header SP, got {len(file_sps)}"
        for sp in file_sps:
            assert sp["severity"] == 5
            assert "存在可疑 zip 文件" in sp["matched_pattern"]

    def test_action_channel_anomaly_high_entropy(self, synthetic_high_entropy_png):
        """合成 G 通道高 entropy → lsb_channel_anomaly SP (sev=4)."""
        action = LSBDetectAction()
        result = action.run({"file_path": str(synthetic_high_entropy_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        anomaly_sps = [sp for sp in sps if sp["category"] == "lsb_channel_anomaly"]
        # 高 entropy 图至少 G 通道应触发 (R/B 可能也触发)
        assert len(anomaly_sps) >= 1, f"expected ≥ 1 lsb_channel_anomaly SP, got {len(anomaly_sps)}"
        for sp in anomaly_sps:
            assert sp["severity"] == 4  # info, 概率
            assert "存在可疑隐藏信息" in sp["matched_pattern"]
            assert "entropy=" in sp["matched_pattern"]
            assert "unique=" in sp["matched_pattern"]

    def test_action_no_match_uniform(self, synthetic_uniform_png):
        """合成 uniform 图 (R=0/G=255/B=128) → 各通道 entropy 低, 不触发 channel_anomaly."""
        action = LSBDetectAction()
        result = action.run({"file_path": str(synthetic_uniform_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        # uniform 图所有通道 entropy = 0, 不应触发 channel_anomaly
        anomaly_sps = [sp for sp in sps if sp["category"] == "lsb_channel_anomaly"]
        assert len(anomaly_sps) == 0, f"uniform image shouldn't trigger anomaly, got {len(anomaly_sps)}"

    def test_action_missing_file(self, tmp_path):
        """文件不存在 → ActionResult success=False."""
        action = LSBDetectAction()
        result = action.run({"file_path": str(tmp_path / "nonexistent.png")})
        assert not result.success
        assert "file not found" in result.message

    def test_action_no_file_path(self):
        """context 缺 file_path → ActionResult success=False."""
        action = LSBDetectAction()
        result = action.run({})
        assert not result.success
        assert "missing 'file_path'" in result.message

    def test_action_disable_channel_anomaly(self, synthetic_high_entropy_png):
        """enable_channel_anomaly=False → 不跑需求 2, 只跑需求 1."""
        action = LSBDetectAction(enable_channel_anomaly=False)
        result = action.run({"file_path": str(synthetic_high_entropy_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        anomaly_sps = [sp for sp in sps if sp["category"] == "lsb_channel_anomaly"]
        assert len(anomaly_sps) == 0, "channel_anomaly disabled should return 0 anomaly SPs"

    def test_action_custom_thresholds(self, synthetic_high_entropy_png):
        """自定义 entropy_threshold=10 → 任何图都不触发 anomaly."""
        action = LSBDetectAction(entropy_threshold=10.0)
        result = action.run({"file_path": str(synthetic_high_entropy_png)})
        assert result.success
        sps = result.data["suspicious_points"]
        anomaly_sps = [sp for sp in sps if sp["category"] == "lsb_channel_anomaly"]
        assert len(anomaly_sps) == 0, "entropy_threshold=10.0 should never trigger"

    def test_action_no_files_written(self, synthetic_text_png, tmp_path):
        """readonly 铁律: action 跑完不在 input 同目录写任何文件 (除了 /tmp file 命令临时)."""
        import os
        action = LSBDetectAction()
        result = action.run({"file_path": str(synthetic_text_png)})
        # 检查 input 同目录没多出 .bin / .txt / .zip / 等 lsb_detect 相关文件
        parent_dir = synthetic_text_png.parent
        for f in parent_dir.iterdir():
            assert f.name == synthetic_text_png.name, f"unexpected file in input dir: {f.name}"
        # 检查 /tmp 没有 lsb_detect 残留 (file 命令临时文件应删)
        import glob
        tmp_files = glob.glob("/tmp/lsb_detect_*")
        assert len(tmp_files) == 0, f"unexpected tmp files: {tmp_files}"
