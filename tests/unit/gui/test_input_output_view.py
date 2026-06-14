"""v0.5-IO-widget 单测: OutputView 升级成 InputOutputView (Owner 2026-06-14)

覆盖:
- 顶 bar 4 按钮存在
- clear() 清空 + 加 [cleared] 标记
- paste_clipboard() 粘板内容
- toggle read-only OFF 后可编辑
- run_hex_to_ascii() 4 格式 + 选中 hex + 候选行挑选 + 错误处理
- toPlainText/setPlainText 兼容 (QPlainTextEdit 接口)
- meihuai.jpg 真实 hex 走通
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from automisc.gui.output_view import InputOutputView, OutputView  # 兼容 alias
from automisc.gui.main_window import MainWindow


# ---------- 顶 bar 4 按钮 ----------
class TestToolbarButtons:
    def test_has_clear_paste_readonly_hex(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        assert v.btn_clear.text() == "Clear"
        assert v.btn_paste.text() == "Paste"
        assert v.btn_readonly.text() == "Read-only: ON"
        assert "Hex" in v.btn_hex_ascii.text() and "ASCII" in v.btn_hex_ascii.text()

    def test_default_readonly(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        assert v.text_edit.isReadOnly() is True
        assert v.btn_readonly.isChecked() is True

    def test_toggle_readonly(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v._toggle_readonly(False)
        assert v.text_edit.isReadOnly() is False
        assert v.btn_readonly.text() == "Read-only: OFF"
        v._toggle_readonly(True)
        assert v.text_edit.isReadOnly() is True
        assert v.btn_readonly.text() == "Read-only: ON"

    def test_alias_back_compat(self, qtbot):
        """OutputView alias 仍可用 (老 test)."""
        v = OutputView()  # noqa: F841 - 测试 alias
        qtbot.addWidget(v)
        # 不抛错即可


# ---------- clear / paste ----------
class TestClearPaste:
    def test_clear(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("something")
        assert "something" in v.toPlainText()
        v.clear()
        text = v.toPlainText()
        assert "something" not in text
        assert "[cleared]" in text

    def test_paste_from_clipboard(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        cb = QApplication.clipboard()
        cb.setText("deadbeef")
        v.paste_clipboard()
        text = v.toPlainText()
        assert "deadbeef" in text
        assert "[pasted 8 chars]" in text

    def test_paste_empty_clipboard(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        QApplication.clipboard().setText("")
        v.paste_clipboard()
        text = v.toPlainText()
        assert "clipboard is empty" in text

    def test_paste_auto_toggles_readonly(self, qtbot):
        """paste 时如果 read-only, 应自动切到可编辑 (用户意图就是输入)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        assert v.text_edit.isReadOnly() is True
        QApplication.clipboard().setText("hello")
        v.paste_clipboard()
        assert v.text_edit.isReadOnly() is False
        assert "hello" in v.toPlainText()

    def test_paste_replaces_old_content(self, qtbot):
        """paste 总是替代旧内容 (per Owner 2026-06-14 设计: '用户可以删除所有内容, 然后粘新内容')."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("OLD STUFF to be replaced")
        v.append_text("more old stuff")
        QApplication.clipboard().setText("new hex 48656c6c6f")
        v.paste_clipboard()
        text = v.toPlainText()
        assert "OLD STUFF" not in text
        assert "more old" not in text
        assert "new hex 48656c6c6f" in text

    def test_paste_then_hex_button(self, qtbot):
        """典型 meihuai 场景: paste '28372c37290a' 后立即 hex→ASCII 出 (7,7)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        QApplication.clipboard().setText("28372c37290a")
        v.paste_clipboard()
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "(7,7)" in out
        assert "detected=hex" in out


