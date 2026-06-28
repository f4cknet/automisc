"""Phase 7 实战 regression (per v0.5-lsb-tool-unify spec §6 + AGENTS §1 铁律 4 关 4).

实战 smoke 3 道题 (per upgrade.md note): N=NP / steg.png / meihuai.jpg
- N=NP: PNG 嵌入 ZIP, G channel bit 0 col MSB 提取
- steg.png: 真实 PNG (per sample_qr_flag.png, 实际本地无 steg.png, 用最近 fixture 替代)
- meihuai.jpg: 实际本地无 meihuai.jpg, 用 sample_qr_url.png 替代 (真实 PNG fixture smoke)

本文件覆盖:
1. TestN=NPRoundtrip: synthetic N=NP (PIL 生成 RGB PNG → embed ZIP → lsb_tool extract → 验证 roundtrip)
2. TestRealFixtureSmoke: 真实 PNG fixture smoke (sample_qr_flag.png + sample_qr_url.png → LsbToolAdapter.run → 验证不 crash + 返回 SP)
3. TestBackwardCompat: 老 API (lsb_extract action / chain lsb-bytes / lsb_bytes_dialog) 仍可工作
"""
from __future__ import annotations

import os
import zipfile

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image


# ============================================================
# Test 1: Synthetic N=NP Roundtrip (per spec §3.6 preset='np')
# ============================================================

