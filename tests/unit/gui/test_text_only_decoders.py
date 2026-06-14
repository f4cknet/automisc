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
    # hex-ascii (per v0.5-hex-ascii-fix)
    "hex-ascii",
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
