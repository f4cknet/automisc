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
# fix_decoder_registry_pyc_magic (per Owner 2026-07-01 实战 flag.pyc):
# v0.5-lsb-byte-stream-extract (magic_sniffer) + v0.5-pyc-magic-sniffer (pyc_decompiler)
# 之前只在 __main__.py 显式 import 触发 CLI 路径, 漏了 __init__.py 这边
# → GUI 路径走 `from automisc.core import decoders` 触发不到, DecodeRunner 报
# "unknown decoder: pyc_decompiler" (同 main_window.py:14 注释里 coords-qr 同类 bug).
# 修法: 在这里也 side-effect import, 让 GUI 启动时 registry 必含这 2 个.
from automisc.core.decoders import magic_sniffer  # noqa: F401, E402  # v0.5-lsb-byte-stream-extract
from automisc.core.decoders import pyc_decompiler  # noqa: F401, E402  # v0.5-pyc-magic-sniffer
# v0.5-sparse-grid-restore (per Owner 2026-07-01 拍板):
# 主动在 __init__.py import, 复刻 fix_decoder_registry_pyc_magic 修法, 避免 GUI 路径
# `from automisc.core import decoders` 触发不到 decoder 注册导致 "unknown decoder" bug.
from automisc.core.decoders import sparse_grid_restore  # noqa: F401, E402  # v0.5-sparse-grid-restore

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
    "magic_sniffer",  # v0.5-lsb-byte-stream-extract
    "pyc_decompiler",  # v0.5-pyc-magic-sniffer
    "sparse_grid_restore",  # v0.5-sparse-grid-restore
] 
