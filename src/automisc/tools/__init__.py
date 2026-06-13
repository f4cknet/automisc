"""工具池层（per ``Architecture.md`` §4）

v0.1.0b-PR1 范围：
- ``base`` — ToolAdapter 抽象基类
- ``shared`` — 共享基础工具（file / strings / binwalk / foremost / exiftool / xxd）

v0.1.0b-PR2 范围：
- ``steganography/image`` — Stego/Image（zsteg + steghide）
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

# steganography/image/ 的 2 个 adapter（v0.1.0b-PR2）
from automisc.tools.steganography.image import steghide  # noqa: F401
from automisc.tools.steganography.image import zsteg  # noqa: F401

# steganography/audio/ 的 3 个 adapter（v0.1.0b-PR4）
from automisc.tools.steganography.audio import ffmpeg_audio  # noqa: F401
from automisc.tools.steganography.audio import sox  # noqa: F401
from automisc.tools.steganography.audio import steghide_audio  # noqa: F401

# steganography/video/ 的 2 个 adapter（v0.1.0b-PR4）
from automisc.tools.steganography.video import ffmpeg_video  # noqa: F401
from automisc.tools.steganography.video import ffprobe  # noqa: F401

# forensics/network/ 的 2 个 adapter（v0.1.0b-PR3）
from automisc.tools.forensics.network import tcpdump  # noqa: F401
from automisc.tools.forensics.network import tshark  # noqa: F401

# misc/archive/ 的 3 个 adapter（v0.1.0b-PR5）
from automisc.tools.misc.archive import john  # noqa: F401
from automisc.tools.misc.archive import sevenz  # noqa: F401
from automisc.tools.misc.archive import unzip  # noqa: F401