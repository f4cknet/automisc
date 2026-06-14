"""单测: GUI Bug Fix 3 个 (2026-06-14)

1. 工具栏 (TOOL_CATEGORIES) 含 2 decoder: base64-image + hex-ascii
2. callback 签名 (name, kind) - kind: adapter | action | decoder
3. LSB 抽到的整段 text 高亮 (整段深黄底 + 敏感词红底黄字)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from automisc.gui.main_window import MainWindow
from automisc.gui.menu_dock import TOOL_CATEGORIES, ToolMenuDock
from automisc.gui.output_view import OutputView
from automisc.core.decoders.registry import list_decoders


# ---------- Bug 1 & 2: 工具栏入口 ----------
class TestToolMenuDockDecoders:
    def test_dock_has_decoder_categories(self, qtbot):
        """左侧工具栏有 2 个新分类."""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)

        # 找 2 个新分类
        cat_names = []
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            cat_names.append(cat.text(0))

        assert any("解码工具" in n for n in cat_names), f"缺解码工具分类: {cat_names}"
        assert any("进制转换" in n for n in cat_names), f"缺进制转换分类: {cat_names}"

    def test_dock_lists_both_decoders(self, qtbot):
        """base64-image + hex-ascii 都在工具栏."""
        dock = ToolMenuDock(on_tool_selected=lambda _, k: None)
        qtbot.addWidget(dock)

        decoder_names = []
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            if "解码工具" in cat.text(0) or "进制转换" in cat.text(0):
                for j in range(cat.childCount()):
                    decoder_names.append(cat.child(j).data(0, Qt.UserRole))

        for expected in ("decoder:base64-image", "decoder:hex-ascii"):
            assert expected in decoder_names, f"工具栏缺 {expected}; 实际: {decoder_names}"


# ---------- Bug 1 & 2: callback 签名 + dispatch ----------
class TestCallbackSignature:
    def test_callback_receives_kind(self, qtbot):
        """点击 decoder 项 -> callback 收到 (name, 'decoder')."""
        selected = []
        dock = ToolMenuDock(on_tool_selected=lambda n, k: selected.append((n, k)))
        qtbot.addWidget(dock)

        # 模拟点击 decoder:base64-image
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                child = cat.child(j)
                if child.data(0, Qt.UserRole) == "decoder:base64-image":
                    dock._on_item_clicked(child, 0)
                    assert selected == [("base64-image", "decoder")]
                    return
        assert False, "decoder:base64-image 未在工具栏"

    def test_callback_dispatch_adapter(self, qtbot):
        """点击 adapter 项 -> callback 收到 (name, 'adapter')."""
        selected = []
        dock = ToolMenuDock(on_tool_selected=lambda n, k: selected.append((n, k)))
        qtbot.addWidget(dock)

        # 找 "file" (PR1 第 1 个)
        for i in range(dock.tree.topLevelItemCount()):
            cat = dock.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                child = cat.child(j)
                if child.data(0, Qt.UserRole) == "file":
                    dock._on_item_clicked(child, 0)
                    assert selected == [("file", "adapter")]
                    return
        assert False, "file 未在工具栏"

    def test_main_window_dispatches_decoder_to_run_decoder(self, qtbot):
        """MainWindow 接收到 (name='base64-image', kind='decoder') -> 调 _run_decoder."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = Path("Challenge/KEY.exe")  # 用真实文件避免 NotFoundError

        # 直接调 _on_dock_item_selected (bypass click)
        window._on_dock_item_selected("base64-image", "decoder")
        # _run_decoder 起 QThread, 等它跑完
        qtbot.waitUntil(
            lambda: window._decode_runner is None
            or not window._decode_runner.isRunning(),
            timeout=10_000,
        )
        if window._decode_runner:
            window._decode_runner.wait()

        # output 应含 Decoder: base64-image
        out = window.output_view.toPlainText()
        assert "Decoder: base64-image" in out

    def test_main_window_dispatches_adapter_to_run_tool(self, qtbot):
        """MainWindow 接收到 (name='strings', kind='adapter') -> 调 _run_tool."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = Path("Challenge/QR_code.png")

        # 模拟 dispatch
        window._on_dock_item_selected("strings", "adapter")
        qtbot.waitUntil(
            lambda: window._runner is None or not window._runner.isRunning(),
            timeout=10_000,
        )
        if window._runner:
            window._runner.wait()

        out = window.output_view.toPlainText()
        assert "strings" in out


# ---------- Bug 3: LSB 抽到的整段 text 高亮 ----------
class TestLsbTextHighlight:
    def test_output_view_append_lsb_text(self, qtbot):
        """OutputView.append_lsb_text 应正常 append text (不 crash)."""
        view = OutputView()
        qtbot.addWidget(view)
        view.append_lsb_text(
            "Hey I think we can write safely in this file without anyone seeing it. "
            "Anyway, the secret key is: st3g0_saurus_wr3cks",
            channel="b1,rgb,lsb,xy",
        )
        out = view.toPlainText()
        assert "secret" in out
        assert "key" in out
        assert "st3g0_saurus_wr3cks" in out
        assert "b1,rgb,lsb,xy" in out

    def test_main_window_lsb_chain_shows_full_text(self, qtbot):
        """主窗口跑 lsb chain -> output 含整段 LSB text (不只 flag_candidate)."""
        if not Path("Challenge/steg.png").exists():
            pytest.skip("Challenge/steg.png not found")

        from PySide6.QtWidgets import QApplication

        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = Path("Challenge/steg.png")

        # 等 finished_with_context 信号 (避免 race: isRunning()=False 时 slot 还没排到事件循环)
        signal_received = {"flag": False}
        window._chain_runner = None
        window._run_chain("lsb")
        runner = window._chain_runner
        assert runner is not None
        runner.finished_with_context.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=30_000)
        QApplication.processEvents()

        out = window.output_view.toPlainText()
        # 整段 LSB text 应在 output (Bug 3 修复目标)
        assert "Hey I think" in out
        assert "secret" in out
        assert "st3g0_saurus_wr3cks" in out
        # 同时 flag_candidate 也应在 (per v0.5-LSB-router)
        assert "FLAG CANDIDATE" in out
