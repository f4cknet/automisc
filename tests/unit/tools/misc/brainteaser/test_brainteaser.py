"""测试 tools/misc/brainteaser/"""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from automisc.core.registry import get_tool
from automisc.tools.misc.brainteaser.zbar import ZbarAdapter


FLAG_QR = "tests/fixtures/sample_qr_flag.png"
URL_QR = "tests/fixtures/sample_qr_url.png"


def test_zbar_adapter_is_registered():
    a = get_tool("zbar")
    assert isinstance(a, ZbarAdapter)


def test_zbar_extracts_flag_from_qr(flag_qr):
    a = ZbarAdapter()
    result = a.run(flag_qr)
    assert result.is_success
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr8_smoke_qr_xyz}" in sp.matched_pattern for sp in flag_sp)
    assert all(sp.severity == 5 for sp in flag_sp)


def test_zbar_extracts_url_from_qr(url_qr):
    a = ZbarAdapter()
    result = a.run(url_qr)
    url_sp = [sp for sp in result.suspicious_points if sp.category == "barcode_url"]
    assert len(url_sp) >= 1
    assert all(sp.severity >= 2 for sp in url_sp)


def test_zbar_handles_non_image(tmp_path):
    """非图片文件 → 不 panic。"""
    a = ZbarAdapter()
    bad = tmp_path / "not_image.txt"
    bad.write_bytes(b"not an image")
    result = a.run(str(bad))
    # exit 1 或 0 with empty stdout（zbar 可能宽容）—— 都不 panic
    assert isinstance(result.suspicious_points, list)


def test_zbar_handles_missing_file(tmp_path):
    a = ZbarAdapter()
    result = a.run(str(tmp_path / "ghost.png"))
    # 1 (no barcode found) 或 2 (file not readable)
    assert result.exit_code != 0


# === v0.5-zbar-windows-install 新增测试 (pyzbar 后端) ===

def test_zbar_check_available_true_when_pyzbar_installed():
    """pyzbar 装好 → check_available() 返回 True."""
    a = ZbarAdapter()
    assert a.check_available() is True


def test_zbar_check_available_false_when_pyzbar_missing(monkeypatch):
    """pyzbar import 失败 → check_available() 返回 False (GUI/auto-run 跳过)."""
    # mock import pyzbar.pyzbar 抛 ImportError
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pyzbar.pyzbar" or name.startswith("pyzbar"):
            raise ImportError("simulated: pyzbar not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    a = ZbarAdapter()
    assert a.check_available() is False


def test_zbar_stdout_format_matches_zbarimg_raw(flag_qr):
    """stdout 格式 1:1 兼容 zbarimg --raw (一行一条解码文本, 无 prefix).

    跟原 zbar adapter 行为兼容, GUI 渲染/journal/SP 解析都依赖这个格式.
    """
    a = ZbarAdapter()
    result = a.run(flag_qr)
    # 一行一条 (单 QR 解出 1 行)
    assert result.stdout == "flag{pr8_smoke_qr_xyz}"
    assert "\n" not in result.stdout  # 不是 multi-line


def test_zbar_returns_127_when_pyzbar_import_fails(monkeypatch, flag_qr):
    """pyzbar 缺失 → run() 返回 exit_code=127 (跟 subprocess FileNotFoundError 行为一致)."""
    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pyzbar.pyzbar" or name.startswith("pyzbar"):
            raise ImportError("simulated: pyzbar not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    a = ZbarAdapter()
    result = a.run(flag_qr)
    assert result.exit_code == 127
    assert "pyzbar" in result.stderr.lower()


def test_zbar_handles_empty_qr_decode(tmp_path):
    """图片里没 QR → 0 SP (no barcode_meta, no false positive)."""
    # 8x8 全白 PNG, 不会触发任何 QR 解码
    from PIL import Image
    img = Image.new("RGB", (8, 8), "white")
    p = tmp_path / "empty.png"
    img.save(p, "PNG")

    a = ZbarAdapter()
    result = a.run(str(p))
    assert result.is_success
    # 没有 QR → barcode_meta 不会被添加
    meta_sp = [sp for sp in result.suspicious_points if sp.category == "barcode_meta"]
    assert len(meta_sp) == 0
    # stdout 是空
    assert result.stdout == ""


def test_zbar_decode_failure_returns_exit_1(tmp_path):
    """PIL.UnidentifiedImageError → exit_code=1 + stderr 含 UnidentifiedImageError."""
    bad = tmp_path / "garbage.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\nnot a real png")
    a = ZbarAdapter()
    result = a.run(str(bad))
    assert result.exit_code == 1
    assert "decode failed" in result.stderr or "UnidentifiedImageError" in result.stderr


# === fixtures ===

@pytest.fixture
def flag_qr():
    import os
    if not os.path.exists(FLAG_QR):
        pytest.skip(f"fixture not found: {FLAG_QR}")
    return FLAG_QR


@pytest.fixture
def url_qr():
    import os
    if not os.path.exists(URL_QR):
        pytest.skip(f"fixture not found: {URL_QR}")
    return URL_QR
