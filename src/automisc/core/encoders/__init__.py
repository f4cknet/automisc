"""Encoding 分支（per ``Architecture.md`` §4.4 + ``tools.md`` §3.8）

**v0.1 不在工具池层**——编码是**纯 Python 实现**，不是外部 CLI 包装（per PR0 cleanup 决策）。

子模块：
- base: base16/32/58/62/64/85/91/2048/32768/65536 编码解码
- classical: ROT/Caesar/Vigenère/Pigpen/Rail Fence/Atbash/Affine
- custom: BCD / IEEE 754 / UTF-16 endianness / Unicode Tags / Multi-layer auto-decoder

调用方式（v0.1）：
- GUI 用户在文件被识别为"含编码候选字符串"时弹出"尝试解码"菜单
- 每个 decoder 调一次可疑点列表
- v0.1 不做自动编排（v0.5+ 模板/DAG）
"""
from automisc.core.encoders import base, classical, custom  # noqa: F401
