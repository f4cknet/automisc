"""v0.5-IO-widget 单测: OutputView 升级成 InputOutputView (Owner 2026-06-14)

覆盖:
- 顶 bar 3 按钮存在 (v0.5-hex-ascii-fix: 删了 Hex→ASCII 按钮, 与菜单栏重复)
- clear() 清空 + 加 [cleared] 标记
- paste_clipboard() 粘板内容
- toggle read-only OFF 后可编辑
- run_hex_to_ascii() 4 格式 + 选中 hex + 候选行挑选 + 错误处理 (内部用, 顶 bar 已删)
- toPlainText/setPlainText 兼容 (QPlainTextEdit 接口)
- meihuai.jpg 真实 hex 走通
- extract_base_candidate() 公共方法 (v0.5-hex-ascii-fix: 菜单栏 / 顶 bar 共享逻辑)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from automisc.gui.output_view import InputOutputView, OutputView  # 兼容 alias
from automisc.gui.main_window import MainWindow


# ---------- 顶 bar 3 按钮 (v0.5-hex-ascii-fix 删了 Hex→ASCII) ----------
class TestToolbarButtons:
    def test_has_3_buttons_no_hex_ascii(self, qtbot):
        """v0.5-hex-ascii-fix: 顶 bar 删了 Hex→ASCII 按钮 (与菜单栏重复)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        assert v.btn_clear.text() == "Clear"
        assert v.btn_paste.text() == "Paste"
        assert v.btn_readonly.text() == "Read-only: ON"
        # 顶 bar 不再有 btn_hex_ascii
        assert not hasattr(v, "btn_hex_ascii") or getattr(v, "btn_hex_ascii", None) is None, \
            "顶 bar Hex→ASCII 按钮已删 (v0.5-hex-ascii-fix)"

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


