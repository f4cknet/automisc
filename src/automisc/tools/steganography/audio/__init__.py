"""Steganography/Audio 子包（per ``tools.md`` §3.6）

v0.1.0b-PR4 范围：
- ffmpeg_audio —— 音频元数据探测
- sox —— 音频元数据探测（与 ffmpeg 互补）
- steghide_audio —— WAV/AU 隐写检测（复用 steghide binary，仅 audio 入口）
"""
from automisc.tools.steganography.audio import ffmpeg_audio  # noqa: F401
from automisc.tools.steganography.audio import sox  # noqa: F401
from automisc.tools.steganography.audio import steghide_audio  # noqa: F401
