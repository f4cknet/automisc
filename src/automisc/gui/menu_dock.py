"""菜单树（左 QDockWidget）— 22 adapter 按 6 类分类 + 4 快捷工具 (v0.5 Actions).

分类（按 prd.md §4.1）：
- 共享基础工具 (PR1) — file / strings / binwalk / foremost / exiftool / xxd
- Stego/Image (PR2) — zsteg / steghide
- Forensics/Network (PR3) — tshark / tcpdump
- Stego/Audio+Video (PR4) — ffmpeg_audio / ffprobe / ffmpeg_video / sox / steghide_audio
- Misc/Archive (PR5) — sevenz / unzip / john
- Forensics/Log (PR6) — grep / evtx_dump
- Misc/Brainteaser (PR8) — zbar
- Forensics/Memory (PR7) — vol
- 快捷工具 (v0.5 Actions) — fix_pseudo_zip / bruteforce_zip / lsb_extract / bruteforce_rar
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem


# 工具 → 分类映射（v0.1 frozen 22 adapter + v0.5 4 快捷 action）
TOOL_CATEGORIES: dict[str, list[str]] = {
    "共享基础工具 (PR1)": ["file", "strings", "binwalk", "foremost", "exiftool", "xxd"],
    "Stego/Image (PR2)": ["zsteg", "steghide"],
    "Forensics/Network (PR3)": ["tshark", "tcpdump"],
    "Stego/Audio+Video (PR4)": [
        "ffmpeg_audio",
        "ffprobe",
        "ffmpeg_video",
        "sox",
        "steghide_audio",
    ],
    "Misc/Archive (PR5)": ["sevenz", "unzip", "john"],
    "Forensics/Log (PR6)": ["grep", "evtx_dump"],
    "Misc/Brainteaser (PR8)": ["zbar"],
    "Forensics/Memory (PR7)": ["vol"],
    "快捷工具 (v0.5 Actions)": [
        "fix_pseudo_zip",  # zip 伪加密破解 (FixPseudoEncryptionAction)
        "bruteforce_zip",  # zip 暴力破解 (BruteforceZipAction)
        "lsb_extract",  # PNG LSB 抽出 (LSBExtractAction)
        "bruteforce_rar",  # rar 暴力破解 (BruteforceRarAction)
    ],
}


# 快捷 action 显示名（v0.5 GUI 同步）
ACTION_DISPLAY_NAMES = {
    "fix_pseudo_zip": "🔓 修复 Zip 伪加密",
    "bruteforce_zip": "🔨 Zip 暴力破解 (4-6 位)",
    "lsb_extract": "🎨 PNG LSB 智能提取",
    "bruteforce_rar": "🔨 RAR 暴力破解 (4-6 位)",
}


class ToolMenuDock(QDockWidget):
    """工具菜单树（左侧 dock）。

    Args:
        tool_lister: callable 返回所有 tool name list（默认 list_tools）
        on_tool_selected: 选中 tool 时的 callback（tool_name: str）
    """

    def __init__(
        self,
        tool_lister: Optional[Callable[[], list[str]]] = None,
        on_tool_selected: Optional[Callable[[str], None]] = None,
        parent=None,
    ) -> None:
        super().__init__("工具菜单 (Tools)", parent)
        self._on_tool_selected = on_tool_selected
        if tool_lister is None:
            from automisc.core.registry import list_tools

            tool_lister = list_tools

        # tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("工具 / 分类")
        self.tree.setColumnCount(1)
        self.tree.itemClicked.connect(self._on_item_clicked)

        self._populate(tool_lister())
        self.setWidget(self.tree)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )

    def _populate(self, available_tools: list[str]) -> None:
        """填充树形结构：分类 → 工具."""
        available_set = set(available_tools)
        for category, tools in TOOL_CATEGORIES.items():
            cat_item = QTreeWidgetItem([category])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(cat_item)

            for tool in tools:
                # 快捷 action 用中文显示名
                display = ACTION_DISPLAY_NAMES.get(tool, tool)
                marker = "✓" if tool in available_set else "✗"
                child = QTreeWidgetItem([f"{marker} {display}"])
                child.setData(0, Qt.UserRole, tool)
                cat_item.addChild(child)

            cat_item.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        tool_name = item.data(0, Qt.UserRole)
        if tool_name and self._on_tool_selected:
            self._on_tool_selected(tool_name)
