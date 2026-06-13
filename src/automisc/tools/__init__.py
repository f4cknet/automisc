"""工具池层（per ``Architecture.md`` §4）

v0.1.0b-PR1 范围：
- ``base`` — ToolAdapter 抽象基类
- ``shared`` — 共享基础工具（file / strings / binwalk / foremost / exiftool / xxd）
"""

# 显式 import 触发 @register_tool 装饰器
# （per Architecture.md §6.3）
from automisc.tools import base  # noqa: F401

# shared/ 的 6 个 adapter 显式 import
from automisc.tools.shared import binwalk  # noqa: F401
from automisc.tools.shared import exiftool  # noqa: F401
from automisc.tools.shared import file  # noqa: F401
from automisc.tools.shared import foremost  # noqa: F401
from automisc.tools.shared import strings  # noqa: F401
from automisc.tools.shared import xxd  # noqa: F401