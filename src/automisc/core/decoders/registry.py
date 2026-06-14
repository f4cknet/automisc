"""Decoder registry (v0.5-decoder-menu)

**职责**：注册所有 decoder (base64 / base-convert / jpeg-trailer / qr-coords / ...)
单一事实来源 —— CLI 和 GUI 都从 REGISTRY 拿菜单项, 不会脱节.

**v0.5-cipher-decoders**：加 ``group`` 字段，老 ``category`` 字段保留（向后兼容）。
GUI 渲染顺序：group（"解密工具1/2/3"）优先 → category 兜底。

**使用**:
```python
from automisc.core.decoders.registry import (
    REGISTRY, DecoderSpec, register_decoder,
)

# 老用法（仅 category，渲染在 Tools 下 "Decode"/"Convert"/...）
register_decoder(DecoderSpec(
    name="base64-image",
    display="Base64 → 图片",
    category="decode",
    cli_cmd="decode base64-image",
    run=decode_file_to_image,
    description="base64 -> 图片（自动识别 data: 头 + file 验证）",
))

# 新用法（cipher，渲染在 Tools 下 "解密工具1"）
register_decoder(DecoderSpec(
    name="caesar",
    display="🔐 凯撒解密",
    category="cipher",  # 兜底 category
    group="解密工具1",
    cli_cmd="decode caesar",
    run=run_caesar,
    description="凯撒密码解密 (默认 shift=3, --shift N 可调)",
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
        name: decoder 内部名 (e.g. "base64-image", "base-convert", "caesar")
        display: GUI 菜单显示 (中文 + emoji)
        category: 兼容旧字段 — GUI 菜单分组 ("decode" / "convert" / "extract" / "base_rot" ...)
        group: v0.5-cipher-decoders — GUI 一级目录分组 ("解密工具1" / "解密工具2" / ...)
            默认 "general"（兼容老 decoder，仍走 category 渲染）
        text_only: v0.5-cipher-decoders-textfix — 该 decoder 是否只接受 text input
            (不从 file 读). True = GUI _run_decoder 跳过 file 检查走 input 区.
            默认 False (保持向后兼容, 老 base64-image 等 file-based decoder 不变)
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
    group: str = "general"  # v0.5-cipher-decoders 加的字段，老 decoder 留空走默认
    text_only: bool = False  # v0.5-cipher-decoders-textfix 加的字段


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
    """按 category 分组 (per GUI 老菜单, 兼容 v0.5-decoder-menu).

    注意：v0.5-cipher-decoders 加的 cipher decoder 也会出现在这里（按各自 category），
    所以此函数在 cipher 阶段可能返回空 category（如 "cipher" 一组），
    GUI 应该用 list_decoders_by_group() + list_decoders_by_category() 一起渲染。
    """
    grouped: dict[str, list[DecoderSpec]] = {}
    for spec in REGISTRY:
        grouped.setdefault(spec.category, []).append(spec)
    return grouped


def list_decoders_by_group() -> dict[str, list[DecoderSpec]]:
    """按 group 分组 (per v0.5-cipher-decoders — "解密工具1/2/3").

    返回的 dict 按注册顺序保留 group 出现顺序（python dict 自带此性质）。
    未指定 group 的 decoder（group == "general"）不出现 — 仍走 category 渲染。
    """
    grouped: dict[str, list[DecoderSpec]] = {}
    for spec in REGISTRY:
        if spec.group == "general":
            continue  # 默认 group 不渲染（兼容老 decoder）
        grouped.setdefault(spec.group, []).append(spec)
    return grouped


__all__ = [
    "DecoderSpec",
    "DecoderRunner",
    "REGISTRY",
    "register_decoder",
    "get_decoder",
    "list_decoders",
    "list_decoders_by_category",
    "list_decoders_by_group",
]
