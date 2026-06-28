"""Steganography 分支（per ``Architecture.md`` §4.4 + ``tools.md`` §3.5-3.7）

子包：
- image/ —— v0.1.0b-PR2（lsb_tool + steghide; per v0.5-lsb-tool-bitplane-preview-matrix zsteg 替换为 lsb_tool, per v0.5-stegseek-remove stegseek 替换为 steghide）
- audio/ —— v0.1.0b-PR4（ffmpeg + sox + steghide_audio）
- video/ —— v0.1.0b-PR4（ffprobe + ffmpeg_video）
"""
from automisc.tools.steganography import audio, image, video  # noqa: F401
