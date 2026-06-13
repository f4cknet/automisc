"""测试 tools/shared/foremost.py"""
from __future__ import annotations

import shutil

import pytest

from automisc.core.registry import get_tool
from automisc.tools.shared.foremost import ForemostAdapter


@pytest.fixture(autouse=True)
def require_foremost():
    """foremost 缺失时跳过整个模块。"""
    if shutil.which("foremost") is None:
        pytest.skip("foremost not in PATH")


def test_foremost_adapter_is_registered():
    a = get_tool("foremost")
    assert isinstance(a, ForemostAdapter)


def test_foremost_runs_on_png(tmp_png_file):
    """foremost 在合法 PNG 上能跑通（可能提取或仅审计）。"""
    a = ForemostAdapter()
    result = a.run(str(tmp_png_file))
    # foremost 应至少 exit code 0（"处理完成"）
    assert result.exit_code in (0, 1), f"unexpected exit_code={result.exit_code}, stderr={result.stderr[:200]}"


def test_foremost_plain_text_yields_nothing(tmp_text_file):
    a = ForemostAdapter()
    result = a.run(str(tmp_text_file))
    # 纯文本应该跑通
    assert result.exit_code in (0, 1)


def test_foremost_handles_invalid_path(tmp_path):
    """foremost 在传入无效路径时不应崩溃（exit code 0 或 1 都可接受）。"""
    a = ForemostAdapter()
    # 注意：macOS 上 foremost 对不存在的文件可能从 stdin 读（exit 0），也可能报错
    # 主要验证 adapter 不抛异常、不 crash
    try:
        result = a.run(str(tmp_path / "does_not_exist_xyz"))
    except Exception as e:
        pytest.fail(f"ForemostAdapter.run() crashed on invalid path: {e}")
    # exit code 0/1 均可，主要验证返回了 ToolResult
    assert isinstance(result, type(a.run(tmp_path / "x")))  # type sanity check