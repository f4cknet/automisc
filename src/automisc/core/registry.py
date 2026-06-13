"""工具注册表（per ``Architecture.md`` §3.3）

``@register_tool`` 装饰器 + 查询 API。错误用 ``core.exceptions`` 子类。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from automisc.core.exceptions import RegistryError, ToolNotFoundError

if TYPE_CHECKING:
    from automisc.tools.base import ToolAdapter


_TOOL_REGISTRY: dict[str, type["ToolAdapter"]] = {}


def register_tool(cls: type["ToolAdapter"]) -> type["ToolAdapter"]:
    """工具 adapter 装饰器：注册到 ``_TOOL_REGISTRY``.

    用法::

        @register_tool
        class BinwalkAdapter(ToolAdapter):
            name = "binwalk"
            category = "binary_analysis"
            ...
    """
    if not getattr(cls, "name", ""):
        raise RegistryError(
            f"{cls.__name__}.name is empty; ToolAdapter subclass must define class attr `name`",
            context={"class": cls.__name__},
        )
    if cls.name in _TOOL_REGISTRY:
        existing = _TOOL_REGISTRY[cls.name]
        raise RegistryError(
            f"tool name {cls.name!r} already registered by {existing.__name__}; "
            f"cannot re-register with {cls.__name__}",
            context={"name": cls.name, "existing": existing.__name__},
        )
    _TOOL_REGISTRY[cls.name] = cls
    return cls


def get_tool_class(name: str) -> type["ToolAdapter"]:
    """根据名称取 adapter **类**（不实例化）."""
    if name not in _TOOL_REGISTRY:
        available = sorted(_TOOL_REGISTRY.keys())
        raise ToolNotFoundError(
            f"tool not registered: {name!r}",
            context={"name": name, "available": available},
        )
    return _TOOL_REGISTRY[name]


def get_tool(name: str) -> "ToolAdapter":
    """根据名称实例化工具 adapter."""
    return get_tool_class(name)()


def list_tools() -> list[str]:
    """列出所有已注册工具名（按字母排序）."""
    return sorted(_TOOL_REGISTRY.keys())


def list_tools_by_category(category: str) -> list[str]:
    """按 category 过滤工具名."""
    return sorted(
        name
        for name, cls in _TOOL_REGISTRY.items()
        if getattr(cls, "category", "") == category
    )


def clear_registry() -> None:
    """**仅供测试使用**：清空注册表."""
    _TOOL_REGISTRY.clear()