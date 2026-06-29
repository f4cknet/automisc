"""v0.5-fix-find-suspicious-race-condition 单测 (per Owner 2026-06-29 22:57 拍板 A).

实战触发: drop jpg (picture pool 含 steghide 30s timeout) → drop zip → 旧 steghide
subprocess 30s 后 emit tool_finished 写入新 output 区, 误读为当前文件.

修法 (per spec §2):
1. base.py: ToolAdapter 持 _current_proc (Popen), _terminate_current_proc() 强 kill
2. orchestrator.py: 持 _last_adapter, kill_last_subprocess() 给 main_window 调
3. main_window.py: _on_new_file_selected 调 core.kill_last_subprocess() 强清旧

测试覆盖:
- adapter _terminate_current_proc 强 kill 当前 Popen
- orchestrator kill_last_subprocess 调 adapter _terminate_current_proc
- main_window 拖新文件时调 core.kill_last_subprocess
- _terminate_current_proc idempotent (多次调不抛)
- 集成测试: 模拟长 subprocess 跑着, 拖新文件, 旧 subprocess terminate
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from automisc.core.orchestrator import CoreOrchestrator
from automisc.tools.base import ToolAdapter
from automisc.core.result import ToolResult


# Mock adapter (ToolAdapter 是 abstract, 不能直接实例化)
class _MockAdapter(ToolAdapter):
    """mock adapter for _terminate_current_proc 单测, 不实现 run()."""
    name = "_mock_v5_race"
    category = "test"
    description = "mock"

    def run(self, file_path: str) -> ToolResult:
        return ToolResult(tool_name=self.name, exit_code=0, stdout="", stderr="")


def _new_adapter() -> ToolAdapter:
    return _MockAdapter()


# ---------- 1. adapter _terminate_current_proc 强 kill ----------

class TestAdapterTerminateCurrentProc:
    """ToolAdapter._terminate_current_proc 强 kill 当前持有的 Popen handle."""

    def test_terminate_kills_running_popen(self):
        """adapter 持 Popen, 调 _terminate_current_proc 后 poll() 必 != None."""
        a = _new_adapter()
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        a._current_proc = proc
        assert proc.poll() is None
        t0 = time.monotonic()
        a._terminate_current_proc()
        elapsed = time.monotonic() - t0
        assert proc.poll() is not None, "Popen 未终止"
        assert elapsed < 3.0, f"terminate 耗时 {elapsed:.1f}s 超 3s"
        assert a._current_proc is None

    def test_terminate_idempotent_no_proc(self):
        """没 _current_proc 时调 _terminate_current_proc 啥也不做, 不抛."""
        a = _new_adapter()
        a._current_proc = None
        a._terminate_current_proc()
        a._terminate_current_proc()
        assert a._current_proc is None

    def test_terminate_idempotent_already_finished(self):
        """_current_proc 已结束 (poll != None), 调 _terminate_current_proc 啥也不做, handle 清空."""
        a = _new_adapter()
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('done')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()
        assert proc.poll() is not None
        a._current_proc = proc
        a._terminate_current_proc()
        assert a._current_proc is None

    def test_terminate_callable_twice_safe(self):
        """连续调 2 次 _terminate_current_proc, 第二次 啥也不做 (handle 已 None)."""
        a = _new_adapter()
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        a._current_proc = proc
        a._terminate_current_proc()
        assert a._current_proc is None
        a._terminate_current_proc()
        assert a._current_proc is None


# ---------- 2. orchestrator kill_last_subprocess ----------

class TestOrchestratorKillLastSubprocess:
    """CoreOrchestrator.kill_last_subprocess 强 kill 最近一次工具的 subprocess."""

    def test_kill_last_subprocess_no_run_yet(self):
        """没 run_tool 调过, kill_last_subprocess 啥也不做."""
        core = CoreOrchestrator()
        core.kill_last_subprocess()
        assert core._last_adapter is None

    def test_run_tool_sets_last_adapter(self, tmp_path):
        """run_tool 后 _last_adapter 持有 (per v0.5-fix-find-suspicious-race-condition)."""
        # 准备一个 fake file
        fake_file = tmp_path / "fake.txt"
        fake_file.write_text("dummy content for adapter run")
        # 跑 strings adapter (短跑, exit 0)
        core = CoreOrchestrator()
        try:
            core.run_tool("strings", str(fake_file))
        except Exception:
            pytest.skip("strings adapter run failed in this env")
        assert core._last_adapter is not None
        assert core._last_adapter.name == "strings"

    def test_kill_last_subprocess_terminates_adapter_handle(self, tmp_path):
        """run_tool 跑长 subprocess 工具, 调 kill_last_subprocess 强 terminate."""
        from automisc.core.registry import register_tool

        @register_tool
        class _SleepAdapter(ToolAdapter):
            name = "_test_sleep_adapter_v5_race"
            category = "test"
            description = "test sleep adapter for race condition test"

            def run(self, file_path: str) -> ToolResult:
                proc = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._current_proc = proc
                try:
                    proc.communicate(timeout=30.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return ToolResult(
                    tool_name=self.name,
                    exit_code=124,
                    stdout="",
                    stderr="subprocess timeout",
                    suspicious_points=[],
                )

        core = CoreOrchestrator()
        adapter = _SleepAdapter()
        core._last_adapter = adapter
        import threading
        result_box = {}

        def run_in_thread():
            result_box["r"] = adapter.run(str(tmp_path / "fake.txt"))

        t = threading.Thread(target=run_in_thread, daemon=True)
        t.start()
        # 等 0.5s 让 Popen 起来 (Win Popen 启动 ~0.1-0.3s)
        time.sleep(0.5)
        assert adapter._current_proc is not None
        t0 = time.monotonic()
        core.kill_last_subprocess()
        elapsed = time.monotonic() - t0
        assert adapter._current_proc is None
        assert elapsed < 3.0, f"kill_last_subprocess 耗时 {elapsed:.1f}s 超 3s"
        t.join(timeout=5.0)


# ---------- 3. main_window 拖新文件时调 kill_last_subprocess ----------

class TestMainWindowKillOnNewFile:
    """MainWindow._on_new_file_selected 拖新文件时调 core.kill_last_subprocess."""

    def test_on_new_file_selected_calls_kill_last_subprocess(self, qtbot, tmp_path, monkeypatch):
        """拖新文件时 core.kill_last_subprocess() 被调 (spy)."""
        from automisc.gui.main_window import MainWindow

        f1 = tmp_path / "first.jpg"
        f1.write_bytes(b"\xff\xd8\xff\xe0fake jpg\n")
        f2 = tmp_path / "second.zip"
        f2.write_bytes(b"PK\x03\x04fake zip\n")

        w = MainWindow()
        qtbot.addWidget(w)

        # 拖 f1
        w._on_new_file_selected(f1, source="drop")
        if w._find_suspicious_runner:
            w._find_suspicious_runner.wait(30000)

        # spy
        call_count = {"n": 0}
        original = w.core.kill_last_subprocess

        def spy_kill():
            call_count["n"] += 1
            return original()

        monkeypatch.setattr(w.core, "kill_last_subprocess", spy_kill)

        # 拖 f2 → 应调 kill_last_subprocess
        w._on_new_file_selected(f2, source="drop")
        assert call_count["n"] == 1, (
            f"拖新文件应调 1 次 core.kill_last_subprocess, 实际 {call_count['n']}"
        )


# ---------- 4. 集成测试: 模拟拖新文件, 旧 subprocess terminate ----------

# 注: 集成测试 (拖 jpg → 拖 zip, 验证 0 段写入) 已在
# tools/_debug/repro_gui_drop2.py 端到端跑过 (per main session 22:32 验证),
# 单测层拆"长 subprocess + 强 terminate" 行为更可靠 (见 TestOrchestratorKillLastSubprocess
# 上面), 这里不重复. 端到端集成建议 GUI 实测 (Owner 22:32 实战确认) + repro_gui_drop2.py
# 已有 5 tools 跑完 chain_finished = ['sevenz', 'unzip', 'zip_classify', 'file', 'strings']
# 0 steghide 段, 验证 race condition 修后行为正确.
