"""统一输出路径工具 (v0.5-output-samedir).

**核心规则** (per Owner 2026-06-14):
> 不论是 foremost 还是 base64 转图片, 只要是有文件输出, 都把输出的文件保存到输入文件的相同目录下,
> 不要保存到其他任何目录 (e.g. /tmp).

**为什么**:
- Owner 一边分析一边需要随时打开输出文件 (Finder 拖到 zbarimg / open / unar 等) 看结果
- /tmp 是系统目录, macOS 每次重启会清掉, 路径又长, 还要 user 给权限
- 同目录方便 owner: 拖入 -> 解出 -> 自动出现在旁边 -> 直接右键打开

**用法**:
```python
from automisc.core.utils.output_path import output_path_for, output_dir_for, temp_path_for

# 持续输出 (留着的):  <input_stem>__base64.png  in input.parent
p = output_path_for("/Challenge/KEY.exe", suffix=".png", purpose="base64")

# 临时辅助 (跑完删):  <input_stem>.automisc_rar_hash.hash  in input.parent
p = temp_path_for("/Challenge/x.rar", suffix=".hash", purpose="rar_hash")
```

**命名规则**:
- 持续: `<input_stem>__<purpose>.<ext>` — 用 `__` 分隔避免与 input 重名
- 临时: `<input_stem>.automisc_<purpose>.<ext>` — 用 `.` 分隔保持"看着像 input 的临时副本"
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _sanitize(purpose: str) -> str:
    """剥 path-unsafe 字符, 避免 output_path 越界."""
    return "".join(c if (c.isalnum() or c in "_-") else "_" for c in purpose)


def _system_tmp_dirs() -> list[Path]:
    """返回系统 tmp 目录列表 (resolved 真实路径).

    macOS 上 /tmp 是符号链接 -> /private/tmp; 此外还有 /var/folders/.../T/ (per-user tmp).
    """
    candidates = [
        Path("/tmp").resolve(),
        Path("/private/tmp").resolve(),
        Path("/var/folders").resolve(),
    ]
    # 去重
    out: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def is_in_tmp(path: str | Path) -> bool:
    """判断 path 是否在系统 tmp 目录下 (resolved 比较, 避免符号链接 / 字符串误匹配).

    Returns:
        True = path 在系统 tmp 下 (e.g. /private/tmp/foo, /private/var/folders/.../T/foo)
        False = 不在 (e.g. /Challenge/KEY__base64.png, /Users/.../opencode/tmp/pytest-xxx)

    Note:
        macOS 上 /tmp 是符号链接 -> /private/tmp, 用 .resolve() 后比较.
        pytest tmp_path 在 /private/var/folders/.../T/<uuid>/, 被识别为 tmp.
        /Users/.../opencode/tmp/ 不是系统 tmp, 不识别 (避免误匹配项目根目录).
    """
    p = Path(path).resolve()
    for tmp in _system_tmp_dirs():
        try:
            p.relative_to(tmp)
            return True
        except ValueError:
            continue
    return False


def output_dir_for(input_path: str | Path) -> Path:
    """返回输入文件所在的目录 (持续输出用).

    Args:
        input_path: 输入文件路径

    Returns:
        input_path.parent (绝对路径)

    Example:
        >>> output_dir_for("/Challenge/KEY.exe")
        PosixPath('/Challenge')
    """
    return Path(input_path).parent.resolve()


def output_path_for(
    input_path: str | Path,
    suffix: str = ".bin",
    purpose: str = "output",
) -> Path:
    """生成持续输出文件路径 — 与输入同目录, 命名 `<stem>__<purpose>.<suffix>`.

    适合: base64 解出图片, foremost 提取文件, rar 解出文件, LSB 抽到 file.
    不自动删, caller 决定.

    Args:
        input_path: 输入文件路径
        suffix: 输出后缀 (含点, e.g. ".png")
        purpose: 用途标识 (e.g. "base64", "foremost", "lsb")

    Returns:
        持续 output 文件绝对路径

    Example:
        >>> output_path_for("/Challenge/KEY.exe", suffix=".png", purpose="base64")
        PosixPath('/Challenge/KEY__base64.png')
    """
    src = Path(input_path)
    p = _sanitize(purpose)
    return (src.parent / f"{src.stem}__{p}{suffix}").resolve()


def temp_path_for(
    input_path: str | Path,
    suffix: str = ".tmp",
    purpose: str = "tmp",
) -> Path:
    """生成临时辅助文件路径 — 与输入同目录, 命名 `<stem>.automisc_<purpose>.<suffix>`.

    适合: rar2john hash 文件, john wordlist, john pot.
    caller 跑完应 unlink (or 加 `--keep-tmp` flag 留).

    Args:
        input_path: 输入文件路径
        suffix: 临时文件后缀 (含点, e.g. ".hash")
        purpose: 用途标识 (e.g. "rar_hash", "john_wordlist")

    Returns:
        临时文件绝对路径

    Example:
        >>> temp_path_for("/Challenge/x.rar", suffix=".hash", purpose="rar_hash")
        PosixPath('/Challenge/x.automisc_rar_hash.hash')
    """
    src = Path(input_path)
    p = _sanitize(purpose)
    return (src.parent / f"{src.stem}.automisc_{p}{suffix}").resolve()


def extract_dir_for(
    input_path: str | Path,
    purpose: str = "extract",
) -> Path:
    """生成提取目录路径 — 与输入同目录, 命名 `<stem>__<purpose>`.

    适合: foremost 一次提取 N 个文件, unrar 解出多个文件.
    caller 决定删/留.

    Args:
        input_path: 输入文件路径
        purpose: 用途标识 (e.g. "foremost", "bruteforced", "extracted")

    Returns:
        提取目录绝对路径

    Example:
        >>> extract_dir_for("/Challenge/KEY.exe", purpose="foremost")
        PosixPath('/Challenge/KEY__foremost')
    """
    src = Path(input_path)
    p = _sanitize(purpose)
    return (src.parent / f"{src.stem}__{p}").resolve()


# v0.5-tmp-text-mode (2026-06-14 12:08 per Owner):
# Text 模式 (用户粘在 input 区 / --text) 没有"输入文件"概念,
# 强制 samedir 会写到无关目录 (e.g. meihuai.jpg 同目录, 但坐标串跟 meihuai 无关)
# 改成默认 /tmp, file 模式仍 samedir
#
# v0.5-hex-router-samedir (2026-06-14 14:24 per Owner):
# Owner 反馈: tempfile.gettempdir() 在 macOS 返回 /private/var/folders/.../T/,
# 不是用户期望的 /tmp. 改用 Path("/tmp") (macOS 系统 tmp, symlink-resolved).
TEXT_BASED_TMP_DIR: Final[Path] = Path("/tmp") / "automisc_text_outputs"


def text_based_output_path(
    suffix: str = ".bin",
    purpose: str = "output",
    out_dir: str | Path | None = None,
) -> Path:
    """text 模式输出文件路径 (v0.5-tmp-text-mode).

    当用户输入是文本 (粘在 input 区 / CLI --text) 时, 没有"输入文件"概念,
    用此 helper 生成路径. 优先级:
    1. out_dir 显式指定 (GUI QFileDialog 选的, 或 CLI --out-dir) -> 用之
    2. 默认 -> /tmp/automisc_text_outputs/<purpose>_<rand>.<suffix>

    Args:
        suffix: 输出后缀 (含点, e.g. ".png")
        purpose: 用途标识 (e.g. "coords_qr", "base64")
        out_dir: 显式指定输出目录 (None = /tmp 默认)

    Returns:
        输出文件绝对路径
    """
    import time
    import secrets
    p = _sanitize(purpose)
    if out_dir:
        target_dir = Path(out_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f"{p}_{int(time.time())}_{secrets.token_hex(4)}{suffix}"
        return target_dir / name
    # 默认 /tmp
    TEXT_BASED_TMP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{p}_{int(time.time())}_{secrets.token_hex(4)}{suffix}"
    return TEXT_BASED_TMP_DIR / name


__all__ = [
    "TEXT_BASED_TMP_DIR",
    "extract_dir_for",
    "is_in_tmp",
    "output_dir_for",
    "output_path_for",
    "temp_path_for",
    "text_based_output_path",
]