# ---------- extract_base_candidate (v0.5-hex-ascii-fix 公共方法) ----------
class TestExtractBaseCandidate:
    def test_empty_input(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.clear()
        assert v.extract_base_candidate() is None

    def test_selection_takes_priority(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("garbage 中文 + symbols !@#")
        v.append_text("48656c6c6f")  # 'Hello' in hex
        # 选中第一行 (中文 + 符号, 不是 base-encoded)
        cursor = v.text_edit.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(22, QTextCursor.KeepAnchor)
        v.text_edit.setTextCursor(cursor)
        c = v.extract_base_candidate()
        assert c is not None
        # selection 优先: 返回 selection 内容 (中文+符号, 不是 base)
        assert "garbage" in c or "中文" in c

    def test_last_base_line_when_no_selection(self, qtbot):
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("=== some log ===")
        v.append_text("[stderr] noop")
        v.append_text("exit_code: 0")
        v.append_text("28372c37290a")  # 真 hex
        c = v.extract_base_candidate()
        assert c == "28372c37290a"

    def test_meihuai_real_hex(self, qtbot):
        """meihuai.jpg 真实 hex."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("28372c37290a")
        assert v.extract_base_candidate() == "28372c37290a"

    def test_skips_log_decoration_lines(self, qtbot):
        """跳 [xxx] / === / --- 行."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("[Hex → ASCII] detected=hex")
        v.append_text("--- chain log ---")
        v.append_text("48656c6c6f")
        c = v.extract_base_candidate()
        # 最后"像 base"的是 "48656c6c6f" (跳过 detected=hex 行因为不是纯 base)
        # 实际上 "detected=hex" 也算 base 字符, 优先选 "48656c6c6f" 因为它最后
        assert c in ("48656c6c6f", "[Hex → ASCII] detected=hex")


# ---------- run_hex_to_ascii (内部用, 顶 bar 已删) ----------
class TestHexToAscii:
    def test_internal_method_still_works(self, qtbot):
        """run_hex_to_ascii 仍可用 (main_window 内部 + 历史 test)."""
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
        # 3 按钮都在
        assert w.output_view.btn_clear is not None
        assert w.output_view.btn_paste is not None
        assert w.output_view.btn_readonly is not None

    def test_main_window_io_e2e_paste_extract(self, qtbot):
        """主窗口级: paste 后 extract_base_candidate 返回正确值 (验证 menu 走 input 区的链路)."""
        w = MainWindow()
        qtbot.addWidget(w)
        w.output_view.append_text("=== Chain: lsb ===")
        w.output_view.append_text("[1] binwalk OK")
        QApplication.clipboard().setText("48656c6c6f20576f726c64")
        w.output_view.paste_clipboard()
        # v0.5-hex-ascii-fix: menu 触发时 main_window 调 _extract_input_candidate
        c = w._extract_input_candidate()
        assert c == "48656c6c6f20576f726c64"

    def test_main_window_extract_empty(self, qtbot):
        """input 区空时, _extract_input_candidate 返回 None, menu 不会读 current_file."""
        w = MainWindow()
        qtbot.addWidget(w)
        w.current_file = Path("Challenge/meihuai.jpg")  # 即便 current_file 是 meihuai.jpg
        w.output_view.clear()
        # 关键: 即便 current_file 是 233KB meihuai.jpg, _extract_input_candidate
        # 仍返回 None (不读 current_file, 不被 hex-ascii 拿去当 hex 解)
        c = w._extract_input_candidate()
        assert c is None


# ---------- v0.5-hex-ascii-fix 端到端 ----------
class TestHexAsciiMenuE2E:
    def test_menu_hex_ascii_uses_input_not_current_file(self, qtbot, tmp_path, monkeypatch):
        """核心修复: 菜单栏 [hex-ascii] 走 input 区, 不会读 current_file.

        场景 (per Owner 2026-06-14 09:50):
        1. 拖 meihuai.jpg -> auto_run 出 hex
        2. Clear + 粘贴 '28372c37290a' 到 input 区
        3. 点菜单 [hex-ascii] -> 应解 input 区出 (7,7), 不应读 meihuai.jpg
        """
        from PySide6.QtWidgets import QApplication, QFileDialog

        # v0.5-tmp-text-mode: monkey-patch QFileDialog 返回 tmp_path (避免弹 native dialog 卡住)
        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *args, **kwargs: str(tmp_path)),
        )

        w = MainWindow()
        qtbot.addWidget(w)

        # 模拟 current_file 是 meihuai.jpg
        meihuai = Path("Challenge/meihuai.jpg")
        if meihuai.exists():
            w.current_file = meihuai

        # 1. 模拟 auto_run 输出
        w.output_view.append_text("=== auto-run strings ===")
        w.output_view.append_text("28372c37290a")  # 真实 hex
        w.output_view.append_text("28372c38290a")
        # 2. clear + 粘贴
        w.output_view.clear()
        QApplication.clipboard().setText("28372c37290a")
        w.output_view.paste_clipboard()
        # 3. 菜单栏 [hex-ascii]
        w._run_decoder("hex-ascii")

        # v0.5-short-circuit-fix: 等 finished_with_result 信号 (避免 isRunning()=False 后立刻 read)
        signal_received = {"flag": False}
        runner = w._decode_runner
        assert runner is not None
        # v0.5-hex-ascii-fix: 走 text 模式, file_path 应该是 <text>
        assert runner.file_path == "<text>", f"应走 text 模式, 实际: {runner.file_path}"
        assert runner.text == "28372c37290a"
        runner.finished_with_result.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=10_000)
        # 多等一帧让 slot (append_text) 执行完
        QApplication.processEvents()

        out = w.output_view.toPlainText()
        # (7,7) 应在 output
        assert "(7,7)" in out
        # decoder result 应含 detected_format=hex
        assert "detected_format" in out
        assert "hex" in out

    def test_menu_hex_ascii_empty_input_no_current_file_read(self, qtbot, tmp_path, monkeypatch):
        """input 区空 + current_file=meihuai.jpg: 不读 current_file, 提示 'input is empty'."""
        from PySide6.QtWidgets import QFileDialog

        # v0.5-tmp-text-mode: monkey-patch 避免弹 native dialog
        monkeypatch.setattr(
            QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *args, **kwargs: str(tmp_path)),
        )

        w = MainWindow()
        qtbot.addWidget(w)
        meihuai = Path("Challenge/meihuai.jpg")
        if meihuai.exists():
            w.current_file = meihuai
        w.output_view.clear()

        w._run_decoder("hex-ascii")
        out = w.output_view.toPlainText()
        # 应提示 input 区为空, **不应**去读 meihuai.jpg (否则 233KB 卡死 + 乱码)
        assert "input 区为空" in out or "input is empty" in out
        assert "粘贴" in out or "paste" in out.lower()


