"""FileRouter 入口分流（v0.1.1 core 完整性补齐）

根据文件 extension / magic bytes / 大小，**推荐**合适的工具列表。

设计原则（per ``Architecture.md`` §3.5）：
- **推荐**而非"自动跑"——输出有序列表（含 reason），由用户（GUI / CLI）决定跑哪个
- 多策略：extension 优先（fast）→ magic bytes（medium）→ size heuristics（fallback）
- 不持有 GUI 状态 / 不直接调工具
- 与 ``FileNotAutomiscError`` 错误体系集成

v0.1.1 范围：
- extension → 推荐工具（覆盖 .pcap/.wav/.mp4/.zip/.png/.log/.evtx 等常见格式）
- magic bytes 探测（libmagic）
- 兜底：未知扩展名 → 返回 ["file", "strings", "binwalk"] 通用分析三件套

v0.5+ 路线：
- 内容相似度（jaccard 文本相似度）
- 工具链 DAG 编排
- LLM 决策（per prd.md §2 明确禁止；v0.5+ 也不引入）
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from automisc.core.exceptions import FileNotAutomiscError


@dataclass
class RouteRecommendation:
    """单个工具的推荐理由 + 排序分."""

    tool_name: str
    reason: str
    score: int = 0  # 越高越靠前


@dataclass
class RouteResult:
    """router 整体输出：检测到的文件类型 + 推荐工具列表."""

    file_path: str
    file_size: int
    detected_extension: str
    detected_magic: str | None  # 如 "PNG image data" / "ASCII text"
    recommendations: list[RouteRecommendation] = field(default_factory=list)


# extension → 推荐工具 + 理由 + 默认 score
EXTENSION_ROUTES: dict[str, list[tuple[str, str, int]]] = {
    # 图片 (Stego)
    ".png": [("zsteg", "PNG LSB 隐写常用", 10), ("steghide", "PNG/BMP 隐写", 8), ("exiftool", "EXIF metadata", 6), ("binwalk", "PNG 内嵌文件检测", 5), ("strings", "可疑字符串 (rule_scanner)", 3)],
    ".bmp": [("steghide", "BMP 隐写", 10), ("exiftool", "BMP metadata", 6)],
    ".jpg": [("exiftool", "JPEG EXIF", 8), ("binwalk", "JPEG 内嵌文件", 5), ("strings", "可疑字符串 (rule_scanner)", 4)],
    ".jpeg": [("exiftool", "JPEG EXIF", 8), ("binwalk", "JPEG 内嵌文件", 5)],
    ".gif": [("exiftool", "GIF metadata", 6), ("binwalk", "GIF 内嵌", 5)],
    # 音视频 (Stego)
    ".wav": [("sox", "WAV metadata + 频谱", 10), ("ffmpeg_audio", "音频元数据", 8), ("steghide_audio", "WAV/AU 隐写", 8), ("ffprobe", "流信息", 5)],
    ".mp3": [("ffmpeg_audio", "MP3 metadata", 10), ("ffprobe", "流信息", 6), ("strings", "ID3 tag", 3)],
    ".flac": [("ffprobe", "FLAC metadata", 10), ("ffmpeg_audio", "音频信息", 6)],
    ".ogg": [("ffprobe", "OGG metadata", 10), ("ffmpeg_audio", "音频信息", 6)],
    ".mp4": [("ffprobe", "MP4 stream info", 10), ("ffmpeg_video", "视频元数据", 8), ("strings", "字幕/标签", 3)],
    ".avi": [("ffprobe", "AVI stream", 10), ("ffmpeg_video", "视频元数据", 8)],
    ".mkv": [("ffprobe", "MKV stream", 10), ("ffmpeg_video", "视频元数据", 8)],
    # 网络 (Forensics) — v0.5-pcap-protocol-router: pcap_protocol_router 优先
    ".pcap": [
        ("pcap_protocol_router", "pcap 协议层路由：协议分类 + TLS key 候选发现 + Wireshark 模板", 12),
        ("tshark", "PCAP 协议解析（基础）", 8),
        ("tcpdump", "PCAP 抓包分析（fallback）", 6),
        ("strings", "明文协议字段", 3),
    ],
    ".pcapng": [
        ("pcap_protocol_router", "pcap 协议层路由", 12),
        ("tshark", "PCAP-NG 协议解析", 8),
        ("tcpdump", "PCAP-NG", 6),
    ],
    # 压缩 (Archive)
    ".zip": [("sevenz", "ZIP 完整性 + 伪加密检测", 10), ("unzip", "ZIP 列表 + 提取", 8), ("john", "ZIP 密码爆破", 5)],
    ".7z": [("sevenz", "7z 完整性", 10), ("john", "7z 密码爆破", 5)],
    ".rar": [("sevenz", "RAR 完整性", 10), ("john", "RAR 密码爆破", 5)],
    ".tar": [("sevenz", "TAR 列表", 10)],
    ".gz": [("sevenz", "GZIP 解压", 10), ("strings", "压缩前文本片段", 3)],
    # 日志 (Forensics)
    ".log": [("grep", "关键字扫描 (password/secret/hidden)", 10), ("strings", "可疑行", 5)],
    ".evtx": [("evtx_dump", "Windows EVTX 事件解析", 10), ("strings", "原始文本", 3)],
    # 内存 (Forensics)
    ".vmem": [("vol", "vol.py 内存分析 (pslist/pstree/netscan)", 10), ("strings", "明文凭证", 5)],
    # 二进制 / 杂项
    ".bin": [("file", "文件类型识别", 10), ("binwalk", "内嵌文件检测", 8), ("strings", "明文字符串", 5), ("xxd", "hex dump", 5)],
    ".exe": [("file", "PE 头识别", 10), ("binwalk", "内嵌文件", 8), ("strings", "明文", 5)],
    ".dll": [("file", "PE 头", 10), ("binwalk", "内嵌", 8), ("strings", "导出表", 5)],
    ".elf": [("file", "ELF 头", 10), ("binwalk", "内嵌", 8), ("strings", "明文", 5)],
    # QR
    ".png_qr": [("zbar", "QR/条码识别", 10)],  # 实际还是 .png，扫描后归类
}

# 通用兜底
FALLBACK_TOOLS: list[tuple[str, str, int]] = [
    ("file", "通用文件类型识别", 10),
    ("strings", "明文字符串", 8),
    ("binwalk", "内嵌文件检测", 6),
    ("xxd", "hex dump", 5),
]

# 文本兜底（小文本文件 + 无扩展名）
TEXT_FALLBACK: list[tuple[str, str, int]] = [
    ("strings", "明文 / 文本", 10),
    ("file", "文件类型识别", 8),
    ("xxd", "hex dump", 5),
]


# Magic bytes → 描述
MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF87a image"),
    (b"GIF89a", "GIF89a image"),
    (b"BM", "BMP image"),
    (b"PK\x03\x04", "ZIP archive"),
    (b"7z\xbc\xaf\x27\x1c", "7z archive"),
    (b"Rar!", "RAR archive"),
    (b"\x1f\x8b", "GZIP archive"),
    (b"RIFF", "RIFF (WAV/AVI)"),
    (b"\xff\xfb", "MP3 audio"),
    (b"ID3", "MP3 with ID3 tag"),
    (b"OggS", "OGG container"),
    (b"\x00\x00\x00\x20ftyp", "MP4/MOV container"),
    (b"\xd4\xc3\xb2\xa1", "PCAP little-endian"),
    (b"\xa1\xb2\xc3\xd4", "PCAP big-endian"),
    (b"\x0a\x0d\x0d\x0a", "PCAP-NG"),
    (b"MZ", "PE/EXE"),
    (b"\x7fELF", "ELF binary"),
    (b"MThd", "MIDI"),
    (b"SQLite format 3", "SQLite DB"),
]


def detect_magic(data: bytes, max_len: int = 16) -> Optional[str]:
    """通过 magic bytes 探测文件类型.

    Args:
        data: 文件前 N 字节
        max_len: 探测的最大字节数

    Returns:
        检测到的类型描述（None 表示未识别）
    """
    for sig, desc in MAGIC_SIGNATURES:
        if data[: len(sig)] == sig:
            return desc
    return None


class FileRouter:
    """文件 → 推荐工具.

    用法::

        router = FileRouter()
        result = router.route("/tmp/sample.pcap")
        for rec in result.recommendations:
            print(f"{rec.score:3d}  {rec.tool_name:15s}  {rec.reason}")
    """

    def route(self, file_path: str | Path) -> RouteResult:
        """给一个文件路径，返回推荐工具列表.

        Args:
            file_path: 文件路径

        Returns:
            RouteResult 含检测信息 + 推荐列表（按 score 降序）

        Raises:
            FileNotAutomiscError.not_found: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotAutomiscError.not_found(str(path))

        # 1) extension
        ext = path.suffix.lower()
        # 2) magic bytes (前 16 字节)
        magic = None
        try:
            with open(path, "rb") as f:
                head = f.read(16)
            magic = detect_magic(head)
        except OSError:
            pass  # 不可读 → 走 size 兜底

        # 3) 选推荐
        recs: list[RouteRecommendation] = []

        if ext in EXTENSION_ROUTES:
            for tool, reason, score in EXTENSION_ROUTES[ext]:
                recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score))
        elif magic and "image" in magic.lower():
            # magic 探测到 image 但 ext 未知
            for tool, reason, score in EXTENSION_ROUTES[".png"][:3]:
                recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score))
        elif magic and "archive" in magic.lower():
            for tool, reason, score in EXTENSION_ROUTES[".zip"][:3]:
                recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score))
        elif magic in ("RIFF (WAV/AVI)",):
            for tool, reason, score in EXTENSION_ROUTES[".wav"][:3]:
                recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score))
        else:
            # 兜底
            for tool, reason, score in FALLBACK_TOOLS:
                recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score))
            # 文本小文件
            if path.stat().st_size < 10_000 and self._looks_like_text(head):
                for tool, reason, score in TEXT_FALLBACK:
                    recs.append(RouteRecommendation(tool_name=tool, reason=reason, score=score + 2))

        # 排序：score 降序
        recs.sort(key=lambda r: (-r.score, r.tool_name))

        return RouteResult(
            file_path=str(path),
            file_size=path.stat().st_size,
            detected_extension=ext,
            detected_magic=magic,
            recommendations=recs,
        )

    @staticmethod
    def _looks_like_text(data: bytes) -> bool:
        """启发式：前 256 字节是否大多数 printable ASCII / UTF-8."""
        if not data:
            return True
        sample = data[:256]
        printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
        return printable / len(sample) > 0.85


__all__ = [
    "FileRouter",
    "RouteResult",
    "RouteRecommendation",
    "EXTENSION_ROUTES",
    "MAGIC_SIGNATURES",
    "detect_magic",
]
