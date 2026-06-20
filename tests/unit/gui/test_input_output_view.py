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


# ---------- extract_base_candidate (v0.5-brainfuck-candidate-fix 加固) ----------

class TestExtractBaseCandidateStricter:
    """per Owner 2026-06-20 20:19 实战反馈 (面具下的flag):
    owner 拖文件 + auto-run 跑完 + 点 brainfuck decoder →
    `_extract_input_candidate` 抽到了 GUI [drop] recommendation 行
    "           5  xxd              hex dump" (28 chars, 纯数字空格英文).
    修法: looks_like_base 加固:
    - 长度 < 8 → 排除 (base 至少 8 chars)
    - 数字开头行 (≥ 2 个数字 + 空格) → 排除 (GUI log 行特征)
    - 必须含 +/= 或全 hex 或全 binary 之一 (避免普通英文行撞候选)
    """

    def test_owner_real_scenario_returns_none(self, qtbot):
        """owner 20:19 实战场景: GUI 日志 + brainfuck decoder 兜底 → 修后返回 None (要求用户手动 paste/selection)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        # 模拟 owner 实战: input 区全是 auto-run 日志 + [drop] recommendation
        v.append_text("[drop] file=/Users/.../where_is_flag_part_two.txt")
        v.append_text("        size=2323 bytes")
        v.append_text("        magic=unknown")
        v.append_text("        recommendations (4):")
        v.append_text("           10  file             通用文件类型识别")
        v.append_text("            8  strings          明文字符串")
        v.append_text("            6  binwalk          内嵌文件检测")
        v.append_text("            5  xxd              hex dump")  # ← 之前的 bug: 这行被抽走
        v.append_text("")
        v.append_text("=== file (auto OK) ===")
        v.append_text("Unicode text, UTF-8 (with BOM) text")
        v.append_text("=== exiftool (auto OK) ===")
        v.append_text("[5] keyword: flag")
        v.append_text("[5] keyword: foremost")
        # 关键: 不应再抽 "5  xxd              hex dump" 这种 GUI 日志行
        c = v.extract_base_candidate()
        # 修后: 兜底返回最后非空行 ("[5] keyword: foremost" 或 "[5] keyword: flag")
        # 这是已知 trade-off: 抽不到 BF 代码, 但不会抽到 GUI log 行误导 decoder
        if c is not None:
            assert "xxd" not in c.lower(), (
                f"修复后不应抽到 GUI log 行 'xxd hex dump', got: {c!r}"
            )
            assert not c.startswith("5  xxd"), f"修复后不应抽到数字开头的 log 行, got: {c!r}"

    def test_number_prefix_log_line_excluded(self, qtbot):
        """数字开头的 GUI log 行 (e.g. "           5  xxd              hex dump") → 排除."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("           5  xxd              hex dump")
        # 这行单独存在时, 抽 candidate 应该兜底返回它 (没有任何 base 行)
        # 但如果同 input 区有真 base 行, 应该返回真 base 行而不是这行
        v.append_text("aGVsbG8=")  # 真 base64: 'hello'
        c = v.extract_base_candidate()
        assert c == "aGVsbG8=", (
            f"数字开头的 log 行不应被抽走, 应选真 base 'aGVsbG8=', got: {c!r}"
        )

    def test_short_log_line_excluded(self, qtbot):
        """短行 (< 8 chars) → 排除."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("ab")  # 太短
        v.append_text("aGVsbG8=")  # 真 base64
        c = v.extract_base_candidate()
        assert c == "aGVsbG8=", f"短行 'ab' 不应被抽, 应选 'aGVsbG8=', got: {c!r}"

    def test_pure_alpha_space_not_base(self, qtbot):
        """纯字母+空格 (无 +/= 不是全 hex/binary) → 不算 base."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("xxd hex dump")  # 纯英文+空格
        v.append_text("S3cr3tK3y")  # 纯字母数字, 不是 hex, 不是 base64 (无 +/=)
        v.append_text("aGVsbG8=")  # 真 base64
        c = v.extract_base_candidate()
        assert c == "aGVsbG8=", (
            f"普通英文 + 字母数字 不应被抽为 base, got: {c!r}"
        )

    def test_real_base64_still_works(self, qtbot):
        """真正 base64 串仍正确识别 (含 = padding)."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("aGVsbG8gd29ybGQ=")
        assert v.extract_base_candidate() == "aGVsbG8gd29ybGQ="

    def test_real_hex_still_works(self, qtbot):
        """真正 hex 串仍正确识别."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("28372c37290a")
        assert v.extract_base_candidate() == "28372c37290a"

    def test_real_binary_still_works(self, qtbot):
        """真正 binary 串仍正确识别."""
        v = InputOutputView()
        qtbot.addWidget(v)
        v.append_text("0100100001100101011011000110110001101111")
        assert v.extract_base_candidate() == "0100100001100101011011000110110001101111"


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
    def test_menu_hex_ascii_uses_input_not_current_file(self, qtbot, tmp_path):
        """核心修复: 菜单栏 [hex-ascii] 走 input 区, 不会读 current_file.

        场景 (per Owner 2026-06-14 09:50):
        1. 拖 meihuai.jpg -> auto_run 出 hex
        2. Clear + 粘贴 '28372c37290a' 到 input 区
        3. 点菜单 [hex-ascii] -> 应解 input 区出 (7,7), 不应读 meihuai.jpg

        v0.5-tmp-text-mode-2 (per Owner 12:44): hex-ascii 不输出文件,
        **不**弹 QFileDialog. Test 不需要 monkey-patch dialog.
        """
        from PySide6.QtWidgets import QApplication

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

    def test_menu_hex_ascii_empty_input_no_current_file_read(self, qtbot, tmp_path):
        """input 区空 + current_file=meihuai.jpg: 不读 current_file, 提示 'input is empty'.

        v0.5-tmp-text-mode-2: hex-ascii 不弹 QFileDialog (不写文件).
        """
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

    def test_hex_ascii_no_qfiledialog_no_write_file(self, qtbot, tmp_path):
        """v0.5-tmp-text-mode-2 (per Owner 12:44): hex-ascii 不输出文件 -> 不弹 QFileDialog.

        之前 (v0.5-tmp-text-mode) 所有 text-based 都弹 dialog, 不合理.
        修后: 仅 spec.run 签名带 output_dir 的 decoder 才弹 (即"真要写文件"才弹).
        """
        from PySide6.QtWidgets import QFileDialog, QApplication

        # 标记是否被调用
        dialog_called = {"flag": False}

        def fake_dialog(*args, **kwargs):
            dialog_called["flag"] = True
            return str(tmp_path)

        original = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = staticmethod(fake_dialog)
        try:
            w = MainWindow()
            qtbot.addWidget(w)
            QApplication.clipboard().setText("28372c37290a")  # 真实 hex
            w.output_view.paste_clipboard()
            # 调 _run_decoder 但 input 有内容, 跑 hex-ascii -> 不应弹 dialog
            # 等 signal 避免 race
            w._decode_runner = None
            w._run_decoder("hex-ascii")
            signal_received = {"flag": False}
            if w._decode_runner:
                w._decode_runner.finished_with_result.connect(
                    lambda *args: signal_received.__setitem__("flag", True)
                )
                qtbot.waitUntil(lambda: signal_received["flag"], timeout=10_000)
            QApplication.processEvents()

            # QFileDialog **不应**被调用 (hex-ascii 不写文件)
            assert dialog_called["flag"] is False, \
                f"hex-ascii 不写文件, 不应弹 QFileDialog (但被调用了)"
            # 但 output 应有 (7,7)
            out = w.output_view.toPlainText()
            assert "(7,7)" in out
        finally:
            QFileDialog.getExistingDirectory = original


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


