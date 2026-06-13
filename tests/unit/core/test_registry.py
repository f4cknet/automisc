"""测试 core/registry.py。"""
from __future__ import annotations

import pytest

from automisc.core.registry import (
    _TOOL_REGISTRY,
    clear_registry,
    get_tool,
    get_tool_class,
    list_tools,
    register_tool,
)
from automisc.tools.base import ToolAdapter


class _DummyAdapter(ToolAdapter):
    name = "test_dummy"
    category = "test"

    def run(self, file_path: str):  # pragma: no cover
        from automisc.core.result import ToolResult
        return ToolResult(tool_name=self.name, exit_code=0, stdout="")


class _DummyAdapter2(ToolAdapter):
    name = "test_dummy2"
    category = "test"

    def run(self, file_path: str):  # pragma: no cover
        from automisc.core.result import ToolResult
        return ToolResult(tool_name=self.name, exit_code=0, stdout="")


def _cleanup_dummies():
    """清理 test_dummy / test_dummy2（不影响真实注册的 shared adapter）。"""
    for n in ("test_dummy", "test_dummy2"):
        _TOOL_REGISTRY.pop(n, None)


@pytest.fixture(autouse=True)
def _cleanup_dummies_fixture():
    """每个测试前后清理 stub（不 clear 真实 adapter）。"""
    _cleanup_dummies()
    yield
    _cleanup_dummies()


def test_register_tool_adds_to_registry():
    register_tool(_DummyAdapter)
    assert "test_dummy" in _TOOL_REGISTRY
    assert _TOOL_REGISTRY["test_dummy"] is _DummyAdapter


def test_register_tool_returns_class():
    result = register_tool(_DummyAdapter2)
    assert result is _DummyAdapter2


def test_register_tool_rejects_duplicate():
    register_tool(_DummyAdapter)
    with pytest.raises(ValueError, match="already registered"):
        register_tool(_DummyAdapter)


def test_get_tool_class_raises_for_unknown():
    with pytest.raises(ValueError, match="Tool not registered"):
        get_tool_class("nonexistent_tool_xyz")


def test_get_tool_class_returns_registered_class():
    register_tool(_DummyAdapter)
    cls = get_tool_class("test_dummy")
    assert cls is _DummyAdapter


def test_get_tool_instantiates_adapter():
    register_tool(_DummyAdapter)
    instance = get_tool("test_dummy")
    assert isinstance(instance, _DummyAdapter)
    assert instance.name == "test_dummy"


def test_list_tools_returns_sorted_names():
    register_tool(_DummyAdapter2)
    register_tool(_DummyAdapter)
    tools = list_tools()
    # shared 的 6 个 + test_dummy + test_dummy2 = 8 个
    assert "test_dummy" in tools
    assert "test_dummy2" in tools
    assert tools == sorted(tools)  # 已排序


def test_list_tools_contains_shared_adapters():
    """确认 conftest.py 触发的 shared adapter 注册仍生效。"""
    tools = list_tools()
    for n in ("file", "strings", "binwalk", "foremost", "exiftool", "xxd"):
        assert n in tools, f"shared adapter {n!r} not registered"