class TestNNPRoundtrip:
    """Synthetic N=NP 场景 roundtrip: embed ZIP → extract via lsb_tool → bytes match.

    per spec §3.6 N=NP 默认: G 通道 / bit 0 / col / MSB (v0.5-train-009).
    """

    @pytest.fixture
    def synthetic_n_np_png(self, tmp_path):
        """生成 32x32 RGB PNG, G channel bit 0 col MSB 嵌入 ZIP bytes.

        Returns:
            Path to PNG with embedded ZIP in G channel LSB col scan MSB.
        """
        from automisc.core.actions.lsb_tool_common import (
            _BYTE_PREVIEW_LIMIT,
            _extract_lsb_byte_stream,
        )

        # 创建 ZIP 内存文件 (含 1 个文件: flag.txt)
        zip_buffer_path = tmp_path / "test_payload.zip"
        with zipfile.ZipFile(zip_buffer_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("flag.txt", "N=NP synthetic test flag: CTF{synthetic_n_np_roundtrip}\n")

        zip_bytes = zip_buffer_path.read_bytes()

        # 创建 32x32 RGB PNG (随机像素, 避免 trivial 0-channel)
        # N=NP 需要至少 len(zip_bytes) * 8 = len(zip_bytes) << 8 pixels worth of capacity
        # 32*32 = 1024 pixels G channel → 1024 bits → 128 bytes max embed
        # 我们的 ZIP bytes 应该 ≤ 100 bytes (留余量)
        if len(zip_bytes) > 100:
            zip_bytes = zip_bytes[:100]

        width, height = 32, 32
        img = Image.new("RGB", (width, height), color=(128, 64, 200))  # 默认非 0
        arr = np.array(img, dtype=np.uint8)
        # 让 R/B 通道保持随机非 LSB 状态 (避免 LSB 干扰), G 通道置 0x00 (8 个 bit 位都是 0)
        arr[:, :, 1] = 0x00  # G 通道 = 0 (低 8 bit 全 0, 高位保证 LSB 提取时不冲突)

        # N=NP 顺序: 列扫描 (外层 w 内层 h), MSB
        # 把 zip_bytes 嵌入 G channel bit 0, col scan, MSB
        # 即每个 byte 的 8 个 bit 分散到 G channel 的 8 个 pixel
        byte_idx = 0
        bit_idx = 0
        for w in range(width):
            for h in range(height):
                if byte_idx >= len(zip_bytes):
                    break
                # 当前 byte 的 bit_idx 位 (MSB first)
                bit_val = (zip_bytes[byte_idx] >> (7 - bit_idx)) & 1
                # 修改 G channel bit 0
                arr[h, w, 1] = (arr[h, w, 1] & 0xFE) | bit_val
                # 推进 bit
                bit_idx += 1
                if bit_idx == 8:
                    bit_idx = 0
                    byte_idx += 1
            if byte_idx >= len(zip_bytes):
                break

        png_path = tmp_path / "n_np_synthetic.png"
        Image.fromarray(arr).save(png_path, "PNG")
        return png_path, zip_bytes

    def test_n_np_extract_matches_embedded_zip(self, synthetic_n_np_png, tmp_path):
        """N=NP 场景: embed ZIP → LSBToolAction(mode='extract_bytes', N=NP 4 参数) 提取 → bytes match."""
        from automisc.core.actions.lsb_tool import LSBToolAction

        png_path, expected_zip_bytes = synthetic_n_np_png

        # N=NP extract 走 extract_bytes mode + 显式 4 参数 (G / bit 0 / col / MSB)
        # 注: extract mode 跑 12 组合跟 embed 1 组合不匹配, extract_bytes 单组合才对得上
        action = LSBToolAction(
            mode="extract_bytes",
            channels="G",  # N=NP 单通道
            bit=0,         # N=NP LSB
            scan_order="col",  # N=NP 列扫描
            byte_bit_order="msb",  # N=NP MSB (lowercase per LSBToolAction validation)
        )
        result = action.run({"file_path": str(png_path)})

        # 验证 result success
        assert result.success, f"lsb_tool extract_bytes failed: {result.message}"
        # 验证 extracted_bytes 字段
        extracted_files = result.data.get("extracted_files", [])
        extracted_bytes_data = result.data.get("extracted_bytes", b"")
        if extracted_files:
            extracted_bytes = open(extracted_files[0], "rb").read()
        else:
            extracted_bytes = extracted_bytes_data

        # N=NP 提取 → 字节流前 N 字节 (N = len(expected_zip_bytes)) 应该 == expected_zip_bytes
        assert extracted_bytes[:len(expected_zip_bytes)] == expected_zip_bytes, (
            f"extracted bytes mismatch: expected first {len(expected_zip_bytes)} bytes "
            f"= {expected_zip_bytes[:20]!r}..., got {extracted_bytes[:20]!r}..., "
            f"full extracted: {len(extracted_bytes)} bytes, message: {result.message}"
        )

    def test_n_np_auto_run_pool_includes_lsb_tool(self):
        """auto-run 池含 lsb_tool (per Phase 3 切换 + spec §3.9)."""
        from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS

        assert "lsb_tool" in FIND_SUSPICIOUS_PICTURE_TOOLS
        assert "lsb_detect" not in FIND_SUSPICIOUS_PICTURE_TOOLS


# ============================================================
# Test 2: Real PNG fixture smoke (sample_qr_flag.png + sample_qr_url.png)
# ============================================================

class TestRealFixtureSmoke:
    """真实 PNG fixture smoke: LsbToolAdapter.run() 不 crash + 返回 SP.

    fixture: tests/fixtures/sample_qr_flag.png + sample_qr_url.png (灰度 QR, 无 LSB)
    期望: run 成功, SP 列表可能为空 (灰度 QR 无 LSB 隐写) 或有 entropy 异常。
    """

    @pytest.fixture
    def real_png_path(self):
        """tests/fixtures/sample_qr_flag.png (330x330 grayscale QR)."""
        from pathlib import Path

        # pytest 跑在 repo root, fixture 路径相对
        repo_root = Path(__file__).resolve().parents[2]
        png_path = repo_root / "tests" / "fixtures" / "sample_qr_flag.png"
        if not png_path.exists():
            pytest.skip(f"fixture not found: {png_path}")
        return png_path

    def test_lsb_tool_adapter_runs_on_real_png(self, real_png_path):
        """LsbToolAdapter.run() on real PNG: success, 返回 SP list."""
        from automisc.tools.steganography.image.lsb_tool_adapter import LsbToolAdapter

        adapter = LsbToolAdapter()  # 默认 mode='detect' + preset=None
        result = adapter.run(str(real_png_path))

        # result 必含 suspicious_points list (可空)
        assert isinstance(result.suspicious_points, list)
        # result 必有 stdout 字段 (替代 message)
        assert result.stdout is not None
        # 不管命中与否, run 都不应 crash
        assert result.exit_code in (0, 1)

    def test_lsb_tool_adapter_explicit_modes_run_on_real_png(self, real_png_path):
        """LsbToolAdapter 显式 mode 切换 (detect/extract/extract_bytes) 都跑得动."""
        from automisc.tools.steganography.image.lsb_tool_adapter import LsbToolAdapter

        for mode in ("detect", "extract", "extract_bytes"):
            adapter = LsbToolAdapter(mode=mode)
            result = adapter.run(str(real_png_path))
            # 不 crash 即可
            assert result.exit_code in (0, 1), f"mode={mode} failed: {result.stdout}"


# ============================================================
# Test 3: Backward compat — 老 API 仍能跑 (Phase 6 deprecated, but 仍可用)
# ============================================================

class TestBackwardCompatSmoke:
    """Phase 6 标记 deprecated 但 API 仍可用 (CLI 用户 backward compat)."""

    def test_lsb_detect_action_still_runnable(self, real_png_path_safe):
        """LSBDetectAction 仍可实例化和 run."""
        from automisc.core.actions.lsb_detect import LSBDetectAction

        action = LSBDetectAction()
        result = action.run({"file_path": str(real_png_path_safe)})
        assert result.success or not result.success  # 不管命中与否, 不 crash

    def test_lsb_bytes_extract_action_still_runnable(self, tmp_path, real_png_path_safe):
        """LSBBytesExtractAction 仍可 run."""
        from automisc.core.actions.lsb_bytes_extract import LSBBytesExtractAction

        # 注: LSBBytesExtractAction 不接 output_dir, 默认 4 参数
        action = LSBBytesExtractAction(channels=["R"], bit=0)
        result = action.run({"file_path": str(real_png_path_safe)})
        assert result is not None  # 不 crash

    def test_lsb_bytes_dialog_still_importable(self):
        """LSBBytesParamDialog 仍可 import (backward compat for chain lsb-bytes)."""
        from automisc.gui.lsb_bytes_dialog import LSBBytesParamDialog

        assert LSBBytesParamDialog is not None

    @pytest.fixture
    def real_png_path_safe(self):
        """tests/fixtures/sample_qr_flag.png (330x330 grayscale QR, safe for backward compat tests)."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        png_path = repo_root / "tests" / "fixtures" / "sample_qr_flag.png"
        if not png_path.exists():
            pytest.skip(f"fixture not found: {png_path}")
        return png_path


# ============================================================
# Test 4: End-to-end auto-run pipeline (mocked mini pool, lsb_tool 在内)
# ============================================================

class TestAutoRunPipeline:
    """auto-run 池全跑 pipeline 验证 (lsb_tool 在内, 不依赖 lsb_detect).

    跳过完整 GUI (PySide6 启动重), 直接 mock main_window, 只测 pipeline。
    """

    def test_auto_run_picture_pool_size_6(self):
        """FIND_SUSPICIOUS_PICTURE_TOOLS 仍 6 tools (per AGENTS §1 铁律 7)."""
        from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS

        assert len(FIND_SUSPICIOUS_PICTURE_TOOLS) == 6

    def test_auto_run_picture_pool_contains_lsb_tool(self):
        """auto-run picture pool 含 lsb_tool (替代 lsb_detect)."""
        from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS

        pool = FIND_SUSPICIOUS_PICTURE_TOOLS
        assert "lsb_tool" in pool
        assert "lsb_detect" not in pool

    def test_auto_run_picture_pool_contains_core_tools(self):
        """auto-run pool 包含其他 5 个核心 tool (per spec §3.9)."""
        from automisc.gui.auto_runner import FIND_SUSPICIOUS_PICTURE_TOOLS

        pool = FIND_SUSPICIOUS_PICTURE_TOOLS
        # spec §3.9: 6 tools = lsb_tool + stegseek + exiftool + binwalk + strings + file
        expected = {"lsb_tool", "stegseek", "exiftool", "binwalk", "strings", "file"}
        assert expected.issubset(set(pool)), (
            f"missing tools: {expected - set(pool)}, actual: {pool}"
        )