# ---------- run_hex_to_ascii ----------
class TestHexToAscii:
    def test_clear_then_hex_button(self, qtbot):
        """典型流程: Clear -> Paste hex -> Hex→ASCII 按钮."""
        v = InputOutputView()
        qtbot.addWidget(v)

        # 1. 先模拟一些 log (类似拖文件后 auto-run 输出)
        v.append_text("=== some log ===")
        v.append_text("[stderr] noop")
        v.append_text("exit_code: 0")
        v.append_text("suspicious: nothing")
        # 2. clear
        v.clear()
        # 3. paste 自己的 hex
        QApplication.clipboard().setText("48656c6c6f")
        v.paste_clipboard()
        # 4. hex → ASCII
        v.run_hex_to_ascii()

        out = v.toPlainText()
        assert "[Hex → ASCII]" in out
        assert "detected=hex" in out
        assert "Hello" in out

    def test_meihuai_real_hex(self, qtbot):
        """真实题: meihuai.jpg 隐藏 QR 坐标 hex '28372c37290a' → (7,7)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("28372c37290a")
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "(7,7)" in out
        assert "detected=hex" in out

    def test_binary_input(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("0100100001100101011011000110110001101111")
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "detected=binary" in out
        assert "Hello" in out

    def test_base64_input(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("aGVsbG8=")
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "detected=base64" in out
        assert "hello" in out

    def test_invalid_input(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        # 用含中文/标点的输入 (base64 字符集不包括中文)
        v.append_text("你好世界!@#$%^&*()")
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "failed" in out
        assert "无法识别格式" in out

    def test_empty_after_clear(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.clear()
        v.run_hex_to_ascii()
        out = v.toPlainText()
        assert "input is empty" in out

    def test_selection_used_instead_of_last_line(self, qtbot):
        """用户选中的文本优先于最后一行."""
        from PySide6.QtGui import QTextCursor
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("garbage 中文 + symbols !@#")
        v.append_text("48656c6c6f")  # 'Hello' in hex
        # 选中第一行 "garbage 中文 + symbols !@#"
        cursor = v.text_edit.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(22, QTextCursor.KeepAnchor)  # 'garbage 中文 + symbols !'
        v.text_edit.setTextCursor(cursor)
        v.run_hex_to_ascii()
        out = v.toPlainText()
        # selection 含中文+符号, 不是 base-encoded, 必失败
        assert "failed" in out or "无法识别" in out


# ---------- QPlainTextEdit API 兼容 ----------
class TestPlainTextEditCompat:
    def test_toPlainText(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("hello")
        assert "hello" in v.toPlainText()

    def test_setPlainText(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.setPlainText("fresh")
        assert v.toPlainText().strip() == "fresh"

    def test_appendPlainText(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.appendPlainText("line 1")
        v.appendPlainText("line 2")
        assert "line 1" in v.toPlainText()
        assert "line 2" in v.toPlainText()


# ---------- main_window 集成 ----------
class TestMainWindowIntegration:
    def test_main_window_has_input_output_view(self, qtbot):
        w = MainWindow()
        qtbot.addWidget(w)
        assert isinstance(w.output_view, InputOutputView)
        # 4 按钮都在
        assert w.output_view.btn_clear is not None
        assert w.output_view.btn_paste is not None
        assert w.output_view.btn_readonly is not None
        assert w.output_view.btn_hex_ascii is not None

    def test_main_window_io_e2e_clear_paste_hex(self, qtbot):
        """主窗口级: clear + paste + hex 按钮端到端."""
        w = MainWindow()
        qtbot.addWidget(w)

        # 1. 一些 log
        w.output_view.append_text("=== Chain: lsb ===")
        w.output_view.append_text("[1] binwalk OK")
        # 2. paste 模式: 自动清空 + 粘新内容
        QApplication.clipboard().setText("48656c6c6f20576f726c64")  # 'Hello World'
        w.output_view.paste_clipboard()
        # 3. hex→ASCII
        w.output_view.run_hex_to_ascii()

        out = w.output_view.toPlainText()
        assert "[Hex → ASCII]" in out
        assert "Hello World" in out