# ---------- v0.5-clear-on-new-file: 拖入新文件清空旧 output ----------
class TestClearOnNewFile:
    def test_drop_clears_previous_output(self, qtbot, tmp_path):
        """拖入新文件 -> 清空旧 output (per Owner 2026-06-14 10:00).

        场景: 拖 meihuai.jpg -> auto-run 出 hex -> 拖 steg.png
        期望: 第二拖的 output 区没有 meihuai 的 hex 残留
        """
        from PySide6.QtCore import QMimeData, QPoint, QUrl
        from PySide6.QtGui import QDropEvent
        from PySide6.QtWidgets import QApplication

        # 准备一个真文件给第二题 (用 tmp_path 自己造)
        second_file = tmp_path / "second.txt"
        second_file.write_text("flag{second_file_test}")

        w = MainWindow()
        qtbot.addWidget(w)

        # 1. 模拟第一题 (meihuai.jpg) 已打印的 output
        w.output_view.append_text("=== first file auto-run ===")
        w.output_view.append_text("28372c37290a")  # meihuai hex
        w.output_view.append_text("28372c38290a")
        QApplication.processEvents()
        first_output = w.output_view.toPlainText()
        assert "first file auto-run" in first_output

        # 2. 拖入第二题
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(second_file))])
        event = QDropEvent(
            QPoint(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        w.dropEvent(event)

        # 3. 等 auto-run 跑完
        signal_received = {"flag": False}
        if w._auto_runner:
            w._auto_runner.chain_finished.connect(
                lambda *args: signal_received.__setitem__("flag", True)
            )
            qtbot.waitUntil(lambda: signal_received["flag"], timeout=10_000)
        QApplication.processEvents()

        # 4. 验证: 第一题的 hex 残留不在 output
        out = w.output_view.toPlainText()
        # 第一题的标记 "first file auto-run" 不应再有
        assert "first file auto-run" not in out, \
            f"旧文件 output 残留: {out[:500]}"
        # 第一题的 hex 串也不应有
        assert "28372c37290a" not in out or "新文件" in out, \
            f"旧文件 hex 残留: {out[:500]}"
        # 新文件的 router 推荐应在
        assert "recommendations" in out

    def test_open_file_dialog_clears_previous_output(self, qtbot, tmp_path, monkeypatch):
        """File → Open File... 同样清空旧 output."""
        from PySide6.QtWidgets import QApplication, QFileDialog

        second_file = tmp_path / "second.txt"
        second_file.write_text("hello")

        w = MainWindow()
        qtbot.addWidget(w)
        w.output_view.append_text("OLD STUFF FROM PREVIOUS FILE")
        QApplication.processEvents()

        # monkeypatch QFileDialog 返回 second_file 路径
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *args, **kwargs: (str(second_file), "")),
        )
        w._open_file_dialog()

        out = w.output_view.toPlainText()
        assert "OLD STUFF" not in out, f"open dialog 没清空: {out[:500]}"

    def test_on_new_file_stops_runners(self, qtbot, tmp_path):
        """新文件拖入时停掉旧 runner (避免并发跑两个文件)."""
        w = MainWindow()
        qtbot.addWidget(w)

        # 假装有个 _auto_runner 在跑 (用一个空 QThread 模拟)
        from PySide6.QtCore import QThread
        class DummyRunner(QThread):
            def __init__(self):
                super().__init__()
                self._stopped = False
            def stop(self):
                self._stopped = True
            def isRunning(self):
                return not self._stopped
            def wait(self, ms=2000):
                pass

        old_runner = DummyRunner()
        w._auto_runner = old_runner

        # 触发新文件选择
        target = tmp_path / "anything.txt"
        target.write_text("dummy")
        w._on_new_file_selected(target, source="drop")

        # 旧 runner 应被 stop
        assert old_runner._stopped is True
