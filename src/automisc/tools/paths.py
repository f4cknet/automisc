"""Cross-platform binary path resolution (per v0.5-platform-extend-tools governance change).

v0.5 之前 (macOS only per AGENTS.md §2.3):
    subprocess 走 PATH (Homebrew 装在 /usr/local/bin 或 /opt/homebrew/bin)

v0.5+ (multi-platform per AGENTS.md §2.3 v3.2):
    resolve_tool_binary(name) -> str | None
    1) 先查 PATH (macOS Homebrew / Windows 系统 PATH)
    2) fallback extend-tools/bin/<platform>/<name>{.exe} (Windows 下 manifest.yaml 自动装的 binary)

返回 None 时, subprocess.run 自然 FileNotFoundError, _run_subprocess 兜底返回 exit 127.

不缓存: 每次调用都重新查 (PATH 可能装新工具, install.ps1 刚跑完想立即生效).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


# Project root = extend-tools/ 的父目录
# tools/paths.py 在 src/automisc/tools/ 下, parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
EXTEND_TOOLS_DIR = _REPO_ROOT / "extend-tools"
EXTEND_TOOLS_BIN_DIR = EXTEND_TOOLS_DIR / "bin"
EXTEND_TOOLS_MANIFEST = EXTEND_TOOLS_DIR / "manifest.yaml"

# Platform -> extend-tools/bin/ 子目录名
_PLATFORM_DIR = {
    "win32": "win-x64",
    "darwin": "macos",
    "linux": "linux-x64",
}.get(sys.platform, "unknown")


def platform_subdir() -> str:
    """Return the extend-tools/bin/ subdirectory for current platform.

    Returns:
        "win-x64" / "macos" / "linux-x64" / "unknown"
    """
    return _PLATFORM_DIR


def exe_suffix() -> str:
    """Return ".exe" on Windows, empty string on other platforms."""
    return ".exe" if sys.platform == "win32" else ""


def extend_tools_bin_dir() -> Path | None:
    """Return the full extend-tools/bin/<platform>/ path (or None if unknown platform)."""
    if _PLATFORM_DIR == "unknown":
        return None
    return EXTEND_TOOLS_BIN_DIR / _PLATFORM_DIR


def resolve_tool_binary(name: str) -> str | None:
    """Resolve the absolute path to an external tool binary.

    Lookup order:
    1. PATH (shutil.which) — macOS Homebrew / Windows system PATH
    2. extend-tools/bin/<platform>/<name>.exe (Windows fallback)

    Args:
        name: tool name (e.g. "binwalk" / "exiftool" / "tshark").

    Returns:
        Absolute path as string, or None if not found.
    """
    # 1) PATH first
    found = shutil.which(name)
    if found:
        return found

    # 2) extend-tools fallback
    bindir = extend_tools_bin_dir()
    if bindir is None:
        return None
    candidate = bindir / f"{name}{exe_suffix()}"
    if candidate.exists():
        return str(candidate)
    return None


def list_extend_tools() -> list[str]:
    """List all tool binary names available in extend-tools/bin/<platform>/.

    Useful for diagnostics / `automisc tools list --source extend-tools`.
    """
    bindir = extend_tools_bin_dir()
    if bindir is None or not bindir.exists():
        return []
    return sorted(p.stem for p in bindir.iterdir() if p.is_file() and not p.name.startswith("."))


__all__ = [
    "EXTEND_TOOLS_DIR",
    "EXTEND_TOOLS_BIN_DIR",
    "EXTEND_TOOLS_MANIFEST",
    "platform_subdir",
    "exe_suffix",
    "extend_tools_bin_dir",
    "resolve_tool_binary",
    "list_extend_tools",
]