"""Forensics 分支 Network 子包（per ``Architecture.md`` §4.4 + ``tools.md`` §3.3）

v0.1.0b-PR3 范围：
- tshark —— 解析 pcap/pcapng/cap，输出协议摘要
- tcpdump —— pcap 解析（fallback）

详细 import 见 ``automisc.tools.__init__``（共享 adapter 触发 @register_tool）。
"""
from automisc.tools.forensics.network import tshark  # noqa: F401
from automisc.tools.forensics.network import tcpdump  # noqa: F401
