"""工具池层（per ``Architecture.md`` §4）

v0.1.0b-PR1 范围：
- ``base`` — ToolAdapter 抽象基类
- ``shared`` — 共享基础工具（file / strings / binwalk / foremost / exiftool / xxd）

v0.1.0b-PR2 范围：
- ``steganography/image`` — Stego/Image（lsb_tool + steghide; per v0.5-lsb-tool-bitplane-preview-matrix zsteg 替换为 lsb_tool, per v0.5-stegseek-remove stegseek 替换为 steghide）
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

# steganography/image/ 的 3 个 adapter（v0.1.0b-PR2 + v0.5-lsb-detector + v0.5-lsb-tool-unify + v0.5-lsb-tool-bitplane-preview-matrix）
# zsteg 已彻底删除 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4, Owner Q4=b 拍板)
from automisc.tools.steganography.image import lsb_detect_adapter as _lsb_detect_v050  # noqa: F401  # v0.5-lsb-detector Owner 2026-06-21 22:00 (Phase 6 deprecated)
from automisc.tools.steganography.image import lsb_tool_adapter  # noqa: F401  # v0.5-lsb-tool-unify (Phase 3, 替代 lsb_detect auto-run + Commit 4 替代 zsteg)
from automisc.tools.steganography.image import steghide  # noqa: F401

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

# misc/archive/ 的 5 个 adapter（v0.1.0b-PR5 + v0.5-zip-verdict-pool + v0.5-sevenz-extract）
from automisc.tools.misc.archive import john  # noqa: F401
from automisc.tools.misc.archive import sevenz  # noqa: F401
from automisc.tools.misc.archive import sevenz_extract  # noqa: F401  # v0.5-sevenz-extract Owner 2026-06-20 19:48
from automisc.tools.misc.archive import unzip  # noqa: F401
from automisc.tools.misc.archive import zip_classify  # noqa: F401  # v0.5-zip-verdict-pool Owner 2026-06-20 14:13

# forensics/log/ 的 2 个 adapter（v0.1.0b-PR6）
from automisc.tools.forensics.log import evtx_dump  # noqa: F401
from automisc.tools.forensics.log import grep  # noqa: F401

# forensics/memory/ 的 1 个 adapter（v0.1.0b-PR7）
from automisc.tools.forensics.memory import vol  # noqa: F401

# misc/brainteaser/ 的 1 个 adapter（v0.1.0b-PR8）
from automisc.tools.misc.brainteaser import zbar  # noqa: F401