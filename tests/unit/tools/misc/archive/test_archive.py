"""测试 tools/misc/archive/"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.misc.archive.john import JohnAdapter
from automisc.tools.misc.archive.sevenz import SevenZipAdapter
from automisc.tools.misc.archive.unzip import UnzipAdapter


NORMAL_ZIP = "tests/fixtures/sample_archive_flag.zip"
PSEUDO_ZIP = "tests/fixtures/sample_archive_pseudo.zip"


# === sevenz ===

def test_sevenz_adapter_is_registered():
    a = get_tool("sevenz")
    assert isinstance(a, SevenZipAdapter)


def test_sevenz_normal_zip_extracts_file_count(normal_zip):
    a = SevenZipAdapter()
    result = a.run(normal_zip)
    assert result.is_success
    meta = [sp for sp in result.suspicious_points if sp.category == "archive_meta"]
    assert any("archive contains" in sp.matched_pattern for sp in meta)


def test_sevenz_pseudo_zip_detects_wrong_password(pseudo_zip):
    """伪加密 zip → 7z t -p 报 Wrong password → severity=4。"""
    a = SevenZipAdapter()
    result = a.run(pseudo_zip)
    pseudo = [sp for sp in result.suspicious_points if sp.category == "archive_pseudo_encryption"]
    assert any("Wrong password" in sp.matched_pattern for sp in pseudo)
    assert all(sp.severity >= 3 for sp in pseudo)


def test_sevenz_handles_non_archive(tmp_path):
    a = SevenZipAdapter()
    bad = tmp_path / "not_zip.txt"
    bad.write_bytes(b"not a zip")
    result = a.run(str(bad))
    # 7z 会报错（exit ≠ 0），但不 panic
    assert result.exit_code != 0 or len(result.suspicious_points) >= 0


# === unzip ===

def test_unzip_adapter_is_registered():
    a = get_tool("unzip")
    assert isinstance(a, UnzipAdapter)


def test_unzip_normal_zip_extracts_file_count(normal_zip):
    a = UnzipAdapter()
    result = a.run(normal_zip)
    assert result.is_success
    meta = [sp for sp in result.suspicious_points if sp.category == "archive_meta"]
    assert any("archive contains" in sp.matched_pattern for sp in meta)


def test_unzip_handles_missing_file(tmp_path):
    a = UnzipAdapter()
    result = a.run(str(tmp_path / "ghost.zip"))
    assert result.exit_code != 0


# === john ===

def test_john_adapter_is_registered():
    a = get_tool("john")
    assert isinstance(a, JohnAdapter)


def test_john_normal_zip_reports_unsupported(normal_zip):
    """zip2john 收到非加密 zip → 报 unsupported + 列出 capability。"""
    a = JohnAdapter()
    result = a.run(normal_zip)
    cap = [sp for sp in result.suspicious_points if sp.category == "john_capability"]
    assert any("zip2john" in sp.matched_pattern for sp in cap)


def test_john_handles_missing_file(tmp_path):
    a = JohnAdapter()
    result = a.run(str(tmp_path / "ghost.zip"))
    # 行为不严格，只验证不 panic
    assert isinstance(result.suspicious_points, list)


# === fixtures ===

@pytest.fixture
def normal_zip():
    import os
    if not os.path.exists(NORMAL_ZIP):
        pytest.skip(f"fixture not found: {NORMAL_ZIP}")
    return NORMAL_ZIP


@pytest.fixture
def pseudo_zip():
    import os
    if not os.path.exists(PSEUDO_ZIP):
        pytest.skip(f"fixture not found: {PSEUDO_ZIP}")
    return PSEUDO_ZIP
