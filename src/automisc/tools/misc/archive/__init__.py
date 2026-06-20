"""Misc/Archive 子包（per ``tools.md`` §3.9）

v0.1.0b-PR5 范围：sevenz + unzip + john 三个 adapter。
v0.5-zip-verdict-pool: 加 zip_classify (per Owner 2026-06-20 14:13 实战反馈,
 拖 ZIP 进去没 verdict, 加 per-entry 伪/真/clear 分类 + clear 自动解压).

**重要**: 每个 adapter 都要在这里显式 import, 触发 @register_tool 装饰器
(GUI 启动只 import subpackage __init__, 不 import 父包 automisc.tools.__init__).
"""
from automisc.tools.misc.archive import john  # noqa: F401
from automisc.tools.misc.archive import sevenz  # noqa: F401
from automisc.tools.misc.archive import unzip  # noqa: F401
from automisc.tools.misc.archive import zip_classify  # noqa: F401  # v0.5-zip-verdict-pool
