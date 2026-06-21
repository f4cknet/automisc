"""magic_sniffer 单测 (v0.5-lsb-byte-stream-extract 能力 C)

不依赖真实 fixture, 自己合成字节流测试 35+ magic 嗅探。

覆盖:
- 滑动窗口扫 offset 0~32 (per spec §3.5)
- 35+ magic (PNG/ZIP/pyc/JPEG/PDF/ELF/WASM/Mach-O/Java/...)
- 命中后写文件 + 同目录 (per v0.5-output-samedir)
- 错误处理 (文件不存在 / 空数据)
"""
from __future__ import annotations

import pytest
from pathlib import Path

from automisc.core.decoders.magic_sniffer import (
    EXTENDED_MAGIC_SIGNATURES,
    SniffResult,
    MagicSnifferResult,
    sniff_magic,
    run_magic_sniffer,
    _sniffed_output_path,
)


# ---------- sniff_magic 测试 ----------
class TestSniffMagic:
    def test_png_at_offset_0(self):
        # PNG magic 8 bytes
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        assert any(h.description == "PNG image" and h.offset == 0 for h in hits)

    def test_zip_at_offset_0(self):
        data = b"PK\x03\x04" + b"\x00" * 16
        hits = sniff_magic(data, max_offset=32)
        assert any(h.description == "ZIP archive" and h.offset == 0 for h in hits)

    def test_magic_at_offset_n_not_zero(self):
        # N=NP 类题核心场景: magic 出现在 offset > 0
        data = b"\xff" * 8 + b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        hits = sniff_magic(data, max_offset=32)
        png_hits = [h for h in hits if h.description == "PNG image"]
        assert len(png_hits) >= 1
        # offset 8 应该有命中 (不是 0)
        assert any(h.offset == 8 for h in png_hits)

    def test_pyce3_at_offset_2(self):
        # 模拟 N=NP 题场景: e3 字节在 offset 2
        data = b"\x4e\x3f\xe3\x00\x00\x00" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "pyc" in h.description.lower()]
        assert len(pyc_hits) >= 1
        assert any(h.offset == 2 for h in pyc_hits)

    def test_jpeg_with_exif_marker(self):
        data = b"\xff\xd8\xff\xe1" + b"\x00" * 16
        hits = sniff_magic(data, max_offset=32)
        jpeg_hits = [h for h in hits if "JPEG" in h.description]
        assert any("EXIF" in h.description for h in jpeg_hits)

    def test_empty_data(self):
        assert sniff_magic(b"", max_offset=32) == []

    def test_no_hits(self):
        data = b"\xab" * 100  # 随机字节
        assert sniff_magic(data, max_offset=32) == []

    def test_short_data_no_overflow(self):
        # 数据短于 magic 长度 → 不抛, 不命中
        data = b"\x89PNG"
        hits = sniff_magic(data, max_offset=32)
        # 不到完整 8 字节 PNG magic, 不应该命中
        assert not any(h.description == "PNG image" for h in hits)

    def test_max_offset_clamp(self):
        # max_offset 超过数据长度 → 不会 IndexError
        data = b"\x89PNG\r\n\x1a\n"
        hits = sniff_magic(data, max_offset=100)  # 远超数据长度
        assert any(h.offset == 0 for h in hits)

    def test_severity_is_5(self):
        """per spec §3.5: 命中后 severity 统一 = 5."""
        data = b"\x89PNG\r\n\x1a\n"
        hits = sniff_magic(data, max_offset=32)
        for h in hits:
            assert h.severity == 5

    def test_all_hits_have_ext(self):
        """每个 hit 必须有 ext 字段 (用于写文件)."""
        data = b"\x89PNG\r\n\x1a\n" + b"PK\x03\x04" * 4
        hits = sniff_magic(data, max_offset=32)
        for h in hits:
            assert h.ext
            assert h.description


# ---------- EXTENDED_MAGIC_SIGNATURES 完整性测试 ----------
class TestMagicDict:
    def test_minimum_35_entries(self):
        """per spec §3.5: 35+ magic 字典."""
        assert len(EXTENDED_MAGIC_SIGNATURES) >= 35

    def test_all_have_3_fields(self):
        """(magic_bytes, description, ext) 三元组."""
        for entry in EXTENDED_MAGIC_SIGNATURES:
            assert len(entry) == 3
            magic, desc, ext = entry
            assert isinstance(magic, bytes)
            assert isinstance(desc, str)
            assert isinstance(ext, str)

    def test_no_duplicate_magic(self):
        """不应该有重复 magic bytes (避免顺序影响命中)."""
        seen = set()
        for magic, _, _ in EXTENDED_MAGIC_SIGNATURES:
            assert magic not in seen, f"duplicate magic: {magic.hex()}"
            seen.add(magic)


# ---------- _sniffed_output_path 测试 ----------
class TestSniffedOutputPath:
    def test_basic(self, tmp_path):
        bin_path = tmp_path / "x__lsb_g_b0_col_msb.bin"
        bin_path.touch()
        out = _sniffed_output_path(bin_path, "pyc")
        assert out.parent == tmp_path
        assert out.name == "x__lsb_g_b0_col_msb__sniffed.pyc"


