"""测试 tools/shared/xxd.py"""
from __future__ import annotations

from automisc.core.registry import get_tool
from automisc.tools.shared.xxd import XxdAdapter


def test_xxd_adapter_is_registered():
    a = get_tool("xxd")
    assert isinstance(a, XxdAdapter)


def test_xxd_detects_png_magic(tmp_png_file):
    a = XxdAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    # 1x1 PNG 应触发 file_header 可疑点
    sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("PNG" in p.matched_pattern for p in sp)


def test_xxd_detects_zip_magic(tmp_path):
    p = tmp_path / "fake.zip"
    p.write_bytes(b"PK\x03\x04rest of zip data")
    a = XxdAdapter()
    result = a.run(str(p))
    assert result.is_success
    sp = [p for p in result.suspicious_points if p.category == "file_header"]
    assert any("ZIP" in p.matched_pattern for p in sp)


def test_xxd_dumps_hex_output(tmp_text_file):
    a = XxdAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success
    # xxd 输出格式: "<offset>: <hex>  <ascii>"
    assert ":" in result.stdout
    assert "flag" in result.stdout  # ASCII 列含原文


def test_xxd_handles_missing_file(tmp_path):
    a = XxdAdapter()
    result = a.run(str(tmp_path / "does_not_exist_xyz"))
    assert not result.is_success


def test_xxd_flags_in_ascii_column(tmp_path):
    """xxd 的 ASCII 列含 flag 字符串，应被关键字扫描捕获。"""
    p = tmp_path / "binary_with_flag.bin"
    # flag 放在前 32 字节内（xxd 默认 -l 256，但 16 字节对齐）
    p.write_bytes(b"flag{hidden_in_binary_data_xyz}\x00\x00")
    a = XxdAdapter()
    result = a.run(str(p))
    assert result.is_success
    flag_sp = [p for p in result.suspicious_points if p.category == "flag"]
    # xxd 可能按 16 字节换行，flag 可能被截断——只验证前半段
    assert any("flag{hidden" in p.matched_pattern for p in flag_sp), (
        f"expected flag{...} in suspicious points, got: {[s.matched_pattern for s in flag_sp]}"
    )