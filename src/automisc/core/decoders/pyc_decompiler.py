"""Pyc 反编译 decoder (v0.5-pyc-magic-sniffer 能力 E)

**目的**: 把 .pyc 文件反编译到 Python 源码。封装 uncompyle6 (Py2.x) + decompyle3 (Py3.x) + dis (fallback)。

**触发**: v0.5-train-009 N=NP 题 — writeup Page 4 抽出字节流是合法 Py2.7 pyc,需要 uncompyle6 反编译得到
KEY1/KEY2 才能解 flag。automisc 之前没有"反编译 .pyc"功能,Owner 手工调 uncompyle6。

**用法**:
- CLI: `automisc decode pyc_decompiler --file <path>`
- GUI: Tools 菜单 → "🐍 Pyc 反编译" (decoder 自动从 registry 渲染)
- Python: `from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler`

**反编译路由**:
1. ``xdis.load_module(path)`` → 拿 version (Py2.x / Py3.x) + magic int
2. Py2.x (magic < 3000) → ``uncompyle6.decompile_file(path, outstream)``
3. Py3.x → ``decompyle3.decompile_file(path, outstream)``
4. 不支持 / 反编译失败 → fallback 到 ``dis`` 字节码反汇编

**输出**: PycDecompileResult(input_path, source_code, method, magic_int, version, error)
- source_code: Python 源码字符串 (反编译) 或 dis 字节码 (fallback)
- method: "uncompyle6" / "decompyle3" / "dis"
- error: 反编译错误信息 (None = 成功)

**注册**: DecoderSpec(name="pyc_decompiler", display="🐍 Pyc 反编译", category="decode", ...)
GUI 自动渲染,CLI `automisc decode pyc_decompiler --file X` 自动可用。
"""
from __future__ import annotations

import dis
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from automisc.core.decoders.registry import DecoderSpec, register_decoder


@dataclass
class PycDecompileResult:
    """pyc_decompiler decoder 结果."""
    input_path: str
    raw_size: int = 0
    source_code: str = ""
    method: str = ""  # "uncompyle6" / "decompyle3" / "dis"
    magic_int: int = 0
    version: tuple = field(default_factory=tuple)  # e.g. (2, 7) / (3, 10)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.source_code)


def _decompile_with_uncompyle6(file_path: str) -> tuple[str, str]:
    """Py2.x 反编译, 返回 (source_code, method)."""
    import uncompyle6
    out = io.StringIO()
    uncompyle6.decompile_file(file_path, out)
    return out.getvalue(), "uncompyle6"


def _decompile_with_decompyle3(file_path: str) -> tuple[str, str]:
    """Py3.x 反编译, 返回 (source_code, method)."""
    import decompyle3
    out = io.StringIO()
    decompyle3.decompile_file(file_path, out)
    return out.getvalue(), "decompyle3"


def _decompile_with_dis(file_path: str, raw: bytes) -> tuple[str, str]:
    """fallback: 用 dis 反汇编字节码.

    Args:
        file_path: 原始路径 (用于错误消息)
        raw: pyc 文件原始字节
    """
    try:
        from xdis import load_module
        version, timestamp, magic_int, co, is_pypy, source_size, sip_hash = load_module(file_path)
        out = io.StringIO()
        dis.dis(co, file=out)
        header = (
            f"# dis fallback (uncompyle6/decompyle3 反编译失败)\n"
            f"# Python {version}, magic {magic_int}, timestamp {timestamp}\n"
            f"# --- bytecode disassembly ---\n\n"
        )
        return header + out.getvalue(), "dis"
    except Exception as e:
        return f"# dis fallback failed: {e}", "dis"


def run_pyc_decompiler(file_path: str) -> PycDecompileResult:
    """pyc_decompiler decoder runner (per DecoderSpec.run signature).

    Args:
        file_path: .pyc 文件路径

    Returns:
        PycDecompileResult(source_code, method, magic_int, version, error)
    """
    p = Path(file_path)
    if not p.exists():
        return PycDecompileResult(
            input_path=str(p),
            error=f"file not found: {p}",
        )

    try:
        raw = p.read_bytes()
    except Exception as e:  # noqa: BLE001
        return PycDecompileResult(
            input_path=str(p),
            error=f"failed to read: {e}",
        )

    # 用 xdis 看 magic + version
    magic_int = 0
    version: tuple = ()
    try:
        from xdis import load_module
        version, _timestamp, magic_int, _co, _is_pypy, _src_size, _sip_hash = load_module(file_path)
    except Exception as e:
        return PycDecompileResult(
            input_path=str(p),
            raw_size=len(raw),
            error=f"xdis load_module failed: {e}",
        )

    # 按 version 路由
    is_py2 = bool(version) and version[0] == 2
    is_py3 = bool(version) and version[0] == 3

    source = ""
    method = ""
    err = None

    if is_py2:
        try:
            source, method = _decompile_with_uncompyle6(file_path)
        except Exception as e:  # noqa: BLE001
            err = f"uncompyle6 failed: {e}"
    elif is_py3:
        try:
            source, method = _decompile_with_decompyle3(file_path)
        except Exception as e:  # noqa: BLE001
            err = f"decompyle3 failed: {e}"
    else:
        err = f"unsupported Python version: {version}"

    # fallback 到 dis
    if not source:
        try:
            source, method = _decompile_with_dis(file_path, raw)
            err = None  # fallback 成功就清掉 err
        except Exception as e:  # noqa: BLE001
            if err is None:
                err = f"dis fallback failed: {e}"

    return PycDecompileResult(
        input_path=str(p),
        raw_size=len(raw),
        source_code=source,
        method=method,
        magic_int=magic_int,
        version=version,
        error=err,
    )


# 注册到 decoder registry (per v0.5-decoder-menu + STRUCTURE.md §3.5)
# GUI Tools 菜单 / CLI `automisc decode pyc_decompiler` 自动从 registry 渲染
register_decoder(DecoderSpec(
    name="pyc_decompiler",
    display="🐍 Pyc 反编译",
    category="decode",  # 兼容旧 category 渲染
    group="general",  # 默认 group, 不走 cipher 解密工具分组
    cli_cmd="decode pyc_decompiler",
    run=run_pyc_decompiler,
    description=(
        "Py2.x / Py3.x pyc 反编译到 Python 源码 "
        "(uncompyle6 / decompyle3 / dis fallback; "
        "不依赖原 .py 源码, 只用字节码反推)"
    ),
    text_only=False,  # file-based, 走 file input
))


__all__ = [
    "PycDecompileResult",
    "run_pyc_decompiler",
    "_decompile_with_uncompyle6",
    "_decompile_with_decompyle3",
    "_decompile_with_dis",
]
