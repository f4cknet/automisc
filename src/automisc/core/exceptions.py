"""automisc 错误体系（v0.1.1 core 完整性补齐）

所有 automisc 内部错误必须派生自 ``AutomiscError``，**不**使用 bare
``ValueError`` / ``RuntimeError`` / ``Exception``。

设计原则（per ``Architecture.md`` §3.7）：
- 顶层基类 ``AutomiscError`` 统一捕获入口
- 子类按层级 + 来源分类：
    - 配置类（registry / route）
    - 工具类（adapter 找不到 / adapter 跑失败 / 输出异常）
    - 文件类（不存在 / 不可读 / 太大）
- 保留 ``__cause__`` 链（``raise ... from e``）
"""

from __future__ import annotations

from typing import Any


class AutomiscError(Exception):
    """automisc 所有错误的统一基类.

    Args:
        message: 人类可读错误描述
        context: 可选 dict 携带调试上下文（tool_name / file_path / 等）
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        cls_name = type(self).__name__
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{cls_name}: {self.message} ({ctx})"
        return f"{cls_name}: {self.message}"


# === 配置类 ===
class RegistryError(AutomiscError):
    """registry 重复注册 / 装饰器使用错误."""


class RoutingError(AutomiscError):
    """FileRouter 无法给文件推荐工具."""


# === 工具类 ===
class ToolNotFoundError(AutomiscError):
    """请求的工具名未在 registry 中."""


class ToolRunError(AutomiscError):
    """工具执行失败（subprocess error / timeout / permission）."""


class ToolOutputError(AutomiscError):
    """工具输出解析失败（stdout 不是预期格式）."""


# === 文件类 ===
class FileNotAutomiscError(AutomiscError):
    """文件不存在 / 不可读 / 太大."""

    @classmethod
    def not_found(cls, path: str) -> "FileNotAutomiscError":
        return cls(
            f"file not found: {path}",
            context={"path": path, "reason": "not_found"},
        )

    @classmethod
    def not_readable(cls, path: str, reason: str = "permission") -> "FileNotAutomiscError":
        return cls(
            f"file not readable: {path} ({reason})",
            context={"path": path, "reason": reason},
        )

    @classmethod
    def too_large(cls, path: str, size: int, max_size: int) -> "FileNotAutomiscError":
        return cls(
            f"file too large: {path} ({size} > {max_size} bytes)",
            context={"path": path, "size": size, "max_size": max_size},
        )


__all__ = [
    "AutomiscError",
    "RegistryError",
    "RoutingError",
    "ToolNotFoundError",
    "ToolRunError",
    "ToolOutputError",
    "FileNotAutomiscError",
]
