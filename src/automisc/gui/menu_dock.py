"""菜单树（左 QDockWidget）— 22 adapter + 4 快捷 action + 21 decoder + 14 cipher (v0.5+)

分类（按 prd.md §4.1 + v0.5-cipher-decoders）：
- 共享基础工具 (PR1) — file / strings / binwalk / foremost / exiftool / xxd
- Stego/Image (PR2) — zsteg / steghide
- Forensics/Network (PR3) — tshark / tcpdump
- Stego/Audio+Video (PR4) — ffmpeg_audio / ffprobe / ffmpeg_video / sox / steghide_audio
- Misc/Archive (PR5) — sevenz_extract / unzip / john / zip_classify (sevenz 是探测类, GUI 不显示, per Owner 20:03)
- Forensics/Log (PR6) — grep / evtx_dump
- Misc/Brainteaser (PR8) — zbar
- Forensics/Memory (PR7) — vol
- 快捷工具 (v0.5 Actions) — fix_pseudo_zip / bruteforce_zip / lsb_extract / bruteforce_rar
- 解码工具 (v0.5+ Decoders) — base64-image (Bug fix 2026-06-14)
- 进制转换 (v0.5+ Convert) — hex-ascii (Bug fix 2026-06-14)
- QR 工具 (v0.5+ QR Tools) — coords-qr (Bug fix 2026-06-14, Owner 10:16)
- 🔐 Base/ROT 解码 (v0.5+ Decoders) — 18 项 (per Owner 17:09 扁平决策, 不分子分类)
- 🔤 解密工具1 (v0.5-cipher-decoders) — 12 经典 cipher (凯撒/培根/栅栏/猪圈/摩尔斯/xxencode/uuencode/jsfuck/jjencode/QP/BF/BubbleBabble)
- 📦 解密工具2 (v0.5-cipher-decoders) — 占位 (TBD)
- 📦 解密工具3 (v0.5-cipher-decoders) — 占位 (TBD)
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QTreeWidget, QTreeWidgetItem


# 工具 → 分类映射（v0.1 frozen 22 adapter + v0.5 4 快捷 action + 21 decoder + 14 cipher/占位）
# v0.5-cipher-decoders: cipher 和 占位从 core.decoders.registry 自动聚合到这里
TOOL_CATEGORIES: dict[str, list[str]] = {
    "共享基础工具 (PR1)": ["file", "strings", "binwalk", "foremost", "exiftool", "xxd"],
    "Stego/Image (PR2)": ["zsteg", "stegseek"],
    "Forensics/Network (PR3)": ["tshark", "tcpdump", "pcap_protocol_router"],  # v0.5-pcap-protocol-router
    "Stego/Audio+Video (PR4)": [
        "ffmpeg_audio",
        "ffprobe",
        "ffmpeg_video",
        "sox",
        "steghide_audio",
    ],
    "Misc/Archive (PR5)": ["sevenz_extract", "unzip", "john", "zip_classify"],
    "Forensics/Log (PR6)": ["grep", "evtx_dump"],
    "Misc/Brainteaser (PR8)": ["zbar"],
    "Forensics/Memory (PR7)": ["vol"],
    "快捷工具 (v0.5 Actions)": [
        "fix_pseudo_zip",  # zip 伪加密破解 (FixPseudoEncryptionAction)
        "bruteforce_zip",  # zip 暴力破解 (BruteforceZipAction)
        "lsb_extract",  # PNG LSB 抽出 (LSBExtractAction)
        "bruteforce_rar",  # rar 暴力破解 (BruteforceRarAction)
    ],
    "🔓 解码工具 (v0.5+ Decoders)": [
        "decoder:base64-image",  # bug fix 2026-06-14: 工具栏入口
    ],
    "🔢 进制转换 (v0.5+ Convert)": [
        "decoder:hex-ascii",  # bug fix 2026-06-14: 工具栏入口
        # v0.5-more-converts (per Owner 22:17): 6 个新转换工具
        "decoder:bin-ascii",  # 2 进 → ASCII
        "decoder:dec-bin",    # 10 进 → 2 进
        "decoder:bin-dec",    # 2 进 → 10 进
        "decoder:dec-hex",    # 10 进 → 16 进
        "decoder:hex-dec",    # 16 进 → 10 进
        "decoder:ascii-bin",  # ASCII → 2 进
    ],
    "🔳 QR 工具 (v0.5+ QR Tools)": [
        "decoder:coords-qr",  # 2026-06-14 10:16: 坐标串 → QR PNG → zbar 识别
    ],
    "🔐 Base/ROT 解码 (v0.5+ Decoders)": [
        # 12 个 Base 系列 (per v0.5-base-rot-decoders PR1+PR3)
        "decoder:base16",
        "decoder:base32",
        "decoder:base36",
        "decoder:base58",
        "decoder:base62",
        "decoder:base64",
        "decoder:base85",
        "decoder:base91",
        "decoder:base92",
        "decoder:base100",
        "decoder:base32768",
        "decoder:base65536",
        # 4 个 ROT 系列
        "decoder:rot5",
        "decoder:rot13",
        "decoder:rot18",
        "decoder:rot47",
        # 1 个 Base64 自定义表 (interactive, 弹 QInputDialog)
        "decoder:base64-custom",
        # 1 个 Base64 隐写 (per PR2)
        "decoder:base64-stego",
    ],
}


# 快捷 action / decoder 显示名（v0.5 GUI 同步）
# v0.5-cipher-decoders: cipher display name 从 core.decoders.registry 自动拿 (这里只留 fallback)
ACTION_DISPLAY_NAMES: dict[str, str] = {
    "fix_pseudo_zip": "🔓 修复 Zip 伪加密",
    "bruteforce_zip": "🔨 Zip 暴力破解 (4-6 位)",
    "lsb_extract": "🎨 PNG LSB 智能提取",
    "bruteforce_rar": "🔨 RAR 暴力破解 (4-6 位)",
    "sevenz_extract": "📦 7z 解压",  # v0.5-sevenz-extract Owner 2026-06-20 19:48
    "decoder:base64-image": "🔓 Base64 → 图片",
    # v0.5-cn-display (per Owner 22:39): 中文 display
    "decoder:hex-ascii": "🔢 16 进制转文本",
    "decoder:coords-qr": "🔳 坐标 → 二维码",  # v0.5-coords-qr
    # Base 系列（per v0.5-base-rot-decoders PR3）
    "decoder:base16": "🔢 Base16",
    "decoder:base32": "🔢 Base32",
    "decoder:base36": "🔢 Base36",
    "decoder:base58": "🔢 Base58",
    "decoder:base62": "🔢 Base62",
    "decoder:base64": "🔢 Base64",
    "decoder:base85": "🔢 Base85",
    "decoder:base91": "🔢 Base91",
    "decoder:base92": "🔢 Base92",
    "decoder:base100": "🔢 Base100",
    "decoder:base32768": "🔢 Base32768",
    "decoder:base65536": "🔢 Base65536",
    # ROT 系列
    "decoder:rot5": "🅰 ROT5",
    "decoder:rot13": "🅰 ROT13",
    "decoder:rot18": "🅰 ROT18",
    "decoder:rot47": "🌀 ROT47",
    # 特殊
    "decoder:base64-custom": "🔐 Base64 自定义表",
    "decoder:base64-stego": "🕵 Base64 隐写",
    # v0.5-more-converts: 6 个新进制转换 (per Owner 22:17)
    # v0.5-cn-display (per Owner 22:39): 全部中文, 方便非 CS 背景理解
    "decoder:bin-ascii": "💻 2 进制转文本",
    "decoder:dec-bin":   "🔟 10 进制转 2 进制",
    "decoder:bin-dec":   "💻 2 进制转 10 进制",
    "decoder:dec-hex":   "🔟 10 进制转 16 进制",
    "decoder:hex-dec":   "🔢 16 进制转 10 进制",
    "decoder:ascii-bin": "🔤 文本转 2 进制",
}


# v0.5-zbar-rename (per Owner 22:17): zbar 工具栏改名为"二维码解析"
# 备注: zbar 实际功能是 QR / barcode 解析 (zxing/zbarimg 类似), CTF 圈叫"二维码"更通俗
ZBAR_DISPLAY_NAME = "🔳 二维码解析"


# adapter 工具名集合 (per core.registry.list_tools())
# 其他以 "decoder:" 开头的是 decoder (走 _run_decoder)
# v0.5-sevenz-extract (per Owner 2026-06-20 19:48): 加 sevenz_extract 7z 解压
# v0.5-sevenz-toolbar-cleanup (per Owner 2026-06-20 20:03): 探测类 (sevenz) 不显示在 GUI menu,
#   但 adapter 仍注册 (auto_run / router / find_suspicious 用)
ADAPTER_TOOLS: set[str] = {
    "file", "strings", "binwalk", "foremost", "exiftool", "xxd",
    "zsteg", "stegseek",
    "tshark", "tcpdump",
    "ffmpeg_audio", "ffprobe", "ffmpeg_video", "sox", "steghide_audio",
    "sevenz", "sevenz_extract", "unzip", "john", "zip_classify",
    "grep", "evtx_dump",
    "zbar",
    "vol",
}


# v0.5-cipher-decoders: cipher/占位分组定义（左侧 dock 也渲染）
# display name 从 registry 自动拿, 这里只定义分类标题 + 占位顺序
CIPHER_DOCK_CATEGORIES: list[tuple[str, str]] = [
    # (group_name, prefix_emoji)
    ("解密工具1", "🔤"),
    ("解密工具2", "📦"),
    ("解密工具3", "📦"),
]


def _get_cipher_categories_from_registry() -> dict[str, list[str]]:
    """从 core.decoders.registry 按 group 聚合 cipher + 占位.

    Returns:
        {category_title: ["decoder:<name>", ...]} — 仅 cipher/占位组
        category_title 格式: "<emoji> <group> (v0.5-cipher-decoders)"
    """
    from automisc.core.decoders.registry import list_decoders_by_group

    result: dict[str, list[str]] = {}
    grouped = list_decoders_by_group()
    for group_name, emoji in CIPHER_DOCK_CATEGORIES:
        specs = grouped.get(group_name, [])
        if not specs:
            continue
        cat_title = f"{emoji} {group_name} (v0.5-cipher-decoders)"
        result[cat_title] = [f"decoder:{s.name}" for s in specs]
    return result


def _get_cipher_display_names() -> dict[str, str]:
    """从 core.decoders.registry 拿 cipher + 占位 display name."""
    from automisc.core.decoders.registry import REGISTRY

    names: dict[str, str] = {}
    for spec in REGISTRY:
        if spec.group == "general":
            continue
        names[f"decoder:{spec.name}"] = spec.display
    return names


class ToolMenuDock(QDockWidget):
    """工具菜单树（左侧 dock）。

    Args:
        tool_lister: callable 返回所有 tool name list（默认 list_tools）
        on_tool_selected: 选中 tool 时的 callback, signature (tool_name, kind)
                          kind = "adapter" | "action" | "decoder"
                          callback 自己 dispatch 到 _run_tool / _run_chain / _run_decoder
    """

    def __init__(
        self,
        tool_lister: Optional[Callable[[], list[str]]] = None,
        on_tool_selected: Optional[Callable[[str, str], None]] = None,
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
        """填充树形结构：分类 → 工具.

        v0.5-cipher-decoders: 先固定分类（adapter/快捷action/老 decoder）
        再从 registry 自动追加 "🔤/📦 解密工具1/2/3" 分类
        """
        available_set = set(available_tools)

        # 1) 老固定分类
        categories: dict[str, list[str]] = dict(TOOL_CATEGORIES)

        # 2) v0.5-cipher-decoders: 从 registry 追加 cipher 分类
        cipher_cats = _get_cipher_categories_from_registry()
        for cat_title, tools in cipher_cats.items():
            categories[cat_title] = tools

        # 3) display names: 老字典 + cipher 从 registry 拿
        display_names = dict(ACTION_DISPLAY_NAMES)
        display_names.update(_get_cipher_display_names())
        # v0.5-zbar-rename (per Owner 22:17): zbar 工具栏显示"二维码解析"
        display_names["zbar"] = ZBAR_DISPLAY_NAME

        for category, tools in categories.items():
            cat_item = QTreeWidgetItem([category])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(cat_item)

            for tool in tools:
                # 工具显示名
                display = display_names.get(tool, tool)
                # adapter 检查是否注册 (decoder 不需要)
                is_adapter = tool in ADAPTER_TOOLS
                marker = (
                    "✓" if (is_adapter and tool in available_set) or not is_adapter
                    else "✗"
                )
                child = QTreeWidgetItem([f"{marker} {display}"])
                child.setData(0, Qt.UserRole, tool)
                cat_item.addChild(child)

            cat_item.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        tool_name = item.data(0, Qt.UserRole)
        if not tool_name or not self._on_tool_selected:
            return
        # 决定 kind (callback 用作 dispatch)
        if tool_name.startswith("decoder:"):
            kind = "decoder"
            name = tool_name[len("decoder:"):]
        elif tool_name in ADAPTER_TOOLS:
            kind = "action" if tool_name in ("fix_pseudo_zip", "bruteforce_zip", "lsb_extract", "bruteforce_rar") else "adapter"
            name = tool_name
        else:
            kind = "action"
            name = tool_name
        self._on_tool_selected(name, kind)