# ---------- run_magic_sniffer 集成测试 ----------
class TestRunMagicSniffer:
    def test_png_byte_stream_at_offset_0(self, tmp_path):
        """PNG 字节流 (有前缀头) 在 offset 0 → 命中."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        bin_path = tmp_path / "test.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        assert result.error is None
        assert result.raw_size == len(data)
        assert result.has_hits
        assert any(h.description == "PNG image" for h in result.hits)

    def test_png_byte_stream_at_offset_n(self, tmp_path):
        """PNG 字节流在 offset 8 → 命中 (验证滑动窗口)."""
        data = b"\xff" * 8 + b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        bin_path = tmp_path / "test.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        png_hits = [h for h in result.hits if h.description == "PNG image"]
        assert any(h.offset == 8 for h in png_hits)

        # 验证写出了 sniffed 文件
        assert len(result.written_files) == 1
        out = Path(result.written_files[0])
        assert out.exists()
        assert out.suffix == ".png"
        assert out.name == "test__sniffed.png"
        # 写出的文件内容 == 原字节流 (sniffed = 原始数据, 不剪裁)
        assert out.read_bytes() == data

    def test_zip_in_random_prefix(self, tmp_path):
        """ZIP magic 在 offset 16 → 命中."""
        data = b"\xab\xcd" * 8 + b"PK\x03\x04" + b"\x00" * 32
        bin_path = tmp_path / "x.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        zip_hits = [h for h in result.hits if h.description == "ZIP archive"]
        assert any(h.offset == 16 for h in zip_hits)

    def test_no_magic_no_write(self, tmp_path):
        """无 magic → 不写文件."""
        data = b"\xab" * 100
        bin_path = tmp_path / "x.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        assert result.error is None
        assert not result.has_hits
        assert result.written_files == []

    def test_file_not_found(self, tmp_path):
        result = run_magic_sniffer(str(tmp_path / "nonexistent.bin"))
        assert result.error is not None
        assert "not found" in result.error

    def test_multiple_hits_one_ext_writes_once(self, tmp_path):
        """多个 hit 同一 ext → 只写一次 (取 offset 最小的)."""
        # 同一个 ZIP magic 在 offset 8 和 offset 24 都命中
        data = b"\xff" * 8 + b"PK\x03\x04" + b"\xff" * 8 + b"PK\x03\x04" + b"\xff" * 32
        bin_path = tmp_path / "x.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        zip_hits = [h for h in result.hits if h.description == "ZIP archive"]
        assert len(zip_hits) >= 2  # 多个命中
        # 但只写一次
        zip_writes = [w for w in result.written_files if w.endswith(".zip")]
        assert len(zip_writes) == 1

    def test_no_write_mode(self, tmp_path):
        """write_files=False → 不写文件 (per decoder kwargs)."""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        bin_path = tmp_path / "x.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32, write_files=False)
        assert result.has_hits
        assert result.written_files == []


# ---------- v0.5-pyc-magic-sniffer: Py2.x / Py3.x magic 字典扩展 (per Owner 06-21 11:40 Q1=Y) ----------
class TestPycMagicExtensions:
    """v0.5-pyc-magic-sniffer: Py2.x / Py3.x magic 字典扩展 (per Owner 06-21 11:40 Q1=Y).

    覆盖: Py2.4 / Py2.5 / Py2.6 / Py2.7 + Py3.0 / Py3.6 / Py3.10 / Py3.12 + 滑动窗口。
    """

    def test_py27_magic_at_offset_0(self):
        """Python 2.7 pyc magic 03 f3 0d 0a (62211) → 命中 (per N=NP 题核心命中)."""
        data = b"\x03\xf3\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 2.7" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py26_magic_at_offset_0(self):
        """Python 2.6 pyc magic 81 f2 0d 0a (62081) → 命中."""
        data = b"\x81\xf2\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 2.6" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py24_magic_at_offset_0(self):
        """Python 2.4 pyc magic 3b f2 0d 0a (62061) → 命中."""
        data = b"\x3b\xf2\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 2.4" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py30_magic_at_offset_0(self):
        """Python 3.0 pyc magic b8 0b 0d 0a (3000) → 命中."""
        data = b"\xb8\x0b\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 3.0" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py36_magic_at_offset_0(self):
        """Python 3.6 pyc magic 5c 0d 0d 0a (3420) → 命中."""
        data = b"\x5c\x0d\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 3.6" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py312_magic_at_offset_0(self):
        """Python 3.12 pyc magic cb 0d 0d 0a (3531) → 命中."""
        data = b"\xcb\x0d\x0d\x0a" + b"\x00" * 32
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 3.12" in h.description]
        assert any(h.offset == 0 for h in pyc_hits)

    def test_py27_magic_at_offset_n(self):
        """Py2.7 magic 在 offset 8 → 命中 (滑动窗口)."""
        data = b"\xff" * 8 + b"\x03\xf3\x0d\x0a" + b"\x00" * 16
        hits = sniff_magic(data, max_offset=32)
        pyc_hits = [h for h in hits if "Python 2.7" in h.description]
        assert any(h.offset == 8 for h in pyc_hits)

    def test_py27_magic_writes_pyc(self, tmp_path):
        """Py2.7 magic 命中 → 写 .pyc 文件 (per spec §6 ④)."""
        data = b"\x03\xf3\x0d\x0a" + b"\x00" * 100
        bin_path = tmp_path / "x.bin"
        bin_path.write_bytes(data)

        result = run_magic_sniffer(str(bin_path), max_offset=32)
        pyc_writes = [w for w in result.written_files if w.endswith(".pyc")]
        assert len(pyc_writes) == 1

    def test_all_python_magics_have_pyc_ext(self):
        """所有 Python pyc magic 都应该 ext='pyc'."""
        for magic, desc, ext in EXTENDED_MAGIC_SIGNATURES:
            if "pyc" in desc.lower() or "python" in desc.lower():
                assert ext == "pyc", f"{desc} should have ext='pyc'"
