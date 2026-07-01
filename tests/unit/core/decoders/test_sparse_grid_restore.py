"""单测: sparse_grid_restore decoder (v0.5-sparse-grid-restore)

覆盖:
- _detect_format 5 种 (json / python-literal / raw-text / empty / unknown)
- _parse_input 7 类 (合法 / 非法语法 / 单引号 / 嵌套 / cell 多字符 / col_index 兜底 / tuple 单元素)
- render 10 类 (basic / empty grid / empty rows / col 越界 / last-wins / sort / zero-based / default_char / sep / size guard)
- restore 2 类 (end-to-end ctf sample / 大输入兜底)
- registry 2 类 (注册 + display name + text_only=True / GUI 工具栏分类)
- 离线约束 1 类 (无网络 import)
- CLI runner 3 类
"""
from __future__ import annotations

import pytest

from automisc.core.decoders import REGISTRY
from automisc.core.decoders.sparse_grid_restore import (
    MAX_CELLS,
    MAX_INPUT_SIZE,
    SparseGridError,
    SparseGridResult,
    render,
    restore,
)


# ============= _detect_format =============
class TestDetectFormat:
    def test_empty(self):
        assert restore("").detected_format == "empty"
        assert restore("   \n  \t").detected_format == "empty"

    def test_json_double_quote(self):
        # 1 row of 2 cells, each cell is 2-elem list [col, char]
        text = '[[[3,"m"],[4,"\\""]]]'
        r = restore(text)
        assert r.detected_format == "json"
        assert r.errors is None
        assert len(r.rendered) == 1
        # col 1-2 空格, col 3 'm', col 4 '"'
        assert r.rendered[0] == '  m"'
        assert r.stats["cols"] == 4

    def test_python_literal_single_quote(self):
        text = "[(3, 'm'), (4, '\"')]"
        r = restore(text)
        assert r.detected_format in ("python-literal", "raw-text")
        assert r.errors is None

    def test_nested_python_literal_owner_ctf_style(self):
        # Owner writeup 那种 "随波逐流" dump 出来的: [[(3, 'm'), (4, '"')], [(1, 'm')], []]
        text = "[[(3, 'm'), (4, '\"')], [(1, 'm')], []]"
        r = restore(text)
        assert r.errors is None
        assert len(r.rendered) == 3

    def test_unknown_starts_not_with_bracket(self):
        r = restore("hello world")
        assert r.detected_format == "unknown"
        assert r.errors is not None
        assert "unrecognized" in r.errors.lower()


# ============= _parse_input 错误路径 =============
class TestParseInput:
    def test_invalid_syntax(self):
        r = restore("[(3, 'm'")  # missing close
        assert r.errors is not None
        assert "parse failed" in r.errors.lower()

    def test_top_level_not_list(self):
        r = restore('"abc"')
        # 顶层 '"abc"' 不是 list, _detect_format 走 unknown 路径
        assert r.errors is not None

    def test_row_not_list_or_tuple(self):
        # outer = ["abc"] = 1 row, row = "abc" 是 string 不是 list/tuple
        r = restore('["abc"]')
        assert r.errors is not None
        assert "must be list" in r.errors

    def test_cell_not_tuple_or_list(self):
        # 1 row of 2 int cells — cell=1 不是 tuple/list
        r = restore("[[1, 2]]")
        assert r.errors is not None

    def test_cell_tuple_not_2_elements(self):
        r = restore("[[(1,)]]")  # tuple 只有 1 元素
        assert r.errors is not None

    def test_char_multi_char(self):
        r = restore("[[(1, 'ab')]]")  # char 是 2 字符
        assert r.errors is not None
        assert "single char" in r.errors

    def test_col_index_string_coerced(self):
        # JSON 里 col 写成 string — _parse_input 走 try int(col_idx) 兜底成 int
        r = restore('[[["3", "a"]]]')
        # cell = ['3', 'a'] list of 2, col_idx = '3', int('3') = 3 → 兜底成功
        assert r.errors is None
        assert r.stats["total_chars"] == 1


