"""AutoMisc — macOS GUI 半自动化 CTF Misc 工具箱

详细架构见 ``Architecture.md``；需求见 ``prd.md``；治理见 ``AGENTS.md``。
"""

__version__ = "0.1.0b.dev0"
__author__ = "Minzhi Zhou"

# Package marker — 真实实现按 PR 渐进引入：
# v0.1.0b-PR1: core/ + tools/shared/（基础 6 个 adapter）
# v0.1.0b-PR2~PR9: 各分支 adapter（per tools.md §6.2）
# v0.1.1+: gui/（PySide6）