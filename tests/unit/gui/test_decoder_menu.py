"""单测: decoder registry + DecodeRunner + GUI Tools 菜单 (v0.5-decoder-menu + v0.5-cipher-decoders)

覆盖:
- registry 注册 / 查找 / 按 category 分组 (老)
- registry 注册 / 查找 / 按 group 分组 (v0.5-cipher-decoders)
- DecodeRunner QThread 异步跑 + signal
- main_window _build_tools_menu 动态生成 (含 group + category 双重渲染)
- 端到端: KEY.exe 走 GUI 路径
- v0.5-cipher-decoders: 3 个 "解密工具1/2/3" submenu 存在, 12 cipher action + 老 submenu 还在
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from automisc.core.decoders.base64_image import decode_file_to_image
from automisc.core.decoders.registry import (
    DecoderSpec,
    REGISTRY,
    get_decoder,
    list_decoders,
    list_decoders_by_category,
    list_decoders_by_group,
    register_decoder,
)


# ---------- registry ----------
class TestRegistry:
    def test_registry_has_base64_image(self):
        """base64-image 应已注册 (在 import base64_image 时触发)."""
        names = [s.name for s in list_decoders()]
        assert "base64-image" in names

    def test_get_decoder(self):
        spec = get_decoder("base64-image")
        assert spec is not None
        assert spec.name == "base64-image"
        assert spec.display == "🔓 Base64 → 图片"
        assert spec.category == "decode"
        assert spec.cli_cmd == "decode base64-image"
        assert spec.run is decode_file_to_image

    def test_get_decoder_unknown(self):
        assert get_decoder("nonexistent-decoder") is None

    def test_list_by_category(self):
        grouped = list_decoders_by_category()
        assert "decode" in grouped
        assert any(s.name == "base64-image" for s in grouped["decode"])

    def test_register_custom_decoder(self):
        """register_decoder 可以加自定义 decoder (per Owner 后续 3 候选)."""
        # 1. 准备一个 dummy runner
        def my_runner(file_path: str) -> object:
            from dataclasses import dataclass

            @dataclass
            class R:
                ok: bool = True
                input: str = file_path

            return R()

        spec = DecoderSpec(
            name="test-decoder",
            display="🧪 Test",
            category="test",
            cli_cmd="decode test-decoder",
            run=my_runner,
            description="unit test stub",
        )
        register_decoder(spec)
        try:
            assert get_decoder("test-decoder") is spec
            assert any(s.name == "test-decoder" for s in list_decoders())
        finally:
            # cleanup
            REGISTRY.remove(spec)


# ---------- CLI dispatcher ----------
class TestCLIDispatcher:
    """CLI `automisc decode <name>` 走 cmd_decode_dispatcher."""

    def test_decode_base64_image_key_exe(self):
        """KEY.exe 走 CLI decode base64-image."""
        import subprocess

        r = subprocess.run(
            [
                sys.executable, "-m", "automisc",
                "decode", "base64-image",
                "--file", "Challenge/KEY.exe",
            ],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        assert r.returncode == 0
        # 输出含 display 标题 + PNG magic
        assert "Base64" in r.stdout
        assert "PNG image" in r.stdout
        assert "133 x 133" in r.stdout

    def test_decode_help_lists_all_decoders(self):
        """decode --help 应自动列出所有注册的 decoder."""
        import subprocess

        r = subprocess.run(
            [sys.executable, "-m", "automisc", "decode", "--help"],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        # 至少含 base64-image + coords-qr
        assert "base64-image" in r.stdout and "coords-qr" in r.stdout

    def test_gui_main_window_triggers_all_decoder_registration(self):
        """v0.5-coords-qr-fix: GUI 启动 (import main_window) 应触发所有 decoder 注册.

        Bug 复现: 之前 GUI 只 import automisc.core.decoders.registry (不触发 __init__.py
        的 side-effect import), 菜单栏 [coords-qr] 触发时报 'unknown decoder: coords-qr'.
        """
        # 重新 import (确保干净状态)
        import importlib
        import automisc.core.decoders
        importlib.reload(automisc.core.decoders)
        import automisc.gui.main_window  # noqa: F401
        from automisc.core.decoders import list_decoders
        names = [s.name for s in list_decoders()]
        # GUI 启动后 3 个 decoder 都应注册
        assert "base64-image" in names
        assert "hex-ascii" in names
        assert "coords-qr" in names, f"GUI 启动后 coords-qr 未注册: {names}"


# ---------- DecodeRunner (QThread) ----------
class TestDecodeRunner:
    def test_decode_runner_base64_image(self, qtbot, sample_key_exe):
        """DecodeRunner 跑 base64-image -> emit finished_with_result."""
        from automisc.gui.decode_runner import DecodeRunner

        results = {}
        runner = DecodeRunner(decoder_name="base64-image", file_path=sample_key_exe)
        runner.finished_with_result.connect(
            lambda n, f, r: results.setdefault("result", r)
        )
        runner.start()
        qtbot.waitUntil(lambda: "result" in results, timeout=10_000)
        runner.wait()

        assert results["result"] is not None
        assert "PNG image" in results["result"].detected_mime

    def test_decode_runner_unknown_decoder(self, qtbot, tmp_path):
        """未知 decoder name -> emit failed_with_error."""
        from automisc.gui.decode_runner import DecodeRunner

        f = tmp_path / "x.txt"
        f.write_text("dummy")

        results = {}
        runner = DecodeRunner(decoder_name="nonexistent-decoder", file_path=str(f))
        runner.failed_with_error.connect(
            lambda n, err: results.setdefault("error", err)
        )
        runner.start()
        qtbot.waitUntil(lambda: "error" in results, timeout=5_000)
        runner.wait()
        assert "unknown decoder" in results["error"]


# ---------- GUI Tools 菜单 ----------
class TestMainWindowToolsMenu:
    def test_tools_menu_has_decode_submenu(self, qtbot):
        """GUI Tools 菜单 -> Decode submenu -> 1 个 base64-image 项."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # 找 Tools 菜单
        tools_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Tools":
                tools_menu = action.menu()
                break
        assert tools_menu is not None, "Tools 菜单未找到"

        # 找 Decode submenu
        decode_submenu = None
        for a in tools_menu.actions():
            if a.text() == "&Decode":
                decode_submenu = a.menu()
                break
        assert decode_submenu is not None, "Decode submenu 未找到"

        # 找 base64-image 项
        base64_action = None
        for a in decode_submenu.actions():
            if "Base64" in a.text() and "图片" in a.text():
                base64_action = a
                break
        assert base64_action is not None, "Base64 → 图片 项未找到"
        assert base64_action.toolTip() != ""  # 至少要 tooltip

    def test_run_decoder_no_file(self, qtbot):
        """无文件时 _run_decoder 报错."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = None

        window._run_decoder("base64-image")
        msg = window.statusBar().currentMessage()
        assert "文件" in msg or "file" in msg.lower()

    def test_run_decoder_e2e(self, qtbot, sample_key_exe):
        """端到端: _run_decoder('base64-image') -> output 渲染 result."""
        from automisc.gui.main_window import MainWindow

        if not Path(sample_key_exe).exists():
            pytest.skip("Challenge/KEY.exe not found")

        window = MainWindow()
        qtbot.addWidget(window)
        window.current_file = Path(sample_key_exe)

        # 等 finished_with_result 信号 (避免 race: isRunning()=False 时 slot 还没排到事件循环)
        signal_received = {"flag": False}
        window._decode_runner = None
        window._run_decoder("base64-image")
        runner = window._decode_runner
        assert runner is not None
        runner.finished_with_result.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=15_000)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        out = window.output_view.toPlainText()
        assert "Decoder: base64-image" in out
        assert "decoder result" in out
        assert "133 x 133" in out
        assert "输出文件" in out


# ---------- v0.5-cipher-decoders: 3 个新 submenu ----------
class TestCipherSubmenus:
    """v0.5-cipher-decoders: Tools 菜单下 3 个新一级目录 (group= 解密工具1/2/3)."""

    def test_tools_menu_has_cipher_group1_submenu(self, qtbot):
        """Tools 菜单 → '解密工具1' submenu 存在 + 含 12 个 cipher action."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # 找 Tools 菜单
        tools_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Tools":
                tools_menu = action.menu()
                break
        assert tools_menu is not None, "Tools 菜单未找到"

        # 找 '解密工具1' submenu
        group1_submenu = None
        for a in tools_menu.actions():
            if a.text() == "&解密工具1":
                group1_submenu = a.menu()
                break
        assert group1_submenu is not None, "'解密工具1' submenu 未找到"

        # 验证含 12 个 cipher action (不含占位 — 占位在 group2/3)
        action_texts = [a.text() for a in group1_submenu.actions()]
        expected = [
            "🔤 凯撒解密", "🥓 培根解密", "🚧 栅栏解密", "🐖 猪圈解密",
            "📡 摩尔斯解密", "✖ xxencode 解密", "📦 uuencode 解密",
            "🤯 JSFuck 解密", "🌀 JJEncode 解密", "🆎 Quoted-printable 解密",
            "🧠 BrainFuck 解密", "🫧 BubbleBabble 解密",
        ]
        for exp in expected:
            assert exp in action_texts, f"{exp} 不在 解密工具1 菜单中"

    def test_tools_menu_has_cipher_group2_submenu(self, qtbot):
        """Tools 菜单 → '解密工具2' submenu 存在 + 占位项."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        tools_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Tools":
                tools_menu = action.menu()
                break
        assert tools_menu is not None

        group2_submenu = None
        for a in tools_menu.actions():
            if a.text() == "&解密工具2":
                group2_submenu = a.menu()
                break
        assert group2_submenu is not None, "'解密工具2' submenu 未找到"
        # 占位项
        action_texts = [a.text() for a in group2_submenu.actions()]
        assert any("占位" in t for t in action_texts)

    def test_tools_menu_has_cipher_group3_submenu(self, qtbot):
        """Tools 菜单 → '解密工具3' submenu 存在 + 占位项."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        tools_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Tools":
                tools_menu = action.menu()
                break
        assert tools_menu is not None

        group3_submenu = None
        for a in tools_menu.actions():
            if a.text() == "&解密工具3":
                group3_submenu = a.menu()
                break
        assert group3_submenu is not None, "'解密工具3' submenu 未找到"

    def test_tools_menu_keeps_existing_base_rot_submenu(self, qtbot):
        """v0.5-cipher-decoders 不能破坏老 'Base/Rot' submenu."""
        from automisc.gui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        tools_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Tools":
                tools_menu = action.menu()
                break
        assert tools_menu is not None

        # 老 'Base_Rot' submenu (per v0.5-base-rot-decoders category='base_rot'
        # 在 _build_tools_menu 里 .title() → 'Base_Rot')
        submenu_titles = []
        for a in tools_menu.actions():
            if a.menu() is not None:
                submenu_titles.append(a.text())

        assert any("Base" in t for t in submenu_titles), \
            f"老 Base/Rot submenu 不见了 — {submenu_titles}"

    def test_list_decoders_by_group_returns_three_groups(self):
        """registry list_decoders_by_group() 返回 3 个 group."""
        grouped = list_decoders_by_group()
        assert "解密工具1" in grouped
        assert "解密工具2" in grouped
        assert "解密工具3" in grouped
        # 不包含 general (老 decoder 不渲染到 by_group)
        assert "general" not in grouped


# ---------- Fixtures ----------
@pytest.fixture
def sample_key_exe():
    return str(Path("Challenge/KEY.exe"))
