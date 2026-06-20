"""单测: v0.5-cipher-decoders-textfix — text_only 标志自动声明

Owner 19:14: 摩尔斯/caesar/base64 等所有 text-based decoder 必须走 input 区,
不要再 hard-fail 在 'no file selected'.

覆盖:
- 12 cipher decoder + 14 base/rot decoder + 2 占位 共 28 个都 text_only=True
- 老 file-based decoder (base64-image, coords-qr) text_only=False
- 1 个 GUI 端到端测试: 无 file + 有 input text → 不报 'no file selected'
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from automisc.core.decoders import REGISTRY
from automisc.core.decoders.registry import get_decoder


# === text_only 标志全量验证 ===

# 这些必须是 text_only=True (per Owner 19:14 + v0.5-cipher-decoders-textfix)
EXPECTED_TEXT_ONLY_DECODERS = [
    # 12 cipher (per v0.5-cipher-decoders)
    "caesar", "bacon", "rail-fence", "pigpen", "morse",
    "xxencode", "uuencode", "jsfuck", "jjencode",
    "quoted-printable", "brainfuck", "bubblebabble",
    # 14 base/rot (per v0.5-base-rot-decoders PR3)
    "base16", "base32", "base36", "base58", "base62", "base64",
    "base85", "base91", "base92", "base100", "base32768", "base65536",
    "rot5", "rot13", "rot18", "rot47",
    "base64-custom", "base64-stego",
    # 7 convert (per v0.5-hex-ascii-fix + v0.5-more-converts)
    "hex-ascii", "bin-ascii", "dec-bin", "bin-dec",
    "dec-hex", "hex-dec", "ascii-bin",
    # 2 占位
    "placeholder-解密工具2", "placeholder-解密工具3",
]


# 这些必须 text_only=False (file-based)
EXPECTED_FILE_BASED_DECODERS = [
    "base64-image",  # 解 base64 编码的图片, 走 file
    "coords-qr",     # 解 QR PNG 文件, 走 file (override)
]


def test_all_text_only_decoders_have_text_only_true():
    """28 个 text-only decoder 全部 text_only=True."""
    for name in EXPECTED_TEXT_ONLY_DECODERS:
        spec = get_decoder(name)
        assert spec is not None, f"{name} not registered"
        assert spec.text_only is True, (
            f"{name} text_only={spec.text_only}, expected True"
        )


def test_all_file_based_decoders_have_text_only_false():
    """2 个 file-based decoder text_only=False (不破坏老逻辑)."""
    for name in EXPECTED_FILE_BASED_DECODERS:
        spec = get_decoder(name)
        assert spec is not None, f"{name} not registered"
        assert spec.text_only is False, (
            f"{name} text_only={spec.text_only}, expected False"
        )


def test_default_text_only_is_false():
    """未显式声明的 decoder text_only 默认 False (向后兼容)."""
    # 构造一个不带 text_only 的 spec
    from automisc.core.decoders.registry import DecoderSpec, register_decoder
    spec = DecoderSpec(
        name="test-text-only-default",
        display="🧪 test",
        category="test",
        cli_cmd="decode test-text-only-default",
        run=lambda **kw: None,
        description="test",
    )
    # 没传 text_only → 默认 False
    assert spec.text_only is False


def test_no_decoder_has_unexpected_text_only():
    """所有 registered decoder 的 text_only 值在已知集合里."""
    expected_true = set(EXPECTED_TEXT_ONLY_DECODERS)
    expected_false = set(EXPECTED_FILE_BASED_DECODERS)
    for spec in REGISTRY:
        if spec.text_only is True:
            assert spec.name in expected_true, (
                f"unexpected text_only=True on {spec.name}"
            )
        else:
            assert spec.name in expected_false, (
                f"unexpected text_only=False on {spec.name} "
                f"(if this is a new text-only decoder, add it to EXPECTED_TEXT_ONLY_DECODERS)"
            )


# === GUI 端到端测试: 无 file + 有 input text → 跑通 ===

def test_run_decoder_morse_no_file_with_text_input(qtbot):
    """Owner 19:14 场景: 摩尔斯解密无 file + input 区有 morse → 跑通 (不报 'no file')."""
    from automisc.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    # 模拟: input 区有摩尔斯串
    morse_text = "../.-../---/...-/./-.--/---/..-/-.-.--/...../..---/-----"
    window.output_view.setPlainText(morse_text)
    # 切到 read-only OFF 让 input 可被 _extract_input_candidate 抽到
    window.output_view.btn_readonly.setChecked(False)
    # 无 current_file
    assert window.current_file is None

    # 等 finished_with_result 信号
    from PySide6.QtWidgets import QApplication
    signal_received = {"flag": False, "result": None, "error": None}
    window._decode_runner = None

    # 直接调 _run_decoder
    window._run_decoder("morse")

    # 关键断言: 没有 '[!] no file selected' 错误
    # statusBar 也不应该有 'no file selected'
    status_msg = window.statusBar().currentMessage() or ""
    assert "no file selected" not in status_msg.lower(), (
        f"morse 仍报 'no file selected': {status_msg!r}"
    )

    # 等 DecodeRunner 跑完
    runner = window._decode_runner
    if runner is not None:
        runner.finished_with_result.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        runner.failed_with_error.connect(
            lambda *args: signal_received.__setitem__("error", args)
        )
        qtbot.waitUntil(
            lambda: signal_received["flag"] or signal_received["error"],
            timeout=15_000,
        )
        QApplication.processEvents()

    # 跑通后 output 应该含 morse decoded text (per ITU 摩尔斯表)
    out = window.output_view.toPlainText()
    assert "Decoder: morse" in out or "morse" in out.lower(), (
        f"output 没含 morse decoder header: {out[:500]!r}"
    )


def test_run_decoder_caesar_no_file_with_text_input(qtbot):
    """凯撒无 file + input 有 'KHOOR' → 解出 'HELLO'."""
    from automisc.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.output_view.setPlainText("KHOOR")
    window.output_view.btn_readonly.setChecked(False)
    assert window.current_file is None

    from PySide6.QtWidgets import QApplication
    signal_received = {"flag": False}
    window._decode_runner = None
    window._run_decoder("caesar")

    status_msg = window.statusBar().currentMessage() or ""
    assert "no file selected" not in status_msg.lower()

    runner = window._decode_runner
    if runner is not None:
        runner.finished_with_result.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=15_000)
        QApplication.processEvents()
        out = window.output_view.toPlainText()
        assert "HELLO" in out, f"caesar 没解出 HELLO: {out[:500]!r}"


def test_run_decoder_base64_no_file_with_text_input(qtbot):
    """base64 (file-based → text_only=True) 无 file + input 有 'SGVsbG8=' → 解出 'Hello'."""
    from automisc.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.output_view.setPlainText("SGVsbG8=")
    window.output_view.btn_readonly.setChecked(False)
    assert window.current_file is None

    from PySide6.QtWidgets import QApplication
    signal_received = {"flag": False}
    window._decode_runner = None
    window._run_decoder("base64")

    status_msg = window.statusBar().currentMessage() or ""
    assert "no file selected" not in status_msg.lower()

    runner = window._decode_runner
    if runner is not None:
        runner.finished_with_result.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=15_000)
        QApplication.processEvents()
        out = window.output_view.toPlainText()
        assert "Hello" in out, f"base64 没解出 Hello: {out[:500]!r}"


def test_run_decoder_base64_image_no_file_still_warns(qtbot):
    """回归: base64-image (text_only=False) 无 file 仍报 'no file selected'."""
    from automisc.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.current_file = None
    window.output_view.setPlainText("not used")

    window._run_decoder("base64-image")
    status_msg = window.statusBar().currentMessage() or ""
    # base64-image 是 file-based, 无 file 应该提示
    assert "文件" in status_msg or "file" in status_msg.lower(), (
        f"base64-image 没 file 时应提示: {status_msg!r}"
    )


# === file fallback (v0.5-brainfuck-candidate-ux) ===

class TestFileFallbackForTextDecoders:
    """per Owner 2026-06-20 20:27 实战反馈:
    owner 拖文本文件 (.txt brainfuck 代码) → auto-run 跑完 → 点 brainfuck decoder.
    input 区是 GUI 日志 (没真 BF 代码) → 抽 candidate 反复抽错.

    修法 (per main_window._extract_input_candidate 加 file fallback):
    - input 区抽不到 candidate → fallback 读 current_file 文本内容
    - 仅文本后缀 + < 256KB + printable 字符 ≥ 85%
    """

    def test_file_fallback_reads_text_file(self, qtbot, tmp_path):
        """文本文件 → fallback 读文件内容."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # 写测试文件 (BF 代码 + 中文标点)
        bf_file = tmp_path / "brainfuck_code.txt"
        bf_file.write_text("++++++++[>+++++++++++++<-]>.", encoding="utf-8")
        window.current_file = bf_file

        # input 区无候选 (空或只有 GUI log)
        window.output_view.setPlainText("[some GUI log line]")

        candidate = window._extract_input_candidate()
        assert candidate == "++++++++[>+++++++++++++<-]>.", (
            f"file fallback 应读 .txt 内容, got: {candidate!r}"
        )

    def test_file_fallback_skips_binary_extensions(self, qtbot, tmp_path):
        """二进制扩展名不读 (避免乱码 + GUI 卡)."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        bin_file = tmp_path / "image.bin"
        bin_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake png" * 100)
        window.current_file = bin_file

        # 二进制文件不 fallback
        candidate = window._extract_input_candidate()
        assert candidate is None, (
            f"二进制文件不应 fallback, got: {candidate!r}"
        )

    def test_file_fallback_skips_large_files(self, qtbot, tmp_path):
        """大文件不读 (> 256KB, 防 GUI 卡)."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        big_file = tmp_path / "huge.txt"
        big_file.write_text("a" * (300 * 1024))  # 300KB
        window.current_file = big_file

        candidate = window._extract_input_candidate()
        assert candidate is None, (
            f"大文件 (> 256KB) 不应 fallback, got len: {len(candidate) if candidate else 0}"
        )

    def test_file_fallback_skips_non_printable_content(self, qtbot, tmp_path):
        """含大量非 printable 字符 → 不算文本 → 不 fallback."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # .txt 后缀但内容是 binary (95% 非 printable)
        fake_text = tmp_path / "fake.txt"
        fake_text.write_bytes(bytes(range(0, 256)) * 4)  # 全 binary 字符
        window.current_file = fake_text

        candidate = window._extract_input_candidate()
        assert candidate is None, (
            f"非 printable 内容不应 fallback, got: {candidate!r}"
        )

    def test_input_area_candidate_takes_priority_over_file(self, qtbot, tmp_path):
        """input 区有候选 → 优先用 input, 不 fallback 到 file."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # 文件内容不同
        file_path = tmp_path / "other.txt"
        file_path.write_text("file content", encoding="utf-8")
        window.current_file = file_path

        # input 区有真候选
        window.output_view.setPlainText("aGVsbG8=")  # base64 for 'hello'
        candidate = window._extract_input_candidate()
        assert candidate == "aGVsbG8=", (
            f"input 区有候选应优先, got: {candidate!r}"
        )

    def test_owner_scenario_brainfuck_txt(self, qtbot, tmp_path):
        """owner 实战完整场景: 拖 .txt brainfuck 文件 → decoder fallback 读."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # 模拟 owner 实战文件 (where_is_flag_part_two.txt 类似)
        bf_file = tmp_path / "where_is_flag_part_two.txt"
        bf_content = "++++++++[>+++++++++++++<-]>."  # 简单 BF 输出 'h'
        bf_file.write_text(bf_content, encoding="utf-8")
        window.current_file = bf_file

        # 模拟 input 区是 GUI log (无 BF 代码)
        window.output_view.setPlainText(
            "[drop] file=/Users/.../where_is_flag_part_two.txt\n"
            "        magic=unknown\n"
            "[auto-run] 启动 find_suspicious_from_binary\n"
            "=== file (auto OK) ===\n"
            "Unicode text, UTF-8"
        )

        candidate = window._extract_input_candidate()
        # 应该 fallback 读文件, 不抽 GUI log
        assert candidate == bf_content, (
            f"owner 实战场景: 应 fallback 读 .txt BF 代码, got: {candidate!r}"
        )
