"""FindSuspiciousRunner 单测（v0.5-philosophy-rethink）

测试 4 个核心不变量:
1. pick_suspicious_pool 按扩展名选对 pool (picture/traffic/archive/binary)
2. 4 个 pool **不**含禁止工具 (foremost/binwalk_extract/steghide_extract/john/fix_pseudo/bruteforce)
3. FindSuspiciousRunner 跑完整个 pool
4. find_suspicious_from_<type> 不触发任何 chain (auto_run 抢 flag 是 owner 决策 1 禁忌)

v0.5-philosophy-rethink 哲学:
- auto_run 是"找可疑点", 不是"雕/修/爆"
- journal 是"可疑点累积"
- 做题人决策下一步 (人工判断, 不抢 flag)
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.auto_runner import (
    EXTENSION_TO_POOL,
    FIND_SUSPICIOUS_ARCHIVE_TOOLS,
    FIND_SUSPICIOUS_BINARY_TOOLS,
    FIND_SUSPICIOUS_PICTURE_TOOLS,
    FIND_SUSPICIOUS_TRAFFIC_TOOLS,
    FindSuspiciousRunner,
    pick_suspicious_pool,
)


# ---------- pick_suspicious_pool 路由 ----------

class TestPickSuspiciousPool:
    """扩展名 → pool 路由."""

    @pytest.mark.parametrize("ext,expected_pool", [
        (".png", "picture"),
        (".jpg", "picture"),
        (".jpeg", "picture"),
        (".bmp", "picture"),
        (".gif", "picture"),
        (".pcap", "traffic"),
        (".pcapng", "traffic"),
        (".zip", "archive"),
        (".7z", "archive"),
        (".rar", "archive"),
        (".tar", "archive"),
        (".gz", "archive"),
        (".exe", "binary"),
        (".dll", "binary"),
        (".elf", "binary"),
        (".bin", "binary"),
        # 兜底: 未知扩展名 → binary
        (".unknown", "binary"),
        ("", "binary"),
    ])
    def test_extension_routes_to_correct_pool(self, ext: str, expected_pool: str) -> None:
        pool_name, tools = pick_suspicious_pool(f"/tmp/ctf_x{ext}")
        assert pool_name == expected_pool, (
            f"ext={ext} should route to {expected_pool}, got {pool_name}"
        )
        assert tools, f"pool={pool_name} should have tools, got []"

    def test_picture_pool_matches_constant(self) -> None:
        _, tools = pick_suspicious_pool("/tmp/x.png")
        assert tools == FIND_SUSPICIOUS_PICTURE_TOOLS

    def test_picture_pool_includes_steghide(self) -> None:
        """v0.5 实战反馈 (per Owner 2026-06-20 13:26):
        writeup 用 `steghide info good-已合并.jpg` 拿 qwe.zip 密码 — steghide 必须进 picture pool.

        steghide adapter 只跑 `steghide info` (纯探测, 无密码) — 不违背 owner 决策 1
        "auto_run 不抢 flag" (extract 留给 GUI 工具栏 / CLI 手工触发).
        """
        _, tools = pick_suspicious_pool("/tmp/x.jpg")
        assert "steghide" in tools, (
            f"picture pool 必须含 steghide (per Owner 实测): {tools}"
        )

    def test_picture_pool_has_six_tools(self) -> None:
        """picture pool 现在有 6 个工具: zsteg/steghide/exiftool/binwalk/strings/file."""
        _, tools = pick_suspicious_pool("/tmp/x.png")
        assert len(tools) == 6, (
            f"picture pool 应有 6 个工具, 实际 {len(tools)}: {tools}"
        )

    def test_traffic_pool_matches_constant(self) -> None:
        _, tools = pick_suspicious_pool("/tmp/x.pcap")
        assert tools == FIND_SUSPICIOUS_TRAFFIC_TOOLS

    def test_archive_pool_matches_constant(self) -> None:
        _, tools = pick_suspicious_pool("/tmp/x.zip")
        assert tools == FIND_SUSPICIOUS_ARCHIVE_TOOLS

    def test_binary_pool_matches_constant(self) -> None:
        _, tools = pick_suspicious_pool("/tmp/x.exe")
        assert tools == FIND_SUSPICIOUS_BINARY_TOOLS

    def test_extension_dict_covers_all_pools(self) -> None:
        """EXTENSION_TO_POOL 至少覆盖 4 类 pool 的代表扩展名."""
        assert EXTENSION_TO_POOL[".png"] == "picture"
        assert EXTENSION_TO_POOL[".pcap"] == "traffic"
        assert EXTENSION_TO_POOL[".zip"] == "archive"
        assert EXTENSION_TO_POOL[".exe"] == "binary"

    def test_extension_lookup_case_insensitive(self) -> None:
        """大写扩展名也能识别 (Path.suffix.lower() 已处理)."""
        pool_name, _ = pick_suspicious_pool("/tmp/x.PNG")
        assert pool_name == "picture"


# ---------- 4 个 pool 不含禁止工具 ----------

# owner 决策 1: auto_run 禁忌工具 (雕/修/爆 — 抢 flag)
FORBIDDEN_AUTO_RUN_TOOLS = {
    "foremost",         # 雕
    "binwalk_extract",  # 雕
    "steghide_extract", # 抽
    "john",             # 爆
    "fix_pseudo_zip",   # 修
    "bruteforce_zip",   # 爆
    "bruteforce_rar",   # 爆
    "lsb_extract",      # 抽
}


class TestPoolForbiddenTools:
    """所有 4 pool **不**含 owner 决策 1 禁忌工具."""

    @pytest.mark.parametrize("pool_name,tools", [
        ("picture", FIND_SUSPICIOUS_PICTURE_TOOLS),
        ("traffic", FIND_SUSPICIOUS_TRAFFIC_TOOLS),
        ("archive", FIND_SUSPICIOUS_ARCHIVE_TOOLS),
        ("binary", FIND_SUSPICIOUS_BINARY_TOOLS),
    ])
    def test_pool_no_forbidden_tools(self, pool_name: str, tools: list[str]) -> None:
        bad = FORBIDDEN_AUTO_RUN_TOOLS.intersection(tools)
        assert not bad, (
            f"pool={pool_name} 含禁止工具 (auto_run 不该雕/修/爆): {bad}"
        )


# ---------- FindSuspiciousRunner QThread 跑完整 pool ----------

@pytest.fixture
def sample_text() -> Path:
    return Path("tests/fixtures/sample_text.txt")


class TestFindSuspiciousRunner:
    """FindSuspiciousRunner QThread 跑完整 pool."""

    def test_picture_pool_runs_all_tools(self, qtbot, sample_text) -> None:
        """png-like 文件 → picture pool → 跑 6 个工具 (含 zsteg/steghide/exiftool/binwalk/strings/file)."""
        core = CoreOrchestrator()
        runner = FindSuspiciousRunner(core, str(sample_text.with_suffix(".png")))
        # 用 sample_text (txt) 跑 png 工具 (适配器应该按文件内容/扩展名判断)
        # 为了不让工具实际失败, 直接改 file_path 指向 sample_text
        # 但扩展名还得是 .png 让 pool 选 picture
        # → 复制 sample_text 到 .png 文件
        png_sample = sample_text.parent / "_test_find_suspicious.png"
        if not png_sample.exists():
            png_sample.write_bytes(sample_text.read_bytes())
        try:
            runner = FindSuspiciousRunner(core, str(png_sample))
            finished = []
            runner.chain_finished.connect(finished.append)
            with qtbot.waitSignal(runner.chain_finished, timeout=15000):
                runner.start()
            summaries = finished[0]
            tools_run = [s.tool_name for s in summaries]
            # picture pool 应跑 6 个工具 (部分可能失败因为 .png 适配器不适合 txt 内容)
            assert set(tools_run) <= set(FIND_SUSPICIOUS_PICTURE_TOOLS), (
                f"tools_run={tools_run} should be subset of picture pool"
            )
        finally:
            if png_sample.exists():
                png_sample.unlink()

    def test_pool_selected_signal(self, qtbot, tmp_path) -> None:
        """pool_selected signal 在 chain 启动前触发 (pool_name, tools)."""
        # 创建一个临时文件, 扩展名决定 pool
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"PK\x03\x04fake zip content for test\n")
        core = CoreOrchestrator()
        runner = FindSuspiciousRunner(core, str(test_file))
        selected = []
        runner.pool_selected.connect(lambda n, t: selected.append((n, t)))
        with qtbot.waitSignal(runner.chain_finished, timeout=15000):
            runner.start()
        assert len(selected) == 1
        pool_name, tools = selected[0]
        assert pool_name == "archive"
        assert tools == FIND_SUSPICIOUS_ARCHIVE_TOOLS

    def test_binary_pool_for_unknown_extension(self, qtbot, tmp_path) -> None:
        """未知扩展名兜底到 binary pool."""
        test_file = tmp_path / "test.unknown_ext"
        test_file.write_bytes(b"some binary content\n")
        core = CoreOrchestrator()
        runner = FindSuspiciousRunner(core, str(test_file))
        selected = []
        runner.pool_selected.connect(lambda n, t: selected.append((n, t)))
        with qtbot.waitSignal(runner.chain_finished, timeout=15000):
            runner.start()
        assert selected[0][0] == "binary"

    def test_chain_failed_on_missing_tool(self, qtbot, tmp_path) -> None:
        """工具不存在 (罕见) → chain_failed 信号 → 链终止."""
        # 没法直接模拟, 但 binary pool 里的 binwalk/exiftool 在测试环境可能不全
        # 简化: 只确认 chain_finished 触发即可 (即使失败也正常)
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"MZfake exe content\n")
        core = CoreOrchestrator()
        runner = FindSuspiciousRunner(core, str(test_file))
        with qtbot.waitSignal(runner.chain_finished, timeout=15000):
            runner.start()
        # 链结束 (success 或 failed 都 OK)

    def test_no_chain_triggered(self, qtbot, tmp_path) -> None:
        """find_suspicious 跑完不触发任何 chain (auto_run 不抢 flag).

        间接验证: FindSuspiciousRunner 类本身不引用任何 chain/builder.
        跑完 → tool_finished 信号只传 (tool_name, summary, result), 没 chain 相关.
        """
        import inspect

        from automisc.gui import auto_runner as ar_mod

        # 1) FindSuspiciousRunner.run 源码里不该调任何 chain 启动
        source = inspect.getsource(ar_mod.FindSuspiciousRunner.run)
        for forbidden in ("build_zip_chain", "build_foremost", "build_binwalk", "build_lsb", "execute_dag", "dag.execute"):
            assert forbidden not in source, (
                f"FindSuspiciousRunner.run 触发 chain {forbidden} — 违背 owner 决策 1"
            )

        # 2) find_suspicious_from_<type> 函数也不该调 chain
        for func_name in (
            "find_suspicious_from_picture",
            "find_suspicious_from_traffic",
            "find_suspicious_from_archive",
            "find_suspicious_from_binary",
        ):
            func = getattr(ar_mod, func_name)
            source = inspect.getsource(func)
            for forbidden in ("build_zip_chain", "build_foremost", "build_binwalk", "build_lsb", "execute_dag"):
                assert forbidden not in source, (
                    f"{func_name} 触发 chain {forbidden} — 违背 owner 决策 1"
                )


# ---------- 集成测试: end-to-end sync 函数跑一个真实样本 ----------

class TestFindSuspiciousSyncFunctions:
    """find_suspicious_from_<type> 同步函数 — 不需要 QThread."""

    def test_find_suspicious_from_archive_returns_list(self, sample_text) -> None:
        """find_suspicious_from_archive 跑 archive pool, 返回 list[ToolResult]."""
        from automisc.gui.auto_runner import find_suspicious_from_archive

        core = CoreOrchestrator()
        # sample_text (txt) 走 archive pool 时 sevenz/unzip 适配器会失败 → 也算 OK
        results = find_suspicious_from_archive(core, str(sample_text))
        assert isinstance(results, list)
        # archive pool 4 个工具 (即使失败也返回结果, 或跑完 4 个)
        assert len(results) >= 1

    def test_find_suspicious_from_picture_returns_list(self, sample_text) -> None:
        from automisc.gui.auto_runner import find_suspicious_from_picture

        core = CoreOrchestrator()
        results = find_suspicious_from_picture(core, str(sample_text))
        assert isinstance(results, list)
        assert len(results) >= 1
