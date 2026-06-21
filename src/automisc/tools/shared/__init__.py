"""共享基础工具（per ``tools.md`` §3.12）

v0.1.0b-PR1 全部 6 个 adapter：file / strings / binwalk / foremost / exiftool / xxd
v0.5-lsb-bytes-auto-run 加 LsbBytesExtractAdapter (auto-run 兜底 zsteg 漏报)
"""
from .lsb_bytes_extract_adapter import LsbBytesExtractAdapter  # noqa: F401  触发 @register_tool