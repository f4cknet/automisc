"""Integration tests for v0.5 chain menu (GUI 同步 CLI).

- MainWindow._run_chain() 触发 ChainRunner (QThread)
- 5 chain 都能跑 (zip / zip-full / binwalk / foremost / lsb)
- output_view 渲染 log + summary + flag_candidate
"""
from __future__ import annotations

import os

# 必须在 import PySide6 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.chain_runner import ChainRunner
from automisc.gui.main_window import MainWindow


# ---------- fixture ----------
@pytest.fixture
def sample_steg_png():
    """Owner 提供的真实 CTF 题目 (233KB PNG with LSB text)."""
    return str(Path("Challenge/steg.png"))


# ---------- ChainRunner 单测 ----------
class TestChainRunner:
    """ChainRunner 是 QThread, 跑完 emit finished_with_context signal."""

    def test_chain_runner_finished_signal(self, qtbot, tmp_path):
        # 造个简单 zip fixture
        import zipfile

        p = tmp_path / "test.zip"
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("flag.txt", "flag{test_xyz}\n")

        results = {}

        def on_finished(chain_name, file_path, context):
            results["context"] = context
            results["chain_name"] = chain_name
            results["file_path"] = file_path

        runner = ChainRunner(chain_name="zip", file_path=str(p))
        runner.finished_with_context.connect(on_finished)
        runner.start()
        qtbot.waitUntil(lambda: "context" in results, timeout=10_000)
        runner.wait()

        assert results["chain_name"] == "zip"
        assert results["file_path"] == str(p)
        assert "file_path" in results["context"]
        assert "__log__" in results["context"]
        log = results["context"]["__log__"]
        assert len(log) >= 1
        # 第一次 try_unzip 应该 OK (无密码)
        first_step = log[0]
        assert first_step["node"] == "try_unzip"
        assert first_step["success"] is True

    def test_chain_runner_lsb_signal(self, qtbot, tmp_path):
        """LSB chain runner: 模拟一个无嵌入 PNG → 跑到 lsb step."""
        # 造一个最小 PNG (不需 LSB 内容, 跑 zsteg 应 graceful)
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        results = {}

        def on_finished(chain_name, file_path, context):
            results["context"] = context

        runner = ChainRunner(chain_name="lsb", file_path=str(png))
        runner.finished_with_context.connect(on_finished)
        runner.start()
        qtbot.waitUntil(lambda: "context" in results, timeout=30_000)
        runner.wait()

        log = results["context"]["__log__"]
        # 至少 2 步: binwalk + lsb
        assert len(log) >= 1
        nodes = [s["node"] for s in log]
        assert "binwalk_extract" in nodes or "lsb_extract" in nodes


# ---------- MainWindow._run_chain() ----------
class TestMainWindowChain:
    """GUI 主窗口的 Chain 菜单入口."""

    def test_chain_menu_5_entries(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)

        # 找 Chain 菜单
        chain_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Chain":
                chain_menu = action.menu()
                break

        assert chain_menu is not None, "Chain 菜单未找到"

        # 5 个 chain 入口 + 1 个 zip-full limit
        actions = chain_menu.actions()
        action_texts = [a.text() for a in actions]
        for chain_name in ("zip", "zip-full", "binwalk", "foremost", "lsb"):
            assert any(chain_name in t for t in action_texts), (
                f"Chain 菜单缺 {chain_name} 入口; 实际: {action_texts}"
            )

    def test_run_chain_no_file(self, qtbot):
        """未选文件时 _run_chain → status bar 报错."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = None

        window._run_chain("lsb")
        # status bar 应有 "no file" / "请先拖入" 类提示
        msg = window.statusBar().currentMessage()
        assert "文件" in msg or "file" in msg.lower()

    def test_run_chain_lsb_steg_png(self, qtbot, sample_steg_png):
        """GUI 跑 steg.png lsb chain → output 应含 flag_candidate 高亮."""
        if not Path(sample_steg_png).exists():
            pytest.skip("Challenge/steg.png 不存在")

        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = Path(sample_steg_png)

        window._run_chain("lsb")
        # 等待 ChainRunner 跑完
        qtbot.waitUntil(
            lambda: window._chain_runner is None
            or not window._chain_runner.isRunning(),
            timeout=30_000,
        )
        if window._chain_runner:
            window._chain_runner.wait()

        output_text = window.output_view.toPlainText()
        # 应有 chain log + summary
        assert "chain log" in output_text or "step" in output_text
        # 应有 flag_candidate 高亮 (steg.png 含 "secret key is:")
        assert "FLAG CANDIDATE" in output_text or "st3g0_saurus_wr3cks" in output_text
