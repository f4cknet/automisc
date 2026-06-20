"""AutoRunner 单测（v0.1.1 GUI 增强）"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.router import RouteRecommendation
from automisc.gui.auto_runner import AutoRunner, AutoRunSummary


@pytest.fixture
def sample_text() -> Path:
    return Path("tests/fixtures/sample_text.txt")


def _rec(tool: str, score: int = 10) -> RouteRecommendation:
    return RouteRecommendation(tool_name=tool, reason="test", score=score)


class TestAutoRunnerSuccess:
    def test_chain_finished_runs_all_tools(self, qtbot, sample_text):
        """链跑完所有工具 → chain_finished 触发，summaries 完整."""
        core = CoreOrchestrator()
        recs = [_rec("file"), _rec("strings")]
        runner = AutoRunner(core, recs, str(sample_text))
        finished = []
        runner.chain_finished.connect(finished.append)
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        assert len(finished) == 1
        summaries = finished[0]
        assert len(summaries) == 2
        assert [s.tool_name for s in summaries] == ["file", "strings"]
        # 跑成功
        for s in summaries:
            assert s.success, f"{s.tool_name} should succeed: {s.error}"

    def test_tool_started_signal(self, qtbot, sample_text):
        """tool_started signal 触发 (tool, index, total).

        v0.5-journal-highlight-keywords Q12 (per Owner 2026-06-16 2:12 铁律):
        "永远跑完所有 max_tools 个工具" — sample_text 含 flag{smoke} 触发 strings
        命中 severity=5, 但不 short-circuit, xxd 仍要跑.
        """
        core = CoreOrchestrator()
        recs = [_rec("file"), _rec("strings"), _rec("xxd")]
        runner = AutoRunner(core, recs, str(sample_text))
        events = []
        runner.tool_started.connect(lambda t, i, n: events.append((t, i, n)))
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        # Q12: 全部 3 个 tool 都启动, 不 short-circuit
        assert events == [("file", 0, 3), ("strings", 1, 3), ("xxd", 2, 3)]  

    def test_tool_finished_with_summary(self, qtbot, sample_text):
        """tool_finished 触发 + summary 含 exit_code + sps."""
        core = CoreOrchestrator()
        recs = [_rec("strings")]
        runner = AutoRunner(core, recs, str(sample_text))
        finished_tools = []
        runner.tool_finished.connect(lambda t, s: finished_tools.append((t, s)))
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        assert len(finished_tools) == 1
        tool_name, summary = finished_tools[0]
        assert tool_name == "strings"
        assert summary.exit_code == 0
        assert summary.suspicious_count == 1  # flag{smoke_test_pr9_xyz}
        assert summary.success is True


class TestAutoRunnerFiltering:
    def test_zero_score_filtered(self, qtbot, sample_text):
        """score=0 的工具跳过; Q12 永不 short-circuit, 其余工具全跑.

        v0.5-journal-highlight-keywords Q12 (per Owner 2026-06-16 2:12 铁律):
        sample_text 含 flag{smoke} 触发 strings 命中 severity=5, 但 SHORT_CIRCUIT_SEVERITY=99
        永不触发, binwalk 仍跑.
        """
        core = CoreOrchestrator()
        recs = [_rec("strings", score=10), _rec("file", score=0), _rec("binwalk", score=5)]
        runner = AutoRunner(core, recs, str(sample_text))
        finished = []
        sc = []
        runner.chain_finished.connect(finished.append)
        runner.short_circuited.connect(lambda t, r: sc.append(t))
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        tools = [s.tool_name for s in finished[0]]
        # file 被 score=0 过滤
        assert "file" not in tools
        # Q12: strings + binwalk 都跑 (无 short-circuit)
        assert "strings" in tools
        assert "binwalk" in tools
        # Q12: short_circuited 信号永远不发
        assert sc == []  

    def test_max_tools_limit(self, qtbot, sample_text):
        """max_tools 限制最大跑几个."""
        core = CoreOrchestrator()
        recs = [_rec(f"t{i}") for i in range(10)]
        runner = AutoRunner(core, recs, str(sample_text), max_tools=3)
        # 但 t0..t9 没注册 → 全部 chain_failed
        finished = []
        runner.chain_finished.connect(finished.append)
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        # 因为第一个就 chain_failed，链终止 → 1 个 summary
        assert len(finished[0]) == 1

    def test_empty_recommendations(self, qtbot, sample_text):
        """空推荐 → 立即 chain_finished + 空 summaries."""
        core = CoreOrchestrator()
        runner = AutoRunner(core, [], str(sample_text))
        finished = []
        runner.chain_finished.connect(finished.append)
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        assert finished[0] == []


class TestAutoRunnerError:
    def test_unknown_tool_stops_chain(self, qtbot, sample_text):
        """链中遇到 ToolNotFoundError → 终止链 + chain_failed 触发."""
        core = CoreOrchestrator()
        recs = [_rec("file"), _rec("nonexistent_xyz"), _rec("strings")]
        runner = AutoRunner(core, recs, str(sample_text))
        failed = []
        runner.chain_failed.connect(lambda t, e: failed.append((t, e)))
        finished = []
        runner.chain_finished.connect(finished.append)
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        assert len(failed) == 1
        assert failed[0][0] == "nonexistent_xyz"
        assert "ToolNotFoundError" in failed[0][1]
        # 链终止 → 只有 file + nonexistent_xyz 2 个 summary（strings 没跑）
        assert len(finished[0]) == 2
        assert [s.tool_name for s in finished[0]] == ["file", "nonexistent_xyz"]


class TestAutoRunnerStop:
    def test_stop_halts_chain(self, qtbot, sample_text):
        """stop() 在下一工具前停止链."""
        core = CoreOrchestrator()
        recs = [_rec("file"), _rec("strings"), _rec("binwalk")]
        runner = AutoRunner(core, recs, str(sample_text))
        started = []

        def on_start(tool, i, n):
            started.append(tool)
            if i == 0:
                runner.stop()  # 第 1 个工具跑完后停止

        runner.tool_started.connect(on_start)
        finished = []
        runner.chain_finished.connect(finished.append)
        with qtbot.waitSignal(runner.chain_finished, timeout=10000):
            runner.start()
        # 只跑了 file
        assert started == ["file"]
        # summaries 只有 file
        assert len(finished[0]) == 1
        assert finished[0][0].tool_name == "file"
