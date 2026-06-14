"""core.decoders package (v0.5-decoder-menu)

解码器/转换器/提取器 (CLI + GUI 共享).

**注册机制**: 每个 decoder module 导入时调 register_decoder().
**CLI**: `automisc decode <name>` (从 registry 动态生成 subparser)
**GUI**: "Tools" 菜单 (从 registry 动态生成)
  - v0.5-cipher-decoders: GUI 优先按 ``group`` 分（"解密工具1/2/3"）渲染，再按 ``category`` 兜底

**v0.5-cipher-decoders 新增**:
- ``group`` 字段（DecoderSpec）— Tools 顶级菜单下的"一级目录"
- ``list_decoders_by_group()`` — 按 group 分组给 GUI 用
- 12 个经典 cipher + 2 占位 → 注册到 group="解密工具1/2/3"
"""
from automisc.core.decoders.registry import (
    DecoderSpec,
    REGISTRY,
    get_decoder,
    list_decoders,
    list_decoders_by_category,
    list_decoders_by_group,
    register_decoder,
)

# 触发所有 decoder 注册 (import side-effect)
from automisc.core.decoders import base64_image  # noqa: F401, E402
from automisc.core.decoders import base_convert  # noqa: F401, E402
from automisc.core.decoders import coords_to_qr  # noqa: F401, E402
from automisc.core.decoders import base_rot_decoders  # noqa: F401, E402  # v0.5-base-rot-decoders
from automisc.core.decoders import cipher_decoders  # noqa: F401, E402  # v0.5-cipher-decoders (12 cipher + 2 placeholder)

__all__ = [
    "DecoderSpec",
    "REGISTRY",
    "register_decoder",
    "get_decoder",
    "list_decoders",
    "list_decoders_by_category",
    "list_decoders_by_group",
    "base64_image",
    "base_convert",
    "coords_to_qr",
    "base_rot_decoders",
    "cipher_decoders",
]
