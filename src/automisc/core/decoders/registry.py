"""Decoder registry (v0.5-decoder-menu)

**职责**：注册所有 decoder (base64 / base-convert / jpeg-trailer / qr-coords / ...)
单一事实来源 —— CLI 和 GUI 都从 REGISTRY 拿菜单项, 不会脱节.

**使用**:
```python
from automisc.core.decoders.registry import (
    REGISTRY, DecoderSpec, register_decoder,
)

register_decoder(DecoderSpec(
    name="base64-image",
    display="Base64 → 图片",
    category="decode",
    cli_cmd="decode base64-image",
    run=decode_file_to_image,
    description="base64 -> 图片（自动识别 data: 头 + file 验证）",
))
```
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


# Decoder runner 返回类型 (每种 decoder 自定义 dataclass)
# 通用 wrapper (GUI / CLI 用)
DecoderRunner = Callable[..., object]


@dataclass(frozen=True)
class DecoderSpec:
    """单个 decoder 的元数据.

    Attributes:
        name: decoder 内部名 (e.g. "base64-image", "base-convert")
        display: GUI 菜单显示 (中文 + emoji)
        category: GUI 菜单分组 ("decode" / "convert" / "extract")
        cli_cmd: CLI 子命令 (e.g. "decode base64-image")
        run: runner 函数 (file_path, **kwargs) -> result dataclass
        description: GUI 状态栏 tooltip
    """

    name: str
    display: str
    category: str
    cli_cmd: str
    run: DecoderRunner
    description: str = ""


# 全局 registry (按注册顺序)
REGISTRY: list[DecoderSpec] = []


def register_decoder(spec: DecoderSpec) -> None:
    """注册 decoder."""
    REGISTRY.append(spec)


def get_decoder(name: str) -> DecoderSpec | None:
    """按 name 找 decoder."""
    for spec in REGISTRY:
        if spec.name == name:
            return spec
    return None


def list_decoders() -> list[DecoderSpec]:
    """返回所有 decoder (注册顺序)."""
    return list(REGISTRY)


def list_decoders_by_category() -> dict[str, list[DecoderSpec]]:
    """按 category 分组 (per GUI 菜单)."""
    grouped: dict[str, list[DecoderSpec]] = {}
    for spec in REGISTRY:
        grouped.setdefault(spec.category, []).append(spec)
    return grouped


__all__ = [
    "DecoderSpec",
    "DecoderRunner",
    "REGISTRY",
    "register_decoder",
    "get_decoder",
    "list_decoders",
    "list_decoders_by_category",
]
