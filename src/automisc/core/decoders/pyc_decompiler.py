"""Pyc 反编译 decoder (v0.5-pyc-magic-sniffer 能力 E)

**目的**: 把 .pyc 文件反编译到 Python 源码。封装 uncompyle6 (Py2.x) + decompyle3 (Py3.x) + dis (fallback)。

**触发**: v0.5-train-009 N=NP 题 — writeup Page 4 抽出字节流是合法 Py2.7 pyc,需要 uncompyle6 反编译得到
KEY1/KEY2 才能解 flag。automisc 之前没有"反编译 .pyc"功能,Owner 手工调 uncompyle6。

**v0.5-pyc-decompiler-buttons (2026-07-01 per Owner)**:
- 加 `force_version` (None/2/3) 路由参数, GUI 工具栏新增 2 强制版本按钮
- 加 `write_output=True` + `output_dir=None`, 反编译成功写 `<stem>__pyc[_pyN].py` 到 pyc 同目录
  (复用 v0.5-output-samedir `output_path_for` helper, 跟 base64-image / coords-qr 风格一致)
- `PycDecompileResult` 加 `output_path` 字段 (写盘后的 .py 路径, None=没写)
- `success` property 改为"写盘后才算 success" (per Owner "反编译成功后输出")

**用法**:
- CLI: `automisc decode pyc_decompiler --file <path>`
- GUI: Tools 菜单 → "🐍 Pyc 反编译" (3 按钮: 自动 / 强制 py2 / 强制 py3)
- Python: `from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler`

**反编译路由** (per v0.5-pyc-decompiler-buttons):
1. ``xdis.load_module(path)`` → 拿 version (Py2.x / Py3.x) + magic int
2. `force_version=2` → ``uncompyle6.decompile_file(path, outstream)`` (强制, 跳过 magic)
3. `force_version=3` → ``decompyle3.decompile_file(path, outstream)`` (强制, 跳过 magic)
4. `force_version=None` → 按 magic 自动判断: Py2.x (magic < 3000) → uncompyle6; Py3.x → decompyle3
5. 不支持 / 反编译失败 → fallback 到 ``dis`` 字节码反汇编 (不写盘, per Owner "成功后输出")

**输出**: PycDecompileResult(input_path, source_code, method, magic_int, version, error, force_version, output_path)
- source_code: Python 源码字符串 (反编译) 或 dis 字节码 (fallback)
- method: "uncompyle6" / "decompyle3" / "dis"
- error: 反编译错误信息 (None = 成功)
- force_version: 实际 force 的版本 (None=auto / 2 / 3)
- output_path: 写盘后的 .py 路径 (None=没写, 反编译失败不写 per Owner)

**注册**: DecoderSpec(name="pyc_decompiler", display="🐍 Pyc 反编译", category="decode", ...)
GUI 自动渲染,CLI `automisc decode pyc_decompiler --file X` 自动可用。
"""
from __future__ import annotations

import dis
import io
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from automisc.core.decoders.registry import DecoderSpec, register_decoder
from automisc.core.utils.output_path import output_path_for


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
    # v0.5-pyc-decompiler-buttons 新增字段
    force_version: Optional[int] = None  # 实际 force 的版本 (None = auto)
    output_path: Optional[str] = None  # 写盘后的 .py 路径 (None = 没写, 反编译失败或 write_output=False)

    @property
    def success(self) -> bool:
        """成功 = 反编译出源码 AND 写盘成功 (per Owner "反编译成功后输出 py 文件").

        Returns:
            True: 写盘了 .py (output_path 非空 + error 为 None)
            False: 没写盘 (反编译失败 / dis fallback / write_output=False)
        """
        return self.output_path is not None and self.error is None


def _decompile_with_uncompyle6(file_path: str) -> tuple[str, str]:
    """Py2.x 反编译, 返回 (source_code, method).

    fix_pyc_uncompyle6_consts_bug (per 2026-07-01 Owner 反馈): 反编译后调
    `_fix_uncompyle6_consts_bug` 修 Py2.7 顶层 consts 列表 bug (uncompyle6 把
    consts 索引当值输出, 真实字符串要去 xdis co.co_consts 查).
    """
    import uncompyle6
    out = io.StringIO()
    uncompyle6.decompile_file(file_path, out)
    skeleton = out.getvalue()
    # 修 bug (per 实战 flag.pyc 命中, 2026-07-01 xdis inspect 验证 100% 匹配)
    fixed = _fix_uncompyle6_consts_bug(skeleton, file_path)
    return fixed, "uncompyle6"


