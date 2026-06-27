"""测试 tools/shared/exiftool.py"""
from __future__ import annotations

import shutil

import pytest

from automisc.core.registry import get_tool
from automisc.tools.shared.exiftool import ExiftoolAdapter


@pytest.fixture(autouse=True)
def require_exiftool():
    if shutil.which("exiftool") is None:
        pytest.skip("exiftool not in PATH")


def test_exiftool_adapter_is_registered():
    a = get_tool("exiftool")
    assert isinstance(a, ExiftoolAdapter)


def test_exiftool_runs_on_png(tmp_png_file):
    a = ExiftoolAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    # PNG 应有 File Type 等基础 metadata
    assert "File Type" in result.stdout


def test_exiftool_runs_on_text(tmp_text_file):
    a = ExiftoolAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success


def test_exiftool_high_value_tags_create_suspicious_points(tmp_path):
    """构造一个带 Author metadata 的 PNG，验证 exiftool 提取到高价值 tag。"""
    # 用 PIL 生成合法 PNG
    from PIL import Image
    src = tmp_path / "src.png"
    Image.new("RGB", (8, 8), "red").save(src, "PNG")

    # exiftool 写入 Author
    import subprocess
    proc = subprocess.run(
        ["exiftool", "-overwrite_original", "-Author=flag{test_metadata_flag}", str(src)],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # exiftool 可能在某些 macOS 版本对 PNG 的 EXIF 写入有限制；fallback 用 XMP
        subprocess.run(
            ["exiftool", "-overwrite_original",
             "-XMP:Author=flag{test_metadata_flag}",
             str(src)],
            check=False, capture_output=True, text=True,
        )

    a = ExiftoolAdapter()
    result = a.run(str(src))
    assert result.is_success, f"stderr={result.stderr}"
    # Author metadata 应被标记为可疑
    md_sp = [p for p in result.suspicious_points if p.category == "metadata"]
    assert any("Author" in p.matched_pattern for p in md_sp), (
        f"missing Author metadata, got: {[(p.category, p.matched_pattern) for p in result.suspicious_points]}"
    )
    # 同时 flag 正则也应该命中（Author 值含 flag{}）
    flag_sp = [p for p in result.suspicious_points if p.category == "flag"]
    assert any("flag{test_metadata_flag}" in p.matched_pattern for p in flag_sp)


def test_exiftool_handles_missing_file(tmp_path):
    a = ExiftoolAdapter()
    result = a.run(str(tmp_path / "does_not_exist_xyz"))
    assert not result.is_success


def test_exiftool_chinese_exif_decodes_correctly(tmp_path):
    """per v0.5-windows-tool-compat PR1: adapter 传 -charset utf8, 中文 EXIF 不乱码.

    触发 bug: Win 上 exiftool 不传 -charset 时按 GBK code page 解码 EXIF Unicode
    字段 (XP*/XMP/Description/Title), 中文 EXIF 全乱码 (e.g. "图穷flag见" →
    "å›¾ç©·flagè§"). 修复: adapter cmd 强制 -charset utf8.

    验证: 写入带中文 Title 的 PNG, exiftool 读回应保留中文.
    """
    from PIL import Image
    src = tmp_path / "chinese.png"
    Image.new("RGB", (8, 8), "red").save(src, "PNG")

    # exiftool 写中文 Title (UTF-8 EXIF Unicode 字段)
    chinese_title = "图穷flag见"  # per v0.5-train-013-meihuai-jpg.jpg
    proc = subprocess.run(
        ["exiftool", "-overwrite_original",
         f"-Title={chinese_title}",
         str(src)],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"exiftool 不能写入 PNG EXIF (Win 上可能不支持): {proc.stderr}")

    a = ExiftoolAdapter()
    result = a.run(str(src))
    assert result.is_success, f"stderr={result.stderr}"
    # Title 字段必须保留中文, 不能是 GBK 错解码的乱码
    assert chinese_title in result.stdout, (
        f"中文 EXIF 乱码! 期望 '{chinese_title}' 在 stdout, 实际 stdout:\n{result.stdout}"
    )