# ============= render 基础 =============
class TestRender:
    def test_basic_2x3(self):
        # 2 行 x 3 列
        rows = [
            [(1, 'a'), (3, 'c')],          # 第 1 行: a c (中间空格)
            [(2, 'B')],                     # 第 2 行: _B_
        ]
        rendered, stats = render(rows)
        assert rendered == ["a c", " B "]
        assert stats["rows"] == 2
        assert stats["cols"] == 3
        assert stats["total_chars"] == 3
        assert stats["empty_rows"] == 0
        assert stats["max_col"] == 3

    def test_empty_grid(self):
        rows: list[list[tuple[int, str]]] = []
        rendered, stats = render(rows)
        assert rendered == []
        assert stats == {
            "rows": 0, "cols": 0, "total_chars": 0,
            "empty_rows": 0, "max_col": 0,
        }

    def test_grid_with_empty_rows(self):
        # 3 行, 第 2 行空
        rows = [[(1, 'a')], [], [(2, 'b')]]
        rendered, stats = render(rows)
        assert rendered == ["a ", "  ", " b"]
        assert stats["empty_rows"] == 1

    def test_col_width_param_silently_drops_overflow(self):
        # 默认 col_width=None, cols 跟实际 max_col 走 → col=20 不越界
        rows = [[(1, 'a'), (10, 'Z')]]  # cols = max_col=10
        rendered, stats = render(rows)
        assert len(rendered[0]) == 10
        assert rendered[0][0] == 'a'
        assert rendered[0][9] == 'Z'
        assert stats["cols"] == 10
        assert stats["max_col"] == 10

        # 显式 col_width=10, col=20 越界 → silent skip
        rows2 = [[(1, 'a'), (20, 'Z')]]
        rendered2, stats2 = render(rows2, col_width=10)
        assert len(rendered2[0]) == 10
        assert rendered2[0][0] == 'a'
        assert 'Z' not in rendered2[0]  # silent skip
        assert stats2["max_col"] == 20  # 实际 data max_col 仍记录, 供 stats 透出

    def test_last_wins_overlap(self):
        # 同 col 出现 2 次 — 后到覆盖
        rows = [[(1, 'a'), (1, 'b')]]  # 同 col=1 后 'b' 覆盖 'a'
        rendered, _ = render(rows)
        assert rendered[0][0] == 'b'

    def test_keep_order_false_sort_by_col(self):
        # keep_order=False → 按 col 升序, last-wins 仍然生效
        rows = [[(3, 'c'), (1, 'a')]]  # 顺序不影响, 都是 a c
        rendered, _ = render(rows, keep_order=False)
        assert rendered[0] == "a c"

    def test_zero_based(self):
        # one_based=False: col index 从 0 起
        rows = [[(0, 'A'), (2, 'C')]]  # 0-indexed 长度 3
        rendered, stats = render(rows, one_based=False)
        assert rendered == ["A C"]
        assert stats["cols"] == 3
        assert stats["max_col"] == 2

    def test_default_char_dot(self):
        # default_char 在 cols > 1 时显出, 单 cell cols=1 时不显
        rows = [[(1, 'a'), (5, 'b')]]  # max_col=5 → cols=5
        rendered, _ = render(rows, default_char=".")
        assert rendered == ["a...b"]  # col 1='a', col 2-4='.', col 5='b'

    def test_sep_dot_show_boundaries(self):
        # sep='.' 在每个 cell char 之间插 '.', 即使空格也插
        rows = [[(1, 'a'), (3, 'c')]]
        rendered, _ = render(rows, sep=".")
        # 1='a', 2=' '(空), 3='c' → a + . + ' ' + . + c = "a. .c"
        assert rendered == ["a. .c"]

    def test_size_guard_raise(self):
        # 构造超大 grid: 100 cell × 1001 行 = 100100 cells > MAX_CELLS=100000
        rows = [[(i + 1, 'a') for i in range(100)]] * 1001
        with pytest.raises(SparseGridError) as exc_info:
            render(rows)
        assert "too large" in str(exc_info.value).lower()


