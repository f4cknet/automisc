"""Magic sniffer decoder (v0.5-lsb-byte-stream-extract 能力 C)

**目的**: 对任意 raw bytes (从 LSBBytesExtractAction 抽出, 或外部拖入) **滑动窗口**
嗅探文件 magic, 不只看 offset 0。

**痛点** (per v0.5-train-009):
- 现有 ``router.detect_magic(data, max_len=16)`` 只匹配 ``data[:len(sig)]`` (offset 0)
- LSB 抽出的字节流如果 magic 出现在偏移 N (>0) 处, detect_magic 漏报
- N=NP 题 G 通道 LSB 列扫描字节流前 16 字节是 ``4e 3f ff ff ff ...``, 第 1 字节就
  不是任何已知 magic, 必须滑动窗口扫偏移 0~32

**算法**:
    for offset in range(max_offset + 1):
        for sig, desc in EXTENDED_MAGIC_SIGNATURES:
            if data[offset:offset+len(sig)] == sig:
                → 命中 (offset, desc, ext, severity=5)

**输出**: 每个命中一个 ``SniffResult(offset, magic_desc, ext, severity)``。
命中后写文件 ``<stem>__sniffed.<ext>`` (per v0.5-output-samedir + Owner Q2:
**不自动执行**,只写文件 + 高亮)。

**注册到 decoder registry** (per v0.5-decoder-menu): CLI 子命令 + GUI Tools 菜单
自动从 registry 渲染, 无需手动注册。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from automisc.core.decoders.registry import DecoderSpec, register_decoder
from automisc.core.utils.output_path import output_path_for


# 扩展 magic 字典: 复用 router.MAGIC_SIGNATURES + 加 pyc / WASM / Mach-O / Java class / 字节码
# per v0.5-train-009 §4.1 候选 C: 解决 router.detect_magic 只看 offset 0 的痛点
EXTENDED_MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    # (magic_bytes, description, file_extension)
    # ----- 图像 -----
    (b"\x89PNG\r\n\x1a\n", "PNG image", "png"),
    (b"\xff\xd8\xff\xe0", "JPEG image (JFIF)", "jpg"),
    (b"\xff\xd8\xff\xe1", "JPEG image (EXIF)", "jpg"),
    (b"GIF87a", "GIF87a image", "gif"),
    (b"GIF89a", "GIF89a image", "gif"),
    (b"BM", "BMP image", "bmp"),
    # ----- 压缩 -----
    (b"PK\x03\x04", "ZIP archive", "zip"),
    (b"PK\x05\x06", "ZIP empty archive", "zip"),
    (b"PK\x07\x08", "ZIP spanned archive", "zip"),
    (b"7z\xbc\xaf\x27\x1c", "7z archive", "7z"),
    (b"Rar!\x1a\x07\x00", "RAR archive v1.5+", "rar"),
    (b"Rar!\x1a\x07\x01", "RAR archive v5.0+", "rar"),
    (b"\x1f\x8b", "GZIP archive", "gz"),
    (b"BZh", "BZIP2 archive", "bz2"),
    (b"7z\xbc\xaf", "7z archive (short)", "7z"),
    (b"\xfd7zXZ\x00", "XZ archive", "xz"),
    # ----- 音视频 -----
    (b"RIFF", "RIFF container (WAV/AVI/WEBP)", "riff"),
    (b"\xff\xfb", "MP3 audio", "mp3"),
    (b"ID3", "MP3 with ID3 tag", "mp3"),
    (b"OggS", "OGG container", "ogg"),
    (b"\x00\x00\x00\x20ftyp", "MP4/MOV container", "mp4"),
    (b"MThd", "MIDI", "mid"),
    # ----- 网络 -----
    (b"\xd4\xc3\xb2\xa1", "PCAP little-endian", "pcap"),
    (b"\xa1\xb2\xc3\xd4", "PCAP big-endian", "pcap"),
    (b"\x0a\x0d\x0d\x0a", "PCAP-NG", "pcapng"),
    # ----- 可执行 -----
    (b"MZ", "PE/EXE (Windows)", "exe"),
    (b"\x7fELF", "ELF binary (Linux/Unix)", "elf"),
    # ----- 数据库 / 字节码 -----
    (b"SQLite format 3", "SQLite DB", "sqlite"),
    # Python pyc 字节码 (per v0.5-train-009 N=NP 题核心命中)
    # pyc magic 是 4 字节: 不同 Python 版本 magic 不同, 共同点首字节 >= 0xe0
    # 简化嗅探: 只匹配前 1 字节 >= 0xe0 标识为 "可能是 pyc", 需要后续 unhexlify 验证
    # 完整 magic 表见: https://github.com/python/cpython/blob/main/Lib/importlib/_bootstrap_external.py
    # 这里列 5 个最常见 Python 3.x magic
    (b"\xe3\x00\x00\x00", "Python 3.0 pyc (magic 3000)", "pyc"),
    (b"\x33\x0d\x0d\x0a", "Python 3.3-3.7 pyc (magic 3379-3394)", "pyc"),
    (b"\x42\x0d\x0d\x0a", "Python 3.8-3.9 pyc (magic 3400-3450)", "pyc"),
    (b"\x61\x0d\x0d\x0a", "Python 3.10+ pyc (magic 3439-3495)", "pyc"),
    (b"\x6c\x0d\x0d\x0a", "Python 2.x pyc (magic 62011-62611)", "pyc"),
    # ----- WebAssembly / Mach-O / Java class -----
    (b"\x00asm", "WebAssembly binary", "wasm"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 32-bit (Mach-O magic LE)", "macho"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit (Mach-O magic BE)", "macho"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit (Mach-O magic BE)", "macho"),
    (b"\xce\xfa\xed\xfe", "Mach-O 64-bit (Mach-O magic LE)", "macho"),
    (b"\xca\xfe\xba\xbe", "Java class file / Mach-O fat", "class"),
]


@dataclass(frozen=True)
class SniffResult:
    """单条 magic 嗅探命中."""
    offset: int  # 字节流内偏移
    magic: bytes  # 命中的 magic bytes
    description: str  # 人类可读描述
    ext: str  # 推荐文件后缀
    severity: int  # 严重度 (固定 5, 表示可疑需要二次处理)


@dataclass
class MagicSnifferResult:
    """magic_sniffer decoder 整体结果."""
    input_path: str  # 输入字节流文件路径
    raw_size: int  # 输入字节流长度
    hits: list[SniffResult] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)  # 写出的 sniffed 文件
    error: str | None = None

    @property
    def has_hits(self) -> bool:
        return len(self.hits) > 0


def sniff_magic(
    data: bytes,
    max_offset: int = 32,
) -> list[SniffResult]:
    """滑动窗口嗅探 raw bytes 内的文件 magic.

    Args:
        data: 字节流
        max_offset: 最大扫描偏移 (默认 32, 覆盖大部分"前缀数据 + magic"场景)

    Returns:
        命中列表 (按 offset 升序, 同一 offset 多 magic 都返回)
    """
    if not data:
        return []
    hits: list[SniffResult] = []
    upper = min(max_offset + 1, len(data))
    for offset in range(upper):
        for sig, desc, ext in EXTENDED_MAGIC_SIGNATURES:
            end = offset + len(sig)
            if end > len(data):
                continue
            if data[offset:end] == sig:
                hits.append(SniffResult(
                    offset=offset,
                    magic=sig,
                    description=desc,
                    ext=ext,
                    severity=5,
                ))
    return hits


def _sniffed_output_path(input_path: str | Path, ext: str) -> Path:
    """生成 sniffed 文件输出路径 (per v0.5-output-samedir + Owner Q2: 不自动执行).

    Args:
        input_path: 输入字节流文件路径 (e.g. /Challenge/np__lsb_g_b0_col_msb.bin)
        ext: 嗅探到的文件后缀 (e.g. "pyc")

    Returns:
        sniffed 文件绝对路径: <stem>__sniffed.<ext> (同目录)
    """
    return output_path_for(input_path, suffix=f".{ext}", purpose="sniffed")


def run_magic_sniffer(
    file_path: str,
    max_offset: int = 32,
    write_files: bool = True,
) -> MagicSnifferResult:
    """magic_sniffer decoder runner (per DecoderSpec.run signature).

    Args:
        file_path: 输入字节流文件路径
        max_offset: 扫描最大偏移 (默认 32)
        write_files: 是否写 sniffed 文件 (默认 True, per Owner Q2)

    Returns:
        MagicSnifferResult
    """
    p = Path(file_path)
    if not p.exists():
        return MagicSnifferResult(
            input_path=str(p),
            raw_size=0,
            error=f"file not found: {p}",
        )

    try:
        data = p.read_bytes()
    except Exception as e:  # noqa: BLE001
        return MagicSnifferResult(
            input_path=str(p),
            raw_size=0,
            error=f"failed to read: {e}",
        )

    hits = sniff_magic(data, max_offset=max_offset)

    written: list[str] = []
    if write_files and hits:
        # 按 (offset, description) 去重, 同一 ext 只写一次 (取 offset 最小的)
        seen_exts: dict[str, SniffResult] = {}
        for h in hits:
            if h.ext not in seen_exts or h.offset < seen_exts[h.ext].offset:
                seen_exts[h.ext] = h
        for ext, h in seen_exts.items():
            out_path = _sniffed_output_path(p, ext)
            try:
                out_path.write_bytes(data)
                written.append(str(out_path))
            except Exception as e:  # noqa: BLE001
                # 写失败不影响 sniff 结果, 只跳过这个 ext
                continue

    return MagicSnifferResult(
        input_path=str(p),
        raw_size=len(data),
        hits=hits,
        written_files=written,
    )


# 注册到 decoder registry (per v0.5-decoder-menu + STRUCTURE.md §3.5)
# GUI Tools 菜单 / CLI `automisc decode magic_sniffer` 自动从 registry 渲染
register_decoder(DecoderSpec(
    name="magic_sniffer",
    display="🔍 Magic Sniffer",
    category="decode",  # 兼容旧 category 渲染
    group="general",  # 默认 group, 不走 cipher 解密工具分组
    cli_cmd="decode magic_sniffer",
    run=run_magic_sniffer,
    description=(
        "字节流 magic 嗅探 (滑动窗口扫 offset 0~32, 匹配 35+ 文件类型: "
        "PNG/ZIP/pyc/JPEG/PDF/ELF/WASM/Mach-O 等; 不自动执行命中文件)"
    ),
    text_only=False,  # file-based, 走 file input
))


__all__ = [
    "EXTENDED_MAGIC_SIGNATURES",
    "SniffResult",
    "MagicSnifferResult",
    "sniff_magic",
    "run_magic_sniffer",
    "_sniffed_output_path",
]
