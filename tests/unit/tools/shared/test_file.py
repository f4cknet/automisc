"""测试 tools/shared/file.py"""
from __future__ import annotations

from automisc.core.registry import get_tool
from automisc.tools.shared.file import FileAdapter


def test_file_adapter_is_registered():
    a = get_tool("file")
    assert isinstance(a, FileAdapter)
    assert a.name == "file"
    assert a.category == "shared"


def test_file_adapter_runs_on_text(tmp_text_file):
    a = FileAdapter()
    result = a.run(str(tmp_text_file))
    assert result.is_success
    assert "ASCII" in result.stdout or "text" in result.stdout.lower()
    # file --brief 应该返回 1 个 file_type 可疑点
    sp = [p for p in result.suspicious_points if p.category == "file_type"]
    assert len(sp) == 1


def test_file_adapter_runs_on_png(tmp_png_file):
    a = FileAdapter()
    result = a.run(str(tmp_png_file))
    assert result.is_success
    assert "PNG" in result.stdout


def test_file_adapter_handles_missing_file(tmp_path):
    a = FileAdapter()
    result = a.run(str(tmp_path / "does_not_exist_xyz"))
    # macOS `file` 命令在文件不存在时仍 exit code 0，但 stdout 含 "cannot open"
    assert "cannot open" in result.stdout.lower() or result.exit_code != 0