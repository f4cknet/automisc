"""pytest 全局配置。"""
import sys
from pathlib import Path

# 把 src/ 加入 sys.path（pyproject.toml 也配了，但保险起见）
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 集中触发所有 adapter 注册（per Architecture.md §6.3）
# 直接 import 6 个 adapter 模块，触发 @register_tool 装饰器
# 这比 import automisc.tools.shared 更可靠（避免 __init__.py 副作用）
from automisc.tools.shared import binwalk  # noqa: F401, E402
from automisc.tools.shared import exiftool  # noqa: F401, E402
from automisc.tools.shared import file  # noqa: F401, E402
from automisc.tools.shared import foremost  # noqa: F401, E402
from automisc.tools.shared import strings  # noqa: F401, E402
from automisc.tools.shared import xxd  # noqa: F401, E402