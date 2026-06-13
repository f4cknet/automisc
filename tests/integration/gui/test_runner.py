"""ToolRunner 单测（v0.1.1 gui/runner.py）"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.runner import ToolRunner


@pytest.fixture
def sample_text() -> Path:
    return Path("tests/fixtures/sample_text.txt")


class TestToolRunnerSignals:
    def test_runner_finishes_with_result(self, qtbot, sample_text):
        """runner.start() → 异步跑完 → finished_with_result 触发."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "strings", str(sample_text))
        results = []
        runner.finished_with_result.connect(results.append)
        with qtbot.waitSignal(runner.finished_with_result, timeout=10000):
            runner.start()
        assert len(results) == 1
        result = results[0]
        assert result.exit_code == 0
        assert "flag{smoke_test_pr9_xyz}" in result.stdout

    def test_runner_emits_started(self, qtbot, sample_text):
        """started_run signal 触发."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "strings", str(sample_text))
        events = []
        runner.started_run.connect(lambda t, f: events.append((t, f)))
        with qtbot.waitSignal(runner.finished_with_result, timeout=10000):
            runner.start()
        assert events == [("strings", str(sample_text))]

    def test_runner_finished_before_started_in_signal(self, qtbot, sample_text):
        """started_run signal 在 finished_with_result 之前触发."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "strings", str(sample_text))
        order = []
        runner.started_run.connect(lambda *_: order.append("started"))
        runner.finished_with_result.connect(lambda *_: order.append("finished"))
        with qtbot.waitSignal(runner.finished_with_result, timeout=10000):
            runner.start()
        assert order == ["started", "finished"]


class TestToolRunnerError:
    def test_runner_failed_for_unknown_tool(self, qtbot):
        """ToolNotFoundError 走 failed_with_error signal."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "nonexistent_tool_xyz", "/tmp/x")
        errors = []
        runner.failed_with_error.connect(errors.append)
        with qtbot.waitSignal(runner.failed_with_error, timeout=10000):
            runner.start()
        assert len(errors) == 1
        assert "ToolNotFoundError" in errors[0]

    def test_runner_failed_for_missing_file(self, qtbot):
        """文件不存在 → adapter 跑失败（exit_code != 0）→ finished_with_result 触发."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "strings", "/tmp/definitely_not_exists_xyz_42")
        results = []
        runner.finished_with_result.connect(results.append)
        with qtbot.waitSignal(runner.finished_with_result, timeout=10000):
            runner.start()
        assert len(results) == 1
        # adapter 把错误塞 exit_code + stderr，不抛异常
        result = results[0]
        assert result.exit_code != 0
        assert "No such file" in result.stderr or "not found" in result.stderr.lower()


class TestToolRunnerProperties:
    def test_result_property(self, qtbot, sample_text):
        """runner.result 在 finished 后可读."""
        core = CoreOrchestrator()
        runner = ToolRunner(core, "strings", str(sample_text))
        with qtbot.waitSignal(runner.finished_with_result, timeout=10000):
            runner.start()
        assert runner.result is not None
        assert runner.result.tool_name == "strings"

    def test_error_property_on_failure(self, qtbot):
        core = CoreOrchestrator()
        runner = ToolRunner(core, "nonexistent_xyz", "/tmp/x")
        with qtbot.waitSignal(runner.failed_with_error, timeout=10000):
            runner.start()
        assert runner.error is not None
        assert "ToolNotFoundError" in runner.error