# ============= restore end-to-end =============
class TestRestore:
    def test_owner_ctf_sample_first_5_rows(self):
        """Owner CTF 实战 enc 数据前 5 行 end-to-end 渲染.

        Sample 取自 Owner 2026-07-01 那次实战 (Pickle 反序列化出来的 30×76 sparse grid).
        这里取前 5 行验证渲染逻辑通过.
        """
        text = """[
            [(3, 'm'), (4, '"'), (5, '"'), (8, '"'), (9, '"'), (10, '#'), (31, 'm'), (32, '"'), (33, '"'), (44, 'm'), (45, 'm'), (46, 'm'), (47, 'm'), (75, '#')],
            [(1, 'm'), (2, 'm'), (3, '#'), (4, 'm'), (5, 'm'), (10, '#'), (16, 'm')],
            [(3, '#'), (10, '#'), (15, '"'), (19, '#'), (22, '#')],
            [(3, '#'), (10, '#'), (15, 'm'), (16, '"'), (17, '"')],
            [(3, '#'), (10, '"'), (11, 'm'), (12, 'm'), (15, '"')]
        ]"""
        r = restore(text)
        assert r.errors is None
        assert len(r.rendered) == 5
        assert all(isinstance(line, str) for line in r.rendered)
        # 第 1 行 col max=75 → cols=75
        assert r.stats["max_col"] == 75
        assert r.stats["rows"] == 5
        assert r.stats["cols"] == 75
        # 第 1 行: col=3 'm', col=4 '"', col 5 '"'
        first_line = r.rendered[0]
        # one_based=True default → col_index=3 → idx=3-1=2
        assert first_line[2] == 'm'
        # col 4 '"', idx=3
        assert first_line[3] == '"'

    def test_too_large_input_size(self):
        # 11MB text → MAX_INPUT_SIZE=10MB 兜底
        big = "[" + "1, " * (11 * 1024 * 1024) + "]"
        r = restore(big)
        assert r.errors is not None
        assert "too large" in r.errors.lower()


# ============= registry 注册 =============
class TestRegistry:
    def test_decoder_registered(self):
        specs = [s for s in REGISTRY if s.name == "sparse_grid_restore"]
        assert len(specs) == 1
        spec = specs[0]
        assert spec.display == "🧩 稀疏网格还原"
        assert spec.text_only is True
        assert spec.cli_cmd == "decode sparse_grid_restore"
        assert callable(spec.run)
        assert "sparse" in spec.description.lower() or "(col" in spec.description.lower()

    def test_gui_display_name_shared_category(self):
        """GUI 工具栏 '共享基础工具 (PR1)' 分类下新增 '🧩 稀疏网格还原'."""
        from automisc.gui.menu_dock import TOOL_CATEGORIES, ACTION_DISPLAY_NAMES
        shared = TOOL_CATEGORIES.get("共享基础工具 (PR1)", [])
        assert "decoder:sparse_grid_restore" in shared
        assert ACTION_DISPLAY_NAMES.get("decoder:sparse_grid_restore") == "🧩 稀疏网格还原"


# ============= 离线约束 =============
class TestOffline:
    def test_module_imports_no_network(self):
        """验证 sparse_grid_restore 仅依赖 stdlib, 无网络调用."""
        import automisc.core.decoders.sparse_grid_restore as mod
        import inspect

        source = inspect.getsource(mod)
        # 无网络相关模块
        assert "urllib" not in source
        assert "requests" not in source
        assert "socket" not in source
        assert "http" not in source.lower()


# ============= CLI runner =============
class TestCliRunner:
    def test_runner_text_mode(self):
        """CLI --text '<literal>' 路径."""
        spec = [s for s in REGISTRY if s.name == "sparse_grid_restore"][0]
        # Standard 1-row-of-2-cells format: outer list 1 element, row has 2 cells
        result = spec.run(text="[[(1, 'a'), (3, 'c')]]")
        assert isinstance(result, SparseGridResult)
        assert result.errors is None
        assert result.rendered == ["a c"]

    def test_runner_text_mode_invalid(self):
        spec = [s for s in REGISTRY if s.name == "sparse_grid_restore"][0]
        result = spec.run(text="garbage")
        # 'garbage' 不是 sparse literal, 会走 unknown 路径
        assert result.errors is not None

    def test_runner_no_input_raises(self):
        """CLI 不传 text 也不传 file_path → 报错 (不是 text_only 模式)."""
        spec = [s for s in REGISTRY if s.name == "sparse_grid_restore"][0]
        with pytest.raises(SparseGridError) as exc_info:
            spec.run()
        assert "需要 --text" in str(exc_info.value) or "--text" in str(exc_info.value)


# ============= size guard 常量 sanity =============
def test_max_constants():
    assert MAX_CELLS == 100_000
    assert MAX_INPUT_SIZE == 10 * 1024 * 1024
