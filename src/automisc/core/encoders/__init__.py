"""Encoding 分支（per ``Architecture.md`` §4.4 + ``tools.md`` §3.8）

**v0.1 不在工具池层**——编码是**纯 Python 实现**，不是外部 CLI 包装（per PR0 cleanup 决策）。

子模块：
- base: base16/32/36/58/62/64/85/91/92/100/2048/32768/65536 编码解码
- base_custom: base64 自定义表编码解码（per v0.5-base-rot-decoders）
- classical: ROT5/13/18/47 + Caesar + Vigenère + Atbash + Pigpen + Rail Fence + Affine
- custom: BCD / IEEE 754 / UTF-16 endianness / Unicode Tags / Multi-layer auto-decoder
- base64_stego: base64 末 2 bit 隐写解码（per v0.5-base-rot-decoders PR2）

调用方式（v0.1）：
- GUI 用户在文件被识别为"含编码候选字符串"时弹出"尝试解码"菜单
- 每个 decoder 调一次可疑点列表
- v0.1 不做自动编排（v0.5+ 模板/DAG）
"""
from automisc.core.encoders import base, base_custom, base64_stego, classical, custom  # noqa: F401
