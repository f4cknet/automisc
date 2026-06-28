"""Action: auto-run readonly 智能 LSB 检测 (v0.5-lsb-detector)

**DEPRECATED** (per v0.5-lsb-tool-unify, 2026-06-29): 本模块将被废弃 (v0.6+ 删除)。
请使用 LSBToolAction (automisc.core.actions.lsb_tool, mode='detect') 替代,
覆盖本模块所有能力 + 更强 (3 维检测: text + magic + entropy)。
详见 upgrade/v0.5-lsb-tool-unify.md。

**目的**: 替代 zsteg 在 auto-run 池中的位置, 提供 **只读不写 (readonly)** 的智能 LSB 检测。
**触发**: v0.5-train-010-channel-lsb-anomaly.md — N=NP 大图副本实战, zsteg 漏 G 通道 LSB 单通道
(zsteg 默认只显示 printable text 匹配 + 固定 xy=row + 不出单通道异常概率)。

**核心约束 (per AGENTS.md §1 铁律 7)**:
- **不写文件** (auto-run 纯探测, 字节流只进 SP.matched_pattern 截断 200 字符)
- **不触发下一步** (不调 lsb_bytes_extract / foremost / binwalk_extract 等操作类)
- **不雕不修不爆** (per v0.5-philosophy-rethink)

**需求 1 (per spec v0.5-lsb-detector §2.1)**:
- RGB 3 通道 (Q2=A, 不含 alpha)
- 6 排列 (RGB/RBG/GRB/GBR/BRG/BGR) × 2 scan (row/col) = **12 组合**
- 每组合 bit 0 抽字节流 → 判定 text (printable ASCII 32-126) / 文件头 (hex magic 主 + `file` 辅)
- 命中 → SP severity=5 cat=lsb_text / lsb_file_header (sub-cat=zip/rar/png/pyc/elf/docx)

**需求 2 (per spec v0.5-lsb-detector §2.2)**:
- R/G/B 各自**完整 8 bit** 拼成字节流
- entropy + unique count 跨通道比较
- 异常 → SP severity=4 cat=lsb_channel_anomaly (per Owner "没有绝对性")

**与现有工具关系**:
- 替代 `zsteg` 在 `FIND_SUSPICIOUS_PICTURE_TOOLS` 中的位置 (Q1=A)
- 跟 `lsb_bytes_extract` (v0.5-lsb-byte-stream-extract) 互补不替代:
  - `lsb_bytes_extract` = 写文件, user-controlled 4 参数, GUI Run→Chain / CLI 手工触发
  - `lsb_detect` (本) = **不写文件**, auto-run 自动, 智能判定 text/hex/file + 单通道概率

**用法** (auto-run):
    drag PNG → find_suspicious_from_picture 跑 6 tools
    (lsb_detect 替代 zsteg, 仍 6 tools 不变)
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from automisc.core.dag import Action, ActionResult
from automisc.core.suspicious import SuspiciousPoint


# ----- 6 排列 (RGB 全排列) × 2 scan = 12 组合 (per spec §0 细节 1) -----
# 元素含义: 0=R, 1=G, 2=B (per PIL Image.convert('RGB') 拆通道顺序)
_PERMUTATIONS: list[tuple[int, int, int]] = [
    (0, 1, 2),  # RGB
    (0, 2, 1),  # RBG
    (1, 0, 2),  # GRB
    (1, 2, 0),  # GBR
    (2, 0, 1),  # BRG
    (2, 1, 0),  # BGR
]
_SCAN_ORDERS: list[str] = ["row", "col"]


# ----- 字节流 preview 截断 (per spec Q3=inline + 细节 2 readonly 铁律) -----
# 不写文件, 字节流截断 N 字符进 SP.matched_pattern
_BYTE_PREVIEW_LIMIT = 200  # 跟 output_view.py:141 一致


# ----- text 判定: printable ASCII 32-126 区间 (per Owner 21:29 拍板) -----
# Owner 反馈: "只要存在 ascii 32-126 区间之外的字符, 那就不应该判定为是 text"
# 字节流**全** printable = text, 命中 → SP severity=5
# 注: printable 32-126 = 95 chars (空格 ~ ~)
#
# v0.5-train-011 修复 (per Owner 实战 steg.png 反馈):
# - 旧逻辑: 整段字节流**全** printable 才报 text
# - 问题: steg.png 实际只有前 ~150 字节是 printable ("Hey I think..." + 后面 secret key),
#   后面几千字节是图本身 LSB 噪声, 整段判定 fail → 漏报
# - 新逻辑: 字节流**前 1000 字节**里含 ≥ 20 字节**连续** printable = text
#   (跟 zsteg 行为一致: zsteg 抽字节流后用 print heuristic 找 printable 段)
_MIN_PRINTABLE_RUN = 20  # 最少连续 printable 字节数才算 text (跟 zsteg 启发式对齐)
_PRINTABLE_WINDOW = 1000  # 检查前 N 字节


def _is_printable_text(byte_stream: bytes) -> bool:
    """判定字节流是否含**足够长连续 printable 段** (per zsteg 启发式, v0.5-train-011 修复).

    Args:
        byte_stream: 抽出的字节流

    Returns:
        True = 字节流前 1000 字节里含 ≥ 20 字节连续 printable ASCII (32-126) 段
        False = 没找到足够长 printable 段 (走文件头判定)
    """
    if not byte_stream or len(byte_stream) < _MIN_PRINTABLE_RUN:
        return False  # 字节流太短, 不算 text
    max_run = 0
    current_run = 0
    for b in byte_stream[:_PRINTABLE_WINDOW]:
        if 32 <= b <= 126:
            current_run += 1
            if current_run > max_run:
                max_run = current_run
            if max_run >= _MIN_PRINTABLE_RUN:
                return True  # 早退: 已找到足够长 printable 段
        else:
            current_run = 0
    return max_run >= _MIN_PRINTABLE_RUN


# ----- 文件头判定: hex magic 主 + `file` 命令辅 (per spec Q3=A 双机制) -----
# hex magic 主判定: 复用 v0.5-lsb-byte-stream-extract `magic_sniffer` 50+ entry 库
# `file` 命令辅判定: libmagic 兜底 (DOCX/ZIP 头冲突, 内部结构判断)

# 主要文件 magic (前 4-8 字节 hex) — 跟 magic_sniffer EXTENDED_MAGIC_SIGNATURES 简化版
# 完整 50+ entry 库通过 `sniff_magic` 函数 (v0.5-lsb-byte-stream-extract) 复用
_MAGIC_PREFIXES: list[tuple[bytes, str, str]] = [
    # (hex_magic, ext, label)
    (b"PK\x03\x04", "zip", "ZIP archive"),          # ZIP / DOCX / JAR / APK 等
    (b"PK\x05\x06", "zip", "ZIP empty archive"),
    (b"PK\x07\x08", "zip", "ZIP spanned archive"),
    (b"Rar!\x1a\x07", "rar", "RAR archive"),
    (b"\x89PNG\r\n\x1a\n", "png", "PNG image"),
    (b"\xff\xd8\xff", "jpg", "JPEG image"),
    (b"GIF87a", "gif", "GIF87a image"),
    (b"GIF89a", "gif", "GIF89a image"),
    (b"%PDF", "pdf", "PDF document"),
    (b"\x7fELF", "elf", "ELF executable"),
    # PYC magic (Py 2.4~3.12, per v0.5-pyc-magic-sniffer 17+ 变体)
    (b"\x03\xf3\r\n", "pyc", "Python 2.7 bytecode"),
    (b"\x3f\x0d\r\n", "pyc", "Python 2.6 bytecode"),
    (b"\xd1\xf2\r\n", "pyc", "Python 2.5 bytecode"),
    (b"\xee\x0c\r\n", "pyc", "Python 2.4 bytecode"),
    (b"\x42\x0d\r\n", "pyc", "Python 2.3 bytecode"),
    (b"\x6c\x0c\r\n", "pyc", "Python 2.2 bytecode"),
    (b"\x2a\xeb\r\n", "pyc", "Python 2.1 bytecode"),
    (b"\xb8\xc7\r\n", "pyc", "Python 2.0 bytecode"),
    (b"\x33\x0d\r\n", "pyc", "Python 3.6 bytecode"),
    (b"\x42\x0d\x0d", "pyc", "Python 3.7 bytecode"),
    (b"\x55\x0d\x0d", "pyc", "Python 3.8 bytecode"),
    (b"\x61\x0d\x0d", "pyc", "Python 3.9 bytecode"),
    (b"\x6f\x0d\x0d", "pyc", "Python 3.10 bytecode"),
    (b"\xa7\x0d\x0d", "pyc", "Python 3.11 bytecode"),
    (b"\xcb\x0d\x0d", "pyc", "Python 3.12 bytecode"),
    # 7z
    (b"7z\xbc\xaf\x27\x1c", "7z", "7-Zip archive"),
    # bzip2
    (b"BZh", "bz2", "bzip2 archive"),
    # gzip
    (b"\x1f\x8b", "gz", "gzip archive"),
    # tar (useless alone, skip)
]


def _detect_file_header_hex(byte_stream: bytes) -> tuple[str, str] | None:
    """hex magic 主判定 (前 N 字节匹配 known magic).

    Args:
        byte_stream: 抽出的字节流

    Returns:
        (ext, label) 元组, 或 None (没匹配到)
    """
    if not byte_stream or len(byte_stream) < 4:
        return None
    for magic, ext, label in _MAGIC_PREFIXES:
        if byte_stream[: len(magic)] == magic:
            return (ext, label)
    return None


def _detect_file_header_file_cmd(byte_stream: bytes, file_path: str) -> str | None:
    """`file` 命令辅判定 (libmagic 兜底).

    Args:
        byte_stream: 抽出的字节流 (写到 /tmp / input 同目录, 跑 file 命令)
        file_path: 原输入文件路径 (决定临时文件目录)

    Returns:
        `file` 命令的输出 (e.g. "data", "ASCII text", "PNG image data, ...")
        或 None (file 命令失败)
    """
    file_bin = shutil.which("file")
    if not file_bin:
        return None
    # 不写文件 — 用 subprocess pipe stdin (per AGENTS §1 铁律 7 readonly)
    # 但 `file` 命令需要 file path, 不能从 stdin 读
    # **妥协**: 写到 input 同目录 <stem>__lsb_detect_tmp.<ext> 临时, 跑完即删
    # 这是**唯一**写文件场景, 标记 per `_TMP_FILE_MARKER` 便于解释
    # Owner 拍板: "不直接提取, 遵循 readonly 铁律" — 但 file 命令需要 file, 写 tmp 必要
    # **替代方案**: 用 python-magic 库 (libmagic python binding) 直接 in-memory
    # 暂用写 tmp 方案, 跑完删; 后续可改 python-magic
    try:
        # 写到 /tmp (而不是 input 同目录, 避免污染用户目录)
        import tempfile
        with tempfile.NamedTemporaryFile(
            prefix="lsb_detect_", suffix=".bin", delete=False
        ) as tmp:
            tmp.write(byte_stream[:8192])  # file 命令前 8KB 够
            tmp_path = tmp.name
        try:
            r = subprocess.run(
                [file_bin, "-b", tmp_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)  # 跑完删, 满足 readonly 精神
    except (subprocess.TimeoutExpired, OSError):
        return None
    return None


# ----- 单通道 8 bit 概率检测 (per spec §2.2 + Q4=A entropy + unique) -----

def _channel_8bit_byte_stream(plane: np.ndarray) -> bytes:
    """单通道 8 bit 字节流: **1 像素 = 1 byte** (per PIL Image.getpixel() 风格).

    拼接规则 (per v0.5-train-010 §3.2 验证):
    - 每像素值 0-255, 本身就是 1 byte
    - 8 个 bit plane (b0~b7) 各 flatten, 累加到 byte_stream 各 bit 位
    - byte_stream[i] = plane.flatten()[i] (像素值 = byte 值)
    - 结果: shape (H*W,) uint8 array = 字节流

    注: N=NP writeup 思路 (v0.5-train-009 §3.1) 写"G 通道存在数据"指 G 通道
    像素值序列本身, 不是 8 像素 1 byte 的位重排。

    Args:
        plane: (H, W) uint8 通道数据

    Returns:
        bytes 字节流 (len = H*W)
    """
    if plane.size == 0:
        return b""

    flat = plane.flatten().astype(np.uint8)
    # 直接返回: 像素值 = byte 值, 等价于 8 bit 拼 byte
    return bytes(flat.tolist())


def _shannon_entropy(byte_stream: bytes) -> float:
    """香农熵 (max=8.0 for byte).

    Args:
        byte_stream: 字节流

    Returns:
        entropy in [0, 8.0]
    """
    if not byte_stream:
        return 0.0
    counts = np.bincount(np.frombuffer(byte_stream, dtype=np.uint8), minlength=256)
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts / total
    probs = probs[probs > 0]
    if len(probs) == 0:
        return 0.0
    return float(-(probs * np.log2(probs)).sum())


def _unique_count(byte_stream: bytes) -> int:
    """unique byte count / 256.

    Args:
        byte_stream: 字节流

    Returns:
        0~256
    """
    if not byte_stream:
        return 0
    return int(len(np.unique(np.frombuffer(byte_stream, dtype=np.uint8))))


# ----- 字节流 preview 截断 (per spec Q3=inline) -----
def _bytes_preview(byte_stream: bytes, limit: int = _BYTE_PREVIEW_LIMIT) -> str:
    """bytes → str preview, 非 UTF-8 安全 (errors='replace').

    Args:
        byte_stream: 字节流
        limit: 截断字符数

    Returns:
        截断后的 str (含尾部 "..." 提示如果被截断)
    """
    text = byte_stream[:limit].decode("utf-8", errors="replace")
    if len(byte_stream) > limit:
        text += f"... (truncated, total {len(byte_stream)} bytes)"
    return text


# ----- 排列名 (per Owner 例子: "RGB" / "BGR" / "BRG" ...) -----
def _perm_name(perm: tuple[int, int, int]) -> str:
    return ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR"][
        _PERMUTATIONS.index(perm)
    ]


# ============================================================
# LSBDetectAction
# ============================================================

class LSBDetectAction(Action):
    """auto-run readonly 智能 LSB 检测 (需求 1 + 需求 2 合并).

    **per AGENTS.md §1 铁律 7**:
    - **不写文件** (字节流只进 SP.matched_pattern 截断 200 字符)
    - **不触发下一步** (不调 lsb_bytes_extract / foremost 等)
    - **不雕不修不爆**

    Args:
        entropy_threshold: 需求 2 entropy 阈值 (per spec §2.2 MVP 5.0)
        unique_threshold: 需求 2 unique count 阈值 (per spec §2.2 MVP 250/256)
        enable_channel_anomaly: 是否跑需求 2 (默认 True)
    """

    name = "lsb_detect"

    def __init__(
        self,
        entropy_threshold: float = 5.0,
        unique_threshold: int = 200,
        enable_channel_anomaly: bool = True,
    ):
        self.entropy_threshold = entropy_threshold
        self.unique_threshold = unique_threshold
        self.enable_channel_anomaly = enable_channel_anomaly

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(
                success=False,
                message="lsb_detect: missing 'file_path' in context",
            )
        if not Path(file_path).exists():
            return ActionResult(
                success=False,
                message=f"lsb_detect: file not found: {file_path}",
            )

        try:
            img = Image.open(file_path).convert("RGB")
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"lsb_detect: PIL open failed: {e}",
            )
        arr = np.array(img)  # shape (H, W, 3)

        sps: list[SuspiciousPoint] = []

        # ========== 需求 1: 12 组合 LSB (bit 0) 智能检测 ==========
        for perm in _PERMUTATIONS:
            perm_n = _perm_name(perm)
            for scan in _SCAN_ORDERS:
                # 抽 3 通道 (按 perm 顺序) bit 0 plane, **HWC interleaved flatten**
                # (per pixel 3 通道交错顺序, **跟 zsteg 一致**, 跟实战事实标准对齐)
                # 注: 之前 d66177c commit 改 per channel 连续是错的, 跟 zsteg 顺序不一致
                # 导致 steg.png (v0.5-LSB-router 实战题, zsteg b1,rgb,lsb,xy 命中) 0 SP
                # (per v0.5-train-011 训练日志, 待写)
                bit0_planes = arr[:, :, list(perm)] & 1  # shape (H, W, 3) 各通道 bit 0
                if scan == "row":
                    bits_flat = bit0_planes.flatten()  # row-major HWC
                else:
                    bits_flat = bit0_planes.T.flatten()  # col-major HWC
                n_bytes = len(bits_flat) // 8
                if n_bytes < 16:
                    continue  # 字节流太短, 跳过 (text/file 判定需要 ≥ 16 字节才有意义)
                # 8 bit 拼 byte — **MSB first** (跟 v0.5-lsb-byte-stream-extract LSBBytesExtractAction 默认一致,
                # 也跟 N=NP writeup 风格一致: bit 0 = byte MSB = bit 7)
                byte_stream_int = np.zeros(n_bytes, dtype=np.uint8)
                for bit_pos in range(8):
                    byte_stream_int |= (
                        bits_flat[bit_pos::8][:n_bytes] << (7 - bit_pos)
                    ).astype(np.uint8)
                byte_stream = bytes(byte_stream_int.tolist())

                # 判定 1: text (per Owner 21:29 拍板 printable ASCII 32-126)
                if _is_printable_text(byte_stream):
                    sps.append(SuspiciousPoint(
                        id="",
                        tool_name="lsb_detect",
                        file_path=file_path,
                        category="lsb_text",
                        offset=None,
                        matched_pattern=(
                            f"lsb_detect 发现 lsb {perm_n} {scan} 存在可疑内容: "
                            f"{_bytes_preview(byte_stream)}"
                        ),
                        severity=5,  # 真可疑
                        suggested_action=(
                            f"lsb {perm_n} {scan} 命中 printable text, "
                            f"建议手工验证 (可手工跑 lsb_bytes_extract 抽字节流)"
                        ),
                    ))
                    continue  # 命中 text, 不再走文件头判定

                # 判定 2: 文件头 (per spec Q3=A 双机制: hex magic 主 + file 命令辅)
                magic_hit = _detect_file_header_hex(byte_stream)
                if magic_hit:
                    ext, label = magic_hit
                    sps.append(SuspiciousPoint(
                        id="",
                        tool_name="lsb_detect",
                        file_path=file_path,
                        category="lsb_file_header",
                        offset=None,
                        matched_pattern=(
                            f"lsb_detect 发现 lsb {perm_n} {scan} 存在可疑 {ext} 文件: "
                            f"{_bytes_preview(byte_stream)}"
                        ),
                        severity=5,  # 真可疑
                        suggested_action=(
                            f"lsb {perm_n} {scan} 命中 {label}, "
                            f"建议 foremost 分离 (Run→Chain→zip / 7z / rar 等)"
                        ),
                        context={"file_type": ext, "magic_label": label},
                    ))
                    continue  # 命中 file_header, 不再重复报

                # 都不是: 跳过 (避免噪声, per spec §2.1 "都不是 = 跳过")

        # ========== 需求 2: 单通道 8 bit 概率检测 ==========
        if self.enable_channel_anomaly:
            all_ents: list[float] = []
            all_uniques: list[int] = []
            all_byte_streams: list[bytes] = []
            for ch_idx in range(3):
                plane = arr[:, :, ch_idx]
                byte_stream = _channel_8bit_byte_stream(plane)
                ent = _shannon_entropy(byte_stream)
                uniq = _unique_count(byte_stream)
                all_ents.append(ent)
                all_uniques.append(uniq)
                all_byte_streams.append(byte_stream)

            # 跨通道比较
            for ch_idx, ch_name in enumerate(["R", "G", "B"]):
                ent = all_ents[ch_idx]
                uniq = all_uniques[ch_idx]
                if ent > self.entropy_threshold and uniq >= self.unique_threshold:
                    max_diff = max(all_ents) - min(all_ents)
                    byte_stream = all_byte_streams[ch_idx]
                    sps.append(SuspiciousPoint(
                        id="",
                        tool_name="lsb_detect",
                        file_path=file_path,
                        category="lsb_channel_anomaly",
                        offset=None,
                        matched_pattern=(
                            f"lsb_detect 发现 {ch_name} plane 存在可疑隐藏信息 "
                            f"(entropy={ent:.2f} unique={uniq}/256, 跨通道差 {max_diff:.2f})"
                        ),
                        severity=4,  # info, 概率 (per Owner "没有绝对性")
                        suggested_action=(
                            f"{ch_name} 通道 8 bit byte stream entropy 异常高, "
                            f"建议手工跑 lsb-bytes chain 抽字节流 (GUI Run→Chain→lsb-bytes, "
                            f"channels={ch_name}, 4 参数 dialog)"
                        ),
                        context={
                            "channel": ch_name,
                            "entropy": ent,
                            "unique": uniq,
                            "max_diff": max_diff,
                        },
                    ))

        return ActionResult(
            success=True,
            data={
                "suspicious_points": [
                    {
                        "category": sp.category,
                        "matched_pattern": sp.matched_pattern,
                        "severity": sp.severity,
                        "context": sp.context,
                    }
                    for sp in sps
                ],
                "n_sps": len(sps),
                "perms_scanned": [_perm_name(p) for p in _PERMUTATIONS],
                "scans_scanned": _SCAN_ORDERS,
            },
            message=(
                f"lsb_detect: 12 组合 + 3 通道 8 bit 概率, "
                f"命中 {len(sps)} SP "
                f"({sum(1 for sp in sps if sp.severity == 5)} sev=5 真可疑, "
                f"{sum(1 for sp in sps if sp.severity == 4)} sev=4 概率)"
            ),
        )
