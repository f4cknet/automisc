"""坐标串 → 二维码 转换器 (v0.5-coords-qr).

**Owner 触发** (2026-06-14 10:16):
> "增加坐标转二维码功能, 同样增加到 GUI 工具栏中"

**真实场景** (per meihuai.jpg Owner 手工解法 · 2026-06-14 08:30):
1. strings 解 meihuai.jpg 报 4 suspicious points (3 keyword + 1 hex `28372c37290a...`)
2. Owner 手工解 hex 串:
   - `28372c37290a` -> `(7,7)`
   - `28372c38290a` -> `(7,8)`
   - ...
   - 共 N 个 hex 串 -> N 个 `(r,c)` 坐标
3. Owner 用 PIL 画 272x272 黑白图 (按坐标点黑块)
4. zbarimg 扫 -> QR flag{40fc0a979f759c8892f4dc045e28b820}

**职责**: 把第 2-3 步自动化 — 用户给坐标串, 自动渲染 QR + zbar 解码.

**输入**:
- text: hex 串 0x 逗号分隔 (e.g. "28372c37290a,28372c38290a,...") → 内部解 hex
- 或者已经解好的 `(r,c)` 列表 (e.g. "(7,7),(7,8),(7,9)")
- 或者混合: "28372c37290a,(8,9),0x0a0b..."

**输出**:
- 写 PNG 到 input 同目录 (per v0.5-output-samedir)
- zbar 识别结果 (含 flag if any)
- DecodedQRResult dataclass

**CLI**: `automisc decode coords-qr --text '<coord串>'` 或 `--file <txt>`
**GUI**: 菜单栏 [🔳 坐标 → 二维码] (text-based decoder, 跟 hex-ascii 一样从 input 区走)

macOS 依赖: zbarimg (brew install zbar, 已装 0.23.93) + Pillow (PR9 装)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from PIL import Image

from automisc.core.utils.output_path import output_path_for, text_based_output_path


# hex 字节对 pattern (e.g. "2837" -> 0x28=40='(' 不太对, 实际是 2 bytes per coord)
# meihuai.jpg 真实 hex 模式: "2837" 2c "3729" 0a (每 4 字符一对 hex byte = 2 bytes = 1 coord)
#  0x28 0x37 = '(' '7' -- 等等, 不是 ASCII
# 重新看: 实际 meihuai 的 hex 是 16 进制 4 chars = 2 bytes
#  0x28 0x37 = 40,55 = (7,7)  -> 这不对啊
# 让我算: 0x28 = 40, 0x37 = 55, 0x2c = 44, 0x37 = 55, 0x29 = 41, 0x0a = 10
#  ASCII 解: '(' '7' ',' '7' ')' '\n'
#  -> 就是 "(7,7)\n" 这个字面! Owner 手工解 hex 出 (7,7)
#  所以 hex-ascii 一次解 1 字符 ASCII, 5 chars = 1 完整 "(7,7)" + \n
#  这跟我们的坐标解析有区别 — 我们的 decoder 直接接受 "(7,7)" 形式的 list

# 1. 坐标点 pattern: (r,c) or (r, c) or r,c
#    容忍: 无括号 / 空格 / 中文逗号 / 半角逗号
_COORD_RE: Final[re.Pattern[str]] = re.compile(
    r"\(?\s*(\d+)\s*[,，]\s*(\d+)\s*\)?"
)

# 2. 4-char hex 串 pattern: "2837" 形式 (2 bytes ASCII) - 但这要预先 hex->ascii
#    实际上更好: 让 caller 传纯 text (text mode 已经在上层剥)
#    所以这里只接 "(7,7)" 形式, 不接 hex 串

# QR 尺寸推断: 给 N 个坐标, 尝试 sqrt(N) 找最接近的整数 (25 常见 for v1)
# 25x25 = 625 cells, 21x21 = 441, 29x29 = 841, 33x33 = 1089
# meihuai 真实 N=323, sqrt(323)~18, 但实际是 25x25 (272/11≈25, 像素缩放)
# 所以我们应该让 user 显式指定 size 或 推断

COMMON_QR_SIZES: Final[tuple[int, ...]] = (21, 25, 29, 33, 37, 41, 47, 53, 57, 65)


class CoordsQRDecoderError(Exception):
    """坐标→二维码 失败."""

    pass


@dataclass
class DecodedQRResult:
    """坐标→二维码 解码结果.

    Attributes:
        coords: 解析出的 (r, c) 坐标 list
        qr_size: 推断/指定的 QR 尺寸 (NxN)
        output_path: 渲染的 PNG 文件路径
        zbar_stdout: zbarimg 原始输出
        zbar_decoded: zbar 识别出的字符串 list
        flag_candidate: 识别出的 flag (e.g. "flag{...}", "KEY{...}", "CTF{...}")
        width_px: 渲染后图片宽度 (像素)
        cell_px: 每个 cell 多少像素
    """

    coords: list[tuple[int, int]]
    qr_size: int
    output_path: str
    zbar_stdout: str
    zbar_decoded: list[str] = field(default_factory=list)
    flag_candidate: str | None = None
    width_px: int = 0
    cell_px: int = 0


def _parse_coords(text: str) -> list[tuple[int, int]]:
    """从 text 解析 (r, c) 坐标 list.

    支持格式:
    - "(7,7),(7,8),(7,9)"  (紧凑)
    - "(7, 7), (7, 8)"  (带空格)
    - "7,7 7,8 7,9"  (无括号)
    - "7,7\\n7,8\\n7,9"  (每行一个)
    - "(7,7)\\n(7,8)\\n(7,9)"  (混合)
    """
    coords: list[tuple[int, int]] = []
    for m in _COORD_RE.finditer(text):
        r, c = int(m.group(1)), int(m.group(2))
        coords.append((r, c))
    if not coords:
        raise CoordsQRDecoderError(
            f"未找到任何 (r,c) 坐标; 请输入 '(7,7),(7,8),...' 形式"
        )
    return coords


def _infer_qr_size(coords: list[tuple[int, int]]) -> int:
    """推断 QR 尺寸.

    算法:
    1. 找所有 r 和 c 的 max, 取较大者 + 1
    2. 如果 max+1 ≤ 65, 直接是 QR 矩阵尺寸
    3. 如果 max+1 > 100, 像素级坐标 - 试除 21/25/29/33 看哪个整除 (e.g. 272/16=17, 272/8=34, 272/11=24.7)
       然后从剩余 candidates 里挑 cell_px 范围 5-20

    Returns:
        qr_size (int), 跟 cell_px 一起给 _render_qr_png 用
    """
    if not coords:
        raise CoordsQRDecoderError("coords 为空")
    max_r = max(r for r, _ in coords)
    max_c = max(c for _, c in coords)
    raw = max(max_r, max_c) + 1

    # 情况 1: 直接是 QR 矩阵尺寸 (raw ≤ 65)
    if raw <= 65:
        return raw

    # 情况 2: 像素级坐标 - 找 raw / candidate_size = 整数 且 cell_px 5-20
    for candidate_size in COMMON_QR_SIZES:
        if raw % candidate_size == 0:
            return candidate_size
    # 兜底: 找最接近的 (允许 ±2 误差)
    return min(COMMON_QR_SIZES, key=lambda s: abs(s - raw))


def _infer_cell_px(coords: list[tuple[int, int]], qr_size: int) -> int:
    """推断每个 cell 多少像素 (像素级坐标时用).

    默认 11 (per meihuai 272/25 ≈ 11).
    """
    if not coords or qr_size <= 0:
        return 11
    max_coord = max(max(r, c) for r, c in coords)
    if max_coord < qr_size:
        return 11  # 坐标已经是 cell 级别, 1:1
    return max(1, (max_coord + 1) // qr_size)


def _render_qr_png(
    coords: list[tuple[int, int]],
    qr_size: int,
    output_path: Path,
    cell_px: int = 11,
) -> tuple[int, int]:
    """渲染坐标为 QR PNG (黑块=坐标, 白块=空白).

    设计 (per Owner 2026-06-14 meihuai 手工解法):
    1. **像素级坐标** (raw max 272): 直接用坐标当 1 像素黑块, image 大小 = (max+1, max+1)
       - 这种坐标密集连续 (meihuai 7~271), zbar 仍然能从"密度"识别 QR
    2. **cell 索引坐标** (raw max ≤ 65): 归到 qr_size x qr_size 矩阵, 每 cell 缩放 cell_px

    Args:
        coords: (r, c) 坐标 list
        qr_size: QR 矩阵尺寸 (NxN, 21/25/29/...)
        output_path: 输出 PNG 路径
        cell_px: 每个 cell 多少像素 (默认 11, 仅 cell 索引模式用)

    Returns:
        (width_px, height_px) 实际图片尺寸
    """
    if not coords:
        raise CoordsQRDecoderError("coords 为空")

    max_coord = max(max(r, c) for r, c in coords)

    # 情况 1: 像素级坐标 (raw > qr_size) - 1 像素 1 黑块
    if max_coord >= qr_size:
        width = max_coord + 1
        img = Image.new("1", (width, width), color=1)  # 1-bit, 白底
        pixels = img.load()
        for r, c in coords:
            if 0 <= r < width and 0 <= c < width:
                pixels[c, r] = 0  # 0 = 黑
        img.save(output_path, format="PNG")
        return (width, width)

    # 情况 2: cell 索引坐标 (raw ≤ qr_size) - 缩放到 cell_px
    img = Image.new("1", (qr_size * cell_px, qr_size * cell_px), color=1)
    pixels = img.load()
    for r, c in coords:
        if 0 <= r < qr_size and 0 <= c < qr_size:
            for dy in range(cell_px):
                for dx in range(cell_px):
                    pixels[c * cell_px + dx, r * cell_px + dy] = 0
    img.save(output_path, format="PNG")
    return (qr_size * cell_px, qr_size * cell_px)


def _run_zbar(png_path: Path) -> tuple[str, list[str]]:
    """扫 PNG 拿 QR 解码结果, 返回 (stdout, decoded_lines).

    v0.5-zbar-windows-install: 改用 ZbarAdapter (pyzbar 后端) 而非 subprocess zbarimg.
    - 之前: `subprocess` 调 `zbarimg --quiet --raw` (SourceForge NSIS installer 2010 老, Win 端失效)
    - 现在: ZbarAdapter.run() 内部调 pyzbar.pyzbar.decode(PIL.Image) (Win wheel 自带 zbar DLL)
    - output 格式 1:1 兼容: stdout = 一行一条解码文本 (跟 zbarimg --raw 一样)
    """
    from automisc.tools.misc.brainteaser.zbar import ZbarAdapter
    adapter = ZbarAdapter()
    if not adapter.check_available():
        raise CoordsQRDecoderError("zbar 不可用: pyzbar 未装 (pip install pyzbar)")
    try:
        result = adapter.run(str(png_path))
    except Exception as e:
        raise CoordsQRDecoderError(f"zbar decode 失败: {type(e).__name__}: {e}")
    if not result.is_success:
        # exit 1 (UnidentifiedImageError) / 2 (file not found) / 127 (pyzbar missing)
        raise CoordsQRDecoderError(f"zbar exit {result.exit_code}: {result.stderr}")
    stdout = result.stdout.strip()
    decoded = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    return stdout, decoded


_FLAG_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:flag|ctf|key)\{[^}]+\}", re.IGNORECASE
)


def _find_flag(decoded: list[str]) -> str | None:
    """从 decoded list 找 flag 候选."""
    for line in decoded:
        m = _FLAG_RE.search(line)
        if m:
            return m.group(0)
    return None


def decode_coords_to_qr(
    text: str,
    file_path: str | None = None,
    qr_size: int | None = None,
    cell_px: int = 11,
    out_dir: str | None = None,
) -> DecodedQRResult:
    """主入口: 坐标串 → QR PNG → zbar 识别.

    Args:
        text: 坐标串 (e.g. "(7,7),(7,8),...")
        file_path: 输入文件路径 (用于决定 output_path 目录, v0.5-output-samedir)
        qr_size: 显式指定 QR 尺寸 (None = 推断)
        cell_px: 每 cell 像素数 (默认 11, 跟 meihuai 272/25 一致)
        out_dir: 显式指定输出目录 (None = /tmp 默认; 仅 text 模式生效)

    Returns:
        DecodedQRResult

    Raises:
        CoordsQRDecoderError: 解析失败
    """
    coords = _parse_coords(text)
    if qr_size is None:
        qr_size = _infer_qr_size(coords)
    # 像素级坐标时自动推断 cell_px (默认 11 仍兜底)
    actual_cell_px = _infer_cell_px(coords, qr_size) if cell_px == 11 else cell_px

    # output 路径: input 同目录 (v0.5-output-samedir) 或 /tmp (v0.5-tmp-text-mode)
    if file_path:
        out_path = output_path_for(file_path, suffix=".png", purpose="coords_qr")
    else:
        # v0.5-tmp-text-mode: text 模式没 input file, 走 /tmp
        out_path = text_based_output_path(
            suffix=".png", purpose="coords_qr", out_dir=out_dir
        )

    width, height = _render_qr_png(coords, qr_size, out_path, cell_px=actual_cell_px)
    zbar_stdout, decoded = _run_zbar(out_path)
    flag = _find_flag(decoded)

    return DecodedQRResult(
        coords=coords,
        qr_size=qr_size,
        output_path=str(out_path),
        zbar_stdout=zbar_stdout,
        zbar_decoded=decoded,
        flag_candidate=flag,
        width_px=width,
        cell_px=actual_cell_px,
    )


# ---------- v0.5-decoder-menu: 注册到 registry ----------
def _register() -> None:
    from automisc.core.decoders.registry import DecoderSpec, register_decoder

    def _runner(file_path: str | None = None, text: str | None = None, output_dir: str | None = None, **_):
        """coords-qr 跟 hex-ascii 一样是 text-based decoder.

        Args:
            file_path: 输入文件路径 (仅用于决定 output_path 目录)
            text: 坐标串 (e.g. "(7,7),(7,8),...")
            output_dir: GUI 弹 QFileDialog 选的 dir / CLI --out-dir (v0.5-tmp-text-mode)
        """
        # 解析 text 源
        if text is None and file_path is not None:
            # file 模式: 读文件当 text
            p = Path(file_path)
            if not p.exists():
                raise FileNotFoundError(f"input not found: {file_path}")
            text = p.read_text(errors="replace")
        if text is None:
            raise CoordsQRDecoderError(
                "需要 --text '(7,7),(7,8),...' 或 --file <含坐标的txt>"
            )
        return decode_coords_to_qr(text, file_path=file_path, out_dir=output_dir)

    register_decoder(
        DecoderSpec(
            name="coords-qr",
            display="🔳 坐标 → 二维码",
            category="qr",
            cli_cmd="decode coords-qr",
            run=_runner,
            description="坐标串 (r,c) → QR PNG → zbar 识别 (per v0.5-coords-qr / meihuai 场景)",
        )
    )


_register()


__all__ = [
    "COMMON_QR_SIZES",
    "CoordsQRDecoderError",
    "DecodedQRResult",
    "decode_coords_to_qr",
    "_parse_coords",
    "_infer_qr_size",
]