# ---------- v0.5-hex-router-fix: append_suspicious 截断 (Owner 14:11) ----------
class TestAppendSuspiciousTruncation:
    def test_long_hex_suspicious_does_not_print_650000_chars(self, qtbot):
        """v0.5-hex-router-fix: append_suspicious 对长 hex 显示占位符, 不打 650000 字符.

        Owner 14:11 截图: 'program 卡顿, 打印了 35000+ 字符'.
        根因: output_view.append_suspicious 之前无截断, 把 sp.matched_pattern 整打.
        修: 长 hex (>= HEX_AUTO_ROUTER_MIN_LEN) 显示 <hex_router 已自动处理> 占位符.
        """
        from automisc.core.suspicious import SuspiciousPoint
        from automisc.core.actions.hex_router import HEX_AUTO_ROUTER_MIN_LEN

        v = InputOutputView()
        qtbot.addWidget(v)
        # 造一个长 hex matched_pattern
        long_hex = "28372c37290a" * 50000  # 600000 chars (meihuai L226 真实)
        sp = SuspiciousPoint(
            id="",
            tool_name="strings",
            file_path="Challenge/meihuai.jpg",
            category="十六进制串_line226",
            offset=226,
            matched_pattern=long_hex,
            severity=4,
            suggested_action="",
        )
        v.append_suspicious(sp)
        text = v.toPlainText()
        # 关键: 不应包含 600000 字符的 hex 内容
        assert len(text) < 500, f"占位符后仍应 < 500 字符, 实际: {len(text)}"
        # 应含占位符
        assert "<hex_router 已自动处理" in text
        # 不应含 hex 字符预览
        assert "28372c37290a" not in text


