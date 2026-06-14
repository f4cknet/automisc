"""core.decoders package (v0.5-decoder-menu)

解码器/转换器/提取器 (CLI + GUI 共享).

**注册机制**: 每个 decoder module 导入时调 register_decoder().
**CLI**: `automisc decode <name>` (从 registry 动态生成 subparser)
**GUI**: "Tools" 菜单 (从 registry 动态生成)
"""
from automisc.core.decoders.registry import (
    DecoderSpec,
    REGISTRY,
    get_decoder,
    list_decoders,
    list_decoders_by_category,
    register_decoder,
)

# 触发所有 decoder 注册 (import side-effect)
from automisc.core.decoders import base64_image  # noqa: F401, E402
from automisc.core.decoders import base_convert  # noqa: F401, E402
from automisc.core.decoders import coords_to_qr  # noqa: F401, E402

__all__ = [
    "DecoderSpec",
    "REGISTRY",
    "register_decoder",
    "get_decoder",
    "list_decoders",
    "list_decoders_by_category",
    "base64_image",
    "base_convert",
    "coords_to_qr",
]
