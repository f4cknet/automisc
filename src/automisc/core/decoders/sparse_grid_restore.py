"""稀疏 (col, char) 网格 → 等宽 ASCII 字符画 decoder (v0.5-sparse-grid-restore)

**Owner 触发**（2026-07-01 CTF 实战 Pickle 反序列化）:
> "把稀疏 (col_index, char) 展开成等宽 ASCII 字符画, 这个能抽象成工具吗?
>  不管数组内容怎么变, 都可以用, 比如 (3, 'm'), (4, '"') 改为 (4, 'm'), (3, '#')"

**职责**: 把 list[list[tuple[int, str]]] 的 sparse 2D 网格还原成等宽 ASCII 字符画.
GUI 工具栏入口 ("共享基础工具 (PR1)" 分类, per Owner Q2 决策) +
CLI `automisc decode sparse_grid_restore --text "<literal>"` 子命令.

**输入格式** (auto-detect 3 种):
1. JSON: `[[3,"m"],[4,"\\""],...]`
2. Python literal: `[(3, 'm'), (4, '"'), ...]`
3. 格式化 raw text (如"随波逐流"反序列化工具 dump 出来的): 
   `[(3, 'm'), (4, '"'), ...]` — 用 ast.literal_eval 整段 parse 兜底

**输出**:
- rendered: list[str], 每行一条 ASCII 字符画
- stats: dict {rows, cols, total_chars, empty_rows, max_col}
- errors: str | None = None (None = 成功)

**算法**: CSR dense 化 — sparse (col, char) 列表 → 等宽字符行数组, last-wins 写入.

**vs base_convert / hex-ascii**: 同模式 (text_only pure compute, no binary),
但不是数据格式转换, 是 2D 网格几何还原.

**跟 trid 的关系** (per v0.5-trid-toolbar): 同样在"共享基础工具 (PR1)"分类, 同样不挂 auto-run, 同样不调 external binary;
唯一区别: trid 是 `tools/shared/` adapter (subprocess wrapper), 这个是 `core/decoders/` decoder (纯计算).

**cross-ref**:
- `v0.5-sparse-grid-restore` spec
- `v0.5-trid-toolbar` (GUI 工具栏相邻 entry 模式)
- `v0.5-cipher-decoders-textfix` (text_only 字段模式)
- `fix_decoder_registry_pyc_magic` (漏 __init__.py import 教训 — 本文件主动 import 进 __init__)
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field


# Size guard 防 OOM (per spec §6 risk 1)
MAX_CELLS: int = 100_000  # 100K cells (~1MB 字符)
MAX_INPUT_SIZE: int = 10 * 1024 * 1024  # 10MB text


class SparseGridError(Exception):
    """稀疏网格解析/渲染失败."""
    pass


@dataclass
class SparseGridResult:
    """渲染结果.

    Attributes:
        input: 原始输入串 (sanity, 截断 200 char)
        detected_format: "json" / "python-literal" / "raw-text" / "empty" / "unknown"
        rendered: list[str], 每行一条 ASCII 字符画
        stats: dict {rows, cols, total_chars, empty_rows, max_col}
        errors: str | None (None = 成功)
    """

    input: str
    detected_format: str
    rendered: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    errors: str | None = None


# ---------- 格式探测 + 解析 ----------
def _detect_format(text: str) -> str:
    """探测输入格式. Returns: json / python-literal / raw-text / empty / unknown."""
    s = text.strip()
    if not s:
        return "empty"
    if not s.startswith("["):
        return "unknown"
    # JSON 特征: 双引号 + 可被 json.loads parse
    if '"' in s[:200]:
        try:
            json.loads(s)
            return "json"
        except json.JSONDecodeError:
            pass
    # 兜底: python literal (含单引号 tuple 风格)
    return "python-literal"


def _parse_input(text: str, fmt: str) -> list[list[tuple[int, str]]]:
    """按 format 解析文本 → list[list[tuple[int, str]]].

    对所有 fmt 走 ast.literal_eval 兜底 (raw-text / python-literal 等价).
    JSON 走 json.loads (双引号 + 数字 int 风格, 跟 ast.literal_eval 行为一致但更快).
    """
    s = text.strip()
    if not s:
        return []
    try:
        if fmt == "json":
            data = json.loads(s)
        else:
            # python-literal / raw-text 兜底走 ast.literal_eval
            data = ast.literal_eval(s)
    except (json.JSONDecodeError, ValueError, SyntaxError) as e:
        raise SparseGridError(f"parse failed ({fmt}): {e}") from e

    # 验证结构: list[list[tuple[int, str]]]
    if not isinstance(data, list):
        raise SparseGridError(
            f"top-level must be list, got {type(data).__name__}"
        )
    rows_out: list[list[tuple[int, str]]] = []
    for ri, row in enumerate(data):
        # 兼容单 tuple 不是 list 的情况 (e.g. 用户贴了一行 ([(1,'m')]) )
        if isinstance(row, tuple):
            row = [row]
        if not isinstance(row, list):
            raise SparseGridError(
                f"row[{ri}] must be list, got {type(row).__name__}"
            )
        new_row: list[tuple[int, str]] = []
        for ci, cell in enumerate(row):
            # 接受 tuple 或 list 当 cell (e.g. JSON 没有 tuple, ast.literal_eval 接受两者)
            if (not isinstance(cell, (tuple, list))) or len(cell) != 2:
                raise SparseGridError(
                    f"row[{ri}][{ci}] must be tuple(int, str) or [int, str], got {cell!r}"
                )
            col_idx, char = cell
            # 容忍 numpy int / numpy str 等数字和字符串子类
            if isinstance(col_idx, bool) or not isinstance(col_idx, int):
                try:
                    col_idx = int(col_idx)  # type: ignore[arg-type]
                except (TypeError, ValueError) as e:
                    raise SparseGridError(
                        f"row[{ri}][{ci}][0] must be int, got {type(col_idx).__name__}"
                    ) from e
            if not isinstance(char, str):
                try:
                    char = str(char)
                except Exception as e:
                    raise SparseGridError(
                        f"row[{ri}][{ci}][1] must be str, got {type(char).__name__}"
                    ) from e
            if len(char) != 1:
                raise SparseGridError(
                    f"row[{ri}][{ci}][1] must be single char, got {char!r} (len={len(char)})"
                )
            new_row.append((col_idx, char))
        rows_out.append(new_row)
    return rows_out


# ---------- 渲染 (CSR dense 化) ----------
def render(
    rows: list[list[tuple[int, str]]],
    *,
    default_char: str = " ",
    sep: str = "",
    one_based: bool = True,
    keep_order: bool = True,
    col_width: int | None = None,
) -> tuple[list[str], dict]:
    """CSR dense 化: sparse (col, char) → 等宽 ASCII.

    Args:
        rows: sparse 2D grid, 每行 list[(col_index, char)]
        default_char: 空白单元用什么 (默认空格 ' ')
        sep: 列间分隔符 (默认 '' 无缝拼接; 给 '.' 看列边界)
        one_based: col index 是否从 1 开始 (默认 True, 跟原 writeup 一致)
        keep_order: True = 按元组出现顺序写入 (同 col 后到覆盖先到, last-wins)
                    False = 按 col 升序写入
        col_width: 强制列宽 (None = 按 max_col 自适应; 设值时 col 超过 col_width 的 cell silent skip,
                  跟原 writeup `temp=[' ']*76` try/except 行为一致)

    Returns:
        (rendered, stats)
        rendered: list[str] 每行一条字符画
        stats: dict {rows, cols, total_chars, empty_rows, max_col}

    Raises:
        SparseGridError: grid 过大 (per MAX_CELLS guard)
    """
    offset = 1 if one_based else 0
    n_rows = len(rows)

    # 推断列宽 (max col from actual data; 用户 col_width=None 时用这个)
    actual_max_col = 0
    total_chars = 0
    for row in rows:
        for c, _ in row:
            if c > actual_max_col:
                actual_max_col = c
            total_chars += 1

    # 决定最终 cols: 用户传 col_width 优先, 否则 = max_col - offset + 1 (空 grid 时 = 0)
    if col_width is not None:
        cols = col_width
    else:
        cols = max(actual_max_col - offset + 1, 0)
    if cols < 0:
        cols = 0

    # size guard
    if cols > 0 and n_rows * cols > MAX_CELLS:
        raise SparseGridError(
            f"grid too large: {n_rows} rows × {cols} cols = {n_rows * cols} cells "
            f"(max {MAX_CELLS})"
        )
    if cols <= 0:
        # 空 grid, 全空行
        return (
            [""] * n_rows if n_rows else []
        ), {
            "rows": n_rows,
            "cols": 0,
            "total_chars": total_chars,
            "empty_rows": n_rows,
            "max_col": actual_max_col,
        }

    rendered: list[str] = []
    empty_rows = 0
    default = default_char if len(default_char) == 1 else " "
    for row in rows:
        line = [default] * cols
        tuples = row if keep_order else sorted(row, key=lambda t: t[0])
        for c, ch in tuples:
            idx = c - offset
            if 0 <= idx < cols:  # col 越界兜底 (跟原 writeup try/except 一致)
                line[idx] = ch
        text = sep.join(line) if sep else "".join(line)
        if all(c == default for c in line):
            empty_rows += 1
        rendered.append(text)

    stats = {
        "rows": n_rows,
        "cols": cols,
        "total_chars": total_chars,
        "empty_rows": empty_rows,
        "max_col": actual_max_col,
    }
    return rendered, stats


# ---------- 总入口 ----------
def restore(text: str) -> SparseGridResult:
    """总入口: 文本 → SparseGridResult.

    Args:
        text: 原始输入 (auto-detect JSON / Python literal / raw text)

    Returns:
        SparseGridResult (含 rendered / stats / errors)
        errors=None 表示成功; errors=str 表示失败, rendered/stats 可能为空/部分填充
    """
    if len(text) > MAX_INPUT_SIZE:
        return SparseGridResult(
            input=text[:200],
            detected_format="unknown",
            rendered=[],
            stats={},
            errors=f"input too large: {len(text)} bytes (max {MAX_INPUT_SIZE})",
        )

    fmt = _detect_format(text)
    if fmt == "empty":
        return SparseGridResult(
            input=text,
            detected_format="empty",
            rendered=[],
            stats={
                "rows": 0, "cols": 0, "total_chars": 0,
                "empty_rows": 0, "max_col": 0,
            },
        )
    if fmt == "unknown":
        return SparseGridResult(
            input=text[:200],
            detected_format="unknown",
            rendered=[],
            stats={},
            errors=f"unrecognized input format (must start with '['): {text[:50]!r}...",
        )

    try:
        rows = _parse_input(text, fmt)
    except SparseGridError as e:
        return SparseGridResult(
            input=text[:200],
            detected_format=fmt,
            rendered=[],
            stats={},
            errors=str(e),
        )

    try:
        rendered, stats = render(rows)
    except SparseGridError as e:
        return SparseGridResult(
            input=text[:200],
            detected_format=fmt,
            rendered=[],
            stats={},
            errors=str(e),
        )

    return SparseGridResult(
        input=text[:200],
        detected_format=fmt,
        rendered=rendered,
        stats=stats,
    )


# ---------- v0.5-decoder-menu: 注册到 registry ----------
def _register() -> None:
    """注册 decoder 到 core.decoders.registry.

    GUI 工具栏入口: '共享基础工具 (PR1)' 分类 '🧩 稀疏网格还原'
    (per Owner 2026-07-01 Q2 拍板; runtime dispatch 走 decoder: prefix, per menu_dock.py:311)
    """
    from automisc.core.decoders.registry import DecoderSpec, register_decoder

    def _runner(file_path: str | None = None, text: str | None = None, **_):
        """text_only runner (跟 hex-ascii / cipher_decoders 同模式)."""
        if text is not None:
            return restore(text)
        if file_path is None:
            raise SparseGridError(
                "需要 --text '<sparse literal>' 或 --file <含 sparse literal 的 txt 文件>"
            )
        from pathlib import Path
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"input not found: {file_path}")
        text = p.read_text(errors="replace")
        if len(text) > MAX_INPUT_SIZE:
            raise SparseGridError(
                f"input too large: {len(text)} bytes (max {MAX_INPUT_SIZE})"
            )
        return restore(text)

    register_decoder(
        DecoderSpec(
            name="sparse_grid_restore",
            display="🧩 稀疏网格还原",
            category="decode",  # 兜底 category; GUI 主入口走 "共享基础工具 (PR1)" 分类, per menu_dock.py Q2 决策
            cli_cmd="decode sparse_grid_restore",
            run=_runner,
            description=(
                "稀疏 (col, char) 网格 → 等宽 ASCII 字符画 "
                "(auto-detect JSON / Python literal / raw text; max 100K cells; 同模式 OCR/数织图/Minesweeper 状态解)"
            ),
            text_only=True,  # 跟 hex-ascii 风格一致, GUI input 区粘 sparse literal
        )
    )


_register()


__all__ = [
    "SparseGridError",
    "SparseGridResult",
    "MAX_CELLS",
    "MAX_INPUT_SIZE",
    "render",
    "restore",
]
