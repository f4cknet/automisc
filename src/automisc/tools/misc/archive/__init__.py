"""Misc/Archive 子包（per ``tools.md`` §3.9）

v0.1.0b-PR5 范围：sevenz + john 两个 adapter。
v0.5-zip-verdict-pool: 加 zip_classify (per Owner 2026-06-20 14:13 实战反馈,
  拖 ZIP 进去没 verdict, 加 per-entry 伪/真/clear 分类 + clear 自动解压).
v0.5-sevenz-extract: 加 sevenz_extract (per Owner 2026-06-20 19:48 拍板,
  GUI 工具栏 "Misc/Archive" 下新增 "📦 7z 解压", 跟 sevenz 对偶).
v0.5-unzip-remove: 删 unzip adapter (per Owner 2026-06-30 21:21 拍板,
  Win 端永远 exit 127; sevenz + zip_classify + zipfile 自研完全替代).
v0.5-qemu-img-remove (per Owner 2026-06-30 22:16 拍板反转 v0.5-qemu-img-adapter):
  删 qemu_img + qemu_img_extract adapter, 因为 7z 23.01 完整安装实测支持 vmdk
  (per v0.5-train-019 + v0.5-7z-layout-migrate), sevenz_extract 已覆盖真实解压能力.

**重要**: 每个 adapter 都要在这里显式 import, 触发 @register_tool 装饰器
(GUI 启动只 import subpackage __init__, 不 import 父包 automisc.tools.__init__).
"""
from automisc.tools.misc.archive import john  # noqa: F401
from automisc.tools.misc.archive import sevenz  # noqa: F401
from automisc.tools.misc.archive import sevenz_extract  # noqa: F401  # v0.5-sevenz-extract
from automisc.tools.misc.archive import zip_classify  # noqa: F401  # v0.5-zip-verdict-pool