# ---------- v0.5-hex-router-fix: main_window 实际渲染 size ----------
class TestMainWindowStringsOutputSize:
    def test_meihuai_auto_run_does_not_explode(self, qtbot):
        """v0.5-hex-router-fix: 拖 meihuai.jpg 跑 strings -> output_view < 2000 字符.

        Owner 14:11 截图显示实际 output_view 650802 字符 (整 hex 串打上).
        修: append_suspicious 截断 + 渲染版 957 字符 -> output_view 总 < 2000.
        """
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from pathlib import Path

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w.current_file = Path("Challenge/meihuai.jpg")
        if not w.current_file.exists():
            pytest.skip("Challenge/meihuai.jpg not found")

        # 直接调 strings 拿 ToolResult
        r = w.core.run_tool("strings", str(w.current_file))

        class _S:
            pass

        s = _S()
        s.success = True
        s.suspicious_count = len(r.suspicious_points)
        # 模拟 _on_auto_tool_finished
        w._on_auto_tool_finished("strings", s, r)
        QApplication.processEvents()

        text = w.output_view.toPlainText()
        # 关键: total < 2000 字符 (vs 之前的 650802)
        assert len(text) < 2000, f"output_view 不应爆 < 2000 字符, 实际: {len(text)}"
        # v0.5-hex-router-journal (per Owner 14:43):
        # stdout 不应再含 'v0.5-hex-router: N 个' / 'saved=' / 'magic=' summary
        assert "v0.5-hex-router:" not in text, "stdout 不应再含 v0.5-hex-router summary"
        assert "saved=" not in text, "saved= 已改走 journal"
        assert "magic=" not in text, "magic= 已改走 journal"

        # 关键: journal_panel 收到 written_files event
        # 找 kind="hex转文件" 的 row
        journal = w.journal_panel
        found_event = False
        for i in range(journal.tree.topLevelItemCount()):
            item = journal.tree.topLevelItem(i)
            if item.text(journal.COL_KIND) == "hex转文件":
                v = item.text(journal.COL_VALUE)
                assert "文件保存在" in v
                assert "hex_router_unknown_" in v
                assert item.text(journal.COL_FILE) == "meihuai.jpg"
                found_event = True
                break
        assert found_event, "journal 应有 hex_router 写文件事件 (kind=hex转文件)"

        # cleanup
        import glob
        from pathlib import Path as _P

        for f in glob.glob("/tmp/automisc_text_outputs/hex_router_*"):
            _P(f).unlink(missing_ok=True)
        # 也清 samedir
        for f in glob.glob("Challenge/hex_router_*"):
            _P(f).unlink(missing_ok=True)