def _decompile_with_pycdc(file_path: str) -> tuple[str, str]:
    """Py2.x 反编译 (v0.5-pyc-decompiler-pycdc), 走 pycdc C++ 反编译器.

    **优先于 uncompyle6** (per Owner 2026-07-01 10:08 拍板 B 方案):
    - pycdc 是 C++ 写的 Decompyle++ (zrax/pycdc), 独立实现
    - 不依赖 uncompyle6 的 Py3 解析路径, 实战 Py2.7 准确率显著高于 uncompyle6
    - 解决 uncompyle6 已知 bug: consts 索引 / lambda / closure / yield / 复杂控制流

    Args:
        file_path: .pyc 文件路径

    Returns:
        (source_code, "pycdc") - 成功
        ("", "pycdc") - 失败 (binary 缺失 / subprocess 失败 / timeout)
                          让 caller fallback 到 uncompyle6+fix
    """
    from automisc.tools.paths import resolve_tool_binary
    pycdc = resolve_tool_binary("pycdc")
    if not pycdc:
        # binary 缺失 (extend-tools 没装 / PATH 也没) → fallback
        return "", "pycdc"
    try:
        result = subprocess.run(
            [pycdc, file_path],
            capture_output=True,
            text=True,
            timeout=30,  # 30s 防止复杂 pyc 卡死
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout, "pycdc"
        # returncode != 0 / 空输出 → 失败
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # subprocess 异常 (timeout / binary 突然消失 / 权限) → 失败
        pass
    return "", "pycdc"


# 顶层 "var = [N, N, N, ...]" 模式 (只含 int, 没字符串)
# uncompyle6 bug 触发的特征: 列表元素全在 [0, N-1] 范围 (consts 索引)
_TOP_LEVEL_INT_LIST_RE = re.compile(
    r"^(\w+)\s*=\s*\[\s*((?:\d+\s*,\s*)*\d+)\s*\]\s*$",
    re.MULTILINE,
)
# 末尾独立行 "return" (module-level 伪 artifact, uncompyle6 Py2.7 已知 issue)
_TRAILING_RETURN_RE = re.compile(r"^return\s*$", re.MULTILINE)


def _fix_uncompyle6_consts_bug(skeleton: str, file_path: str) -> str:
    """修 uncompyle6 Py2.7 顶层 consts 列表反编译 bug (fix_pyc_uncompyle6_consts_bug).

    **bug 现象** (per v0.5-train-019 实战 + 2026-07-01 Owner 反馈):
    - uncompyle6 把 `ciphertext = ['96', '65', ...]` 反编译成 `ciphertext = [3, 4, 5, ...]`
    - 输出是 `co_consts` 索引, 真实字符串要去 `co.co_consts` 查
    - 末尾还多 `return` (module-level 伪 artifact)

    **根因** (per 2026-07-01 xdis inspect):
    - uncompyle6 Py2.7 module-level LOAD_CONST 反汇编 bug
    - 修复: xdis `co.co_consts` 含真实字符串, 按 LOAD_CONST 顺序还原

    **修法**:
    1. xdis 拿 co.co_consts (顶层 code object 的真实 consts)
    2. 正则解析 skeleton 里 "var = [N, N, N, ...]" 模式 (顶层 module-level)
    3. 对每个匹配: 查 co_consts[N] 拿真实值
    4. 全是 str → 替换成 'val1', 'val2', ... (单引号 per Python 2 repr)
    5. 末尾 `return` 去掉 (独立行)

    Args:
        skeleton: uncompyle6 反编译输出 (含 bug 的源码)
        file_path: pyc 文件路径 (供 xdis load_module 读 code object)

    Returns:
        修后 source code (跟 online 工具反编译输出 100% 一致, per xdis inspect 验证).
    """
    # 1. 拿 xdis co.co_consts (顶层 code object 的真实 consts)
    try:
        from xdis import load_module
        _version, _ts, _magic, co, *_ = load_module(file_path)
        top_consts = co.co_consts
    except Exception:
        # xdis 失败 (e.g. 损坏 pyc) → 退而求其次, 返回 uncompyle6 原输出
        return skeleton

    def _replace_int_list(m: re.Match) -> str:
        """正则替换回调: 解析 "var = [N, N, N, ...]" → 查 co_consts → 还原字符串."""
        var_name = m.group(1)
        indices_str = m.group(2)
        try:
            indices = [int(x.strip()) for x in indices_str.split(",") if x.strip()]
        except ValueError:
            return m.group(0)  # 解析失败, 保留原输出

        # 2. 查 top_consts[N] 拿真实值
        try:
            real_values = [top_consts[i] for i in indices]
        except IndexError:
            return m.group(0)  # 索引越界, 跳过

        # 3. 全是 str 才替换 (其他类型可能本身正确, 避免破坏)
        if not real_values or not all(isinstance(v, str) for v in real_values):
            return m.group(0)

        # 4. 替换成 'val1', 'val2', ... (单引号, per Python 2 repr 风格)
        quoted = ", ".join(repr(v) for v in real_values)
        return f"{var_name} = [{quoted}]"

    # 5. 顶层 consts 列表替换
    fixed = _TOP_LEVEL_INT_LIST_RE.sub(_replace_int_list, skeleton)

    # 6. 末尾 `return` 去掉 (module-level 伪 artifact)
    fixed = _TRAILING_RETURN_RE.sub("", fixed)

    return fixed


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


def _purpose_for_force(force_version: Optional[int]) -> str:
    """反编译输出文件 purpose 命名 (per v0.5-output-samedir naming convention).

    Args:
        force_version: None=auto / 2=py2 / 3=py3

    Returns:
        purpose 字符串, 用于 `output_path_for(input, suffix='.py', purpose=...)` 命名:
        - "pyc" (auto) → `<stem>__pyc.py`
        - "pyc_py2" (force=2) → `<stem>__pyc_py2.py`
        - "pyc_py3" (force=3) → `<stem>__pyc_py3.py`
    """
    if force_version == 2:
        return "pyc_py2"
    if force_version == 3:
        return "pyc_py3"
    return "pyc"


def run_pyc_decompiler(
    file_path: str,
    force_version: Optional[int] = None,  # v0.5-pyc-decompiler-buttons: None=auto / 2=py2 / 3=py3
    write_output: bool = True,  # 反编译成功后是否写盘 (CLI 可关: --no-write)
    output_dir: Optional[str] = None,  # 显式指定输出目录 (None=pyc 同目录)
) -> PycDecompileResult:
    """pyc_decompiler decoder runner (per DecoderSpec.run signature).

    Args:
        file_path: .pyc 文件路径
        force_version: 强制反编译版本 (None=auto 按 magic / 2=uncompyle6 / 3=decompyle3)
        write_output: 反编译成功是否写盘到 output_dir / pyc 同目录
                      (Default: True; CLI 可传 False, GUI 默认 True per Owner "反编译成功后输出")
        output_dir: 输出目录 (None=pyc 同目录 per v0.5-output-samedir; GUI 弹 QFileDialog 选 dir)

    Returns:
        PycDecompileResult(source_code, method, magic_int, version, error, force_version, output_path)

    Note:
        - 反编译成功 (uncompyle6/decompyle3 产出 source_code) → 写 `<stem>__pyc[_pyN].py`
        - 反编译失败 / dis fallback → **不写盘** (per Owner "成功后输出" 暗含)
        - 写盘失败 (e.g. 权限不足) → `error` 字段填 write 错误, output_path=None
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

    # 按 force_version 路由 (per v0.5-pyc-decompiler-buttons):
    # - force=2: 强制 uncompyle6 (跳过 magic 判断)
    # - force=3: 强制 decompyle3 (跳过 magic 判断)
    # - None: 按 magic 自动判断
    is_py2 = bool(version) and version[0] == 2
    is_py3 = bool(version) and version[0] == 3

    source = ""
    method = ""
    err = None

    if force_version == 2:
        # 强制 py2, 跳过 magic
        # v0.5-pyc-decompiler-pycdc: Py2.x 优先 pycdc, 失败 fallback uncompyle6+fix
        source, method = _decompile_with_pycdc(file_path)
        if not source:
            # pycdc 不可用/失败 → fallback uncompyle6+fix
            try:
                source, method = _decompile_with_uncompyle6(file_path)
            except Exception as e:  # noqa: BLE001
                err = f"uncompyle6 fallback failed (force_version=2): {e}"
    elif force_version == 3:
        # 强制 py3, 跳过 magic (pycdc 不参与 Py3.x 路由, 走 decompyle3)
        try:
            source, method = _decompile_with_decompyle3(file_path)
        except Exception as e:  # noqa: BLE001
            err = f"decompyle3 failed (force_version=3): {e}"
    elif is_py2:
        # v0.5-pyc-decompiler-pycdc: Py2.x 优先 pycdc, 失败 fallback uncompyle6+fix
        source, method = _decompile_with_pycdc(file_path)
        if not source:
            try:
                source, method = _decompile_with_uncompyle6(file_path)
            except Exception as e:  # noqa: BLE001
                err = f"uncompyle6 fallback failed: {e}"
    elif is_py3:
        try:
            source, method = _decompile_with_decompyle3(file_path)
        except Exception as e:  # noqa: BLE001
            err = f"decompyle3 failed: {e}"
    else:
        err = f"unsupported Python version: {version}"

    # fallback 到 dis (per v0.5-pyc-magic-sniffer: 反编译失败时给字节码)
    if not source:
        try:
            source, method = _decompile_with_dis(file_path, raw)
            err = None  # fallback 成功就清掉 err
        except Exception as e:  # noqa: BLE001
            if err is None:
                err = f"dis fallback failed: {e}"

    # v0.5-pyc-decompiler-buttons: 反编译成功后写盘 (per Owner "成功后输出 py 文件到 pyc 同目录")
    # - 写盘条件: source 非空 (反编译出源码) + write_output=True
    # - 不写盘: 失败 / dis fallback / write_output=False
    # - 命名: `<stem>__pyc[_pyN].py` (per v0.5-output-samedir `output_path_for`)
    # v0.5-pyc-decompiler-pycdc: 写盘 method 含 "pycdc" (Py2.x 走 pycdc 也算成功反编译)
    output_path: Optional[str] = None
    if source and write_output and method in ("uncompyle6", "decompyle3", "pycdc"):
        # 写盘 (只有 uncompyle6/decompyle3/pycdc 成功才写, dis fallback 是字节码不算"成功反编译源码")
        try:
            purpose = _purpose_for_force(force_version)
            if output_dir:
                # 显式指定 output_dir (GUI 弹 QFileDialog 选的 / CLI --out-dir)
                out_dir = Path(output_dir).resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{p.stem}__{purpose}.py"
            else:
                # 默认: 与 input 同目录 (v0.5-output-samedir)
                out_path = output_path_for(p, suffix=".py", purpose=purpose)
            # 写盘
            out_path.write_text(source, encoding="utf-8")
            output_path = str(out_path)
        except Exception as e:  # noqa: BLE001
            # 写盘失败, 写 error 字段 (反编译成功但写盘失败仍是 partial success)
            err = f"decompile OK but write to disk failed: {e}"
            output_path = None

    return PycDecompileResult(
        input_path=str(p),
        raw_size=len(raw),
        source_code=source,
        method=method,
        magic_int=magic_int,
        version=version,
        error=err,
        force_version=force_version,
        output_path=output_path,
    )


# 注册到 decoder registry (per v0.5-decoder-menu + STRUCTURE.md §3.5)
# GUI Tools 菜单 / CLI `automisc decode pyc_decompiler` 自动从 registry 渲染
# v0.5-pyc-decompiler-buttons: 显示名改为 "🐍 Pyc 反编译 (自动判版本)" 区分强制按钮
register_decoder(DecoderSpec(
    name="pyc_decompiler",
    display="🐍 Pyc 反编译 (自动判版本)",  # v0.5-pyc-decompiler-buttons: 移除 "(默认 Python 2)" 歧义
    category="decode",  # 兼容旧 category 渲染
    group="general",  # 默认 group, 不走 cipher 解密工具分组
    cli_cmd="decode pyc_decompiler",
    run=run_pyc_decompiler,
    description=(
        "Py2.x / Py3.x pyc 反编译到 Python 源码 "
        "(uncompyle6 / decompyle3 / dis fallback; "
        "成功时写 <stem>__pyc.py 到 pyc 同目录; "
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
    "_purpose_for_force",
]
