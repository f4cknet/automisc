"""测试 tools/misc/brainteaser/"""
from __future__ import annotations

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
