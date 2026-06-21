"""LSBExtractAction 写文件格式单测 (v0.5-lsb-extract-output-bytes)

修 lsb_extract.py 写文件 (per Owner 2026-06-21 22:55 实战反馈):
- 旧: suffix=".txt" 写死 + write_text (UTF-8 decode) → 二进制 (e.g. PNG) 乱码
- 新: magic 判定后缀 (89 50 4E 47 = .png) + write_bytes (per Owner "用 python wb")

覆盖:
- _decide_suffix 纯函数: PNG / ZIP / PYC / ELF magic 命中 + fallback .bin
- _decide_suffix fallback 接受 hint_ext 兜底
- LSBExtractAction.run 端到端 (mock zsteg subprocess 跑 zsteg) verify 文件输出格式
- write_bytes 后用 `file` 命令识别为实际类型 (不是 "ASCII text" / "data")
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from automisc.core.actions.lsb_extract import (
    LSBExtractAction,
    _decide_suffix,
    _write_tmp_extracted,
)


# ============================================================
# 单元测试: _decide_suffix 纯函数
# ============================================================

class TestDecideSuffix:
    """_decide_suffix: 根据 magic 决定后缀 (per Owner 89 50 4E 47 是 PNG)."""

    def test_decide_suffix_png(self):
        """PNG magic (89 50 4E 47 0D 0A 1A 0A) → .png."""
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"rest" * 100
        assert _decide_suffix(png_bytes) == ".png"

    def test_decide_suffix_zip(self):
        """ZIP magic (PK\\x03\\x04) → .zip (含 docx/jar/apk 等)."""
        zip_bytes = b"PK\x03\x04" + b"rest" * 100
        assert _decide_suffix(zip_bytes) == ".zip"

    def test_decide_suffix_zip_empty(self):
        """ZIP empty (PK\\x05\\x06) → .zip."""
        zip_bytes = b"PK\x05\x06" + b"rest" * 100
        assert _decide_suffix(zip_bytes) == ".zip"

    def test_decide_suffix_rar(self):
        """RAR magic (Rar!\\x1a\\x07) → .rar."""
        rar_bytes = b"Rar!\x1a\x07" + b"rest" * 100
        assert _decide_suffix(rar_bytes) == ".rar"

    def test_decide_suffix_pyc_27(self):
        """Py 2.7 pyc magic (03 f3 0d 0a) → .pyc."""
        pyc_bytes = b"\x03\xf3\r\n" + b"rest" * 100
        assert _decide_suffix(pyc_bytes) == ".pyc"

    def test_decide_suffix_pyc_38(self):
        """Py 3.8 pyc magic (55 0d 0d 0a) → .pyc."""
        pyc_bytes = b"\x55\x0d\r\n" + b"rest" * 100
        assert _decide_suffix(pyc_bytes) == ".pyc"

    def test_decide_suffix_elf(self):
        """ELF magic (7F 45 4C 46) → .elf."""
        elf_bytes = b"\x7fELF\x02\x01\x01" + b"rest" * 100
        assert _decide_suffix(elf_bytes) == ".elf"

    def test_decide_suffix_png_only(self):
        """PNG magic 4 字节不够, 8 字节才命中 → .png.
        (PNG magic 是 \\x89PNG\\r\\n\\x1a\\n 8 字节, 4 字节前缀不匹配, fallback .bin)"""
        # 4 字节不够 — fallback .bin
        assert _decide_suffix(b"\x89PNG") == ".bin"
        # 8 字节完整 magic — 命中 .png
        assert _decide_suffix(b"\x89PNG\r\n\x1a\n") == ".png"

    def test_decide_suffix_fallback_bin(self):
        """没命中 magic → .bin (fallback 默认)."""
        assert _decide_suffix(b"random data here without any magic") == ".bin"

    def test_decide_suffix_fallback_with_hint(self):
        """没命中 magic + default='.txt' → .txt (default 兜底)."""
        assert _decide_suffix(b"random data here", default=".txt") == ".txt"

    def test_decide_suffix_empty(self):
        """空字节流 → .bin (fallback)."""
        assert _decide_suffix(b"") == ".bin"


# ============================================================
# 单元测试: _write_tmp_extracted (file 分支)
# ============================================================

class TestWriteTmpExtracted:
    """file 分支: _write_tmp_extracted 写文件 + magic 判定后缀 + write_bytes."""

    def test_write_png_binary(self, tmp_path):
        """合成 PNG 字节流 → 写 <stem>__lsb.png + write_bytes.

        注: 完整 PNG 结构需正确 CRC + IDAT 数据, 复杂. MVP 测试只验证:
        - 文件名后缀 .png (magic 覆盖 hint_ext)
        - 写真二进制 (无 UTF-8 decode 损失)
        - 写真字节流前 8 字节是 PNG magic (file 命令识别取决于完整 PNG 结构)
        """
        test_png = tmp_path / "test.png"
        test_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        # 完整 PNG magic + IDAT chunk (CRC 不一定正确, 但足够验证写文件逻辑)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"           # PNG signature
            + b"\x00" * 4 + b"IHDR"        # IHDR chunk
            + b"\x00" * 13                 # IHDR data
            + b"\x00" * 4                  # IHDR CRC
            + b"\x00" * 4 + b"IDAT"        # IDAT chunk
            + b"\x00" * 100                # IDAT data
            + b"\x00" * 4                  # IDAT CRC
            + b"\x00" * 4 + b"IEND"        # IEND chunk
            + b"\xae\x42\x60\x82"          # IEND CRC (best-effort)
        )

        result_path = _write_tmp_extracted(png_bytes, str(test_png), hint_ext=".bin")
        # 验证: 文件名用 .png 后缀 (magic 覆盖 hint_ext)
        assert result_path.endswith("__lsb.png"), f"expected .png suffix, got {result_path}"
        # 验证: 写真二进制
        written = open(result_path, "rb").read()
        assert written == png_bytes, "written bytes should match raw (no UTF-8 decode loss)"
        # 验证: 写真字节流前 8 字节是 PNG magic (file 命令识别取决于完整 PNG 结构, 不强求)
        assert written[:8] == b"\x89PNG\r\n\x1a\n", "written bytes should start with PNG magic"

    def test_write_zip_binary(self, tmp_path):
        """ZIP 字节流 → 写 .zip + file 命令识别."""
        test_png = tmp_path / "test.png"
        test_png.write_bytes(b"\x89PNG")
        zip_bytes = b"PK\x03\x04" + b"\x00" * 100

        result_path = _write_tmp_extracted(zip_bytes, str(test_png))
        assert result_path.endswith("__lsb.zip")
        file_out = subprocess.run(["file", "-b", result_path], capture_output=True, text=True, timeout=5)
        assert "Zip" in file_out.stdout or "zip" in file_out.stdout.lower()

    def test_write_random_fallback_bin(self, tmp_path):
        """随机数据 → 写 .bin (fallback)."""
        test_png = tmp_path / "test.png"
        test_png.write_bytes(b"\x89PNG")
        random_bytes = b"random data here without magic header"

        result_path = _write_tmp_extracted(random_bytes, str(test_png))
        assert result_path.endswith("__lsb.bin")


# ============================================================
# 集成测试: LSBExtractAction.run 端到端 (mock zsteg subprocess)
# ============================================================

class TestLSBExtractActionOutput:
    """LSBExtractAction.run 端到端: mock zsteg subprocess 验证写文件格式."""

    def test_action_text_branch_writes_correct_ext(self, tmp_path):
        """text 通道命中 printable text → 写真二进制 (text 不是文件 magic, fallback .bin).
        验证: 写真真实文件 (不 mock output_path_for), 文件名后缀跟 magic 一致.
        """
        test_png = tmp_path / "test.png"
        test_png.write_bytes(b"\x89PNG" + b"\x00" * 100)

        # mock zsteg 输出
        zsteg_output = (
            "b1,rgb,lsb,xy   .. text: \"Hello, World!\"\n"
            "b1,r,lsb,xy     .. file: PNG archive\n"
        )
        # mock zsteg extract bytes (zsteg -e 抽 raw bytes, 这里 text 实际是 text 不是二进制)
        extracted_bytes = b"Hello, World! " * 100  # printable text, 没 magic

        action = LSBExtractAction()
        with patch("automisc.core.actions.lsb_extract._run_zsteg_detect", return_value=zsteg_output), \
             patch("automisc.core.actions.lsb_extract._run_zsteg_extract", return_value=extracted_bytes):
            result = action.run({"file_path": str(test_png)})

        assert result.success
        # 写真文件: 验证文件名 + 内容
        from automisc.core.utils.output_path import output_path_for
        expected_path = output_path_for(str(test_png), suffix=".bin", purpose="lsb")
        # .bin suffix 因为 text bytes 没命中 magic (fallback)
        assert expected_path.exists(), f"file not written: {expected_path}"
        assert expected_path.suffix == ".bin", f"expected .bin fallback, got: {expected_path.suffix}"
        # 写真二进制, 没 UTF-8 decode 损失
        written = expected_path.read_bytes()
        assert written == extracted_bytes, "written bytes should match raw (no UTF-8 decode loss)"

    def test_action_text_branch_writes_png_for_png_bytes(self, tmp_path):
        """text 通道抽出的 raw bytes 实际是 PNG (zsteg 误判) → 写真 .png 后缀.
        验证: 文件名 .png (PNG magic 命中, 覆盖 hint), 写真字节流前 8 字节是 PNG magic.
        """
        test_png = tmp_path / "test.png"
        test_png.write_bytes(b"\x89PNG" + b"\x00" * 100)

        zsteg_output = (
            "b1,rgb,lsb,xy   .. text: \"\\x89PNG...\"\n"
        )
        # 实际 raw bytes 是 PNG (zsteg 误判为 text, 但 raw 是 PNG magic)
        extracted_bytes = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00" * 4 + b"IHDR" + b"\x00" * 13 + b"\x00" * 4
            + b"\x00" * 4 + b"IDAT" + b"\x00" * 100 + b"\x00" * 4
            + b"\x00" * 4 + b"IEND" + b"\xae\x42\x60\x82"
        )

        action = LSBExtractAction()
        with patch("automisc.core.actions.lsb_extract._run_zsteg_detect", return_value=zsteg_output), \
             patch("automisc.core.actions.lsb_extract._run_zsteg_extract", return_value=extracted_bytes):
            result = action.run({"file_path": str(test_png)})

        assert result.success
        # 写真文件: 验证文件名 + 内容
        from automisc.core.utils.output_path import output_path_for
        expected_path = output_path_for(str(test_png), suffix=".png", purpose="lsb")
        assert expected_path.exists(), f"file not written: {expected_path}"
        assert expected_path.suffix == ".png", f"expected .png (PNG magic), got: {expected_path.suffix}"
        # 写真二进制
        written = expected_path.read_bytes()
        assert written == extracted_bytes
        # 验证字节流前 8 字节是 PNG magic
        assert written[:8] == b"\x89PNG\r\n\x1a\n", "written bytes should start with PNG magic"
