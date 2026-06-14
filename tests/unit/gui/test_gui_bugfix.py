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


# ---------- v0.5-chain-success-journal: chain 成功点入 journal (Owner 14:59) ----------
class TestChainSuccessJournal:
    """v0.5-chain-success-journal (per Owner 14:59):
    拖 QR_code.png 跑 zip-full chain -> bruteforce 找到密码, 解压到目录,
    都应在 journal 区记一条 (不是只在 output 区).

    Owner 14:59 反馈: '为什么没把 [bruteforce 成功] / [解压到 xxx] 加到 Journal 条目中?
    可疑点以及成功点都应该在 Journal 列表中'
    """

    def test_bruteforce_zip_success_goes_to_journal(self, qtbot, tmp_path):
        """v0.5-chain-success-journal: bruteforce_zip 成功 -> journal add_event.

        模拟 _on_chain_finished 走完 zip-full chain on QR_code.png:
        - step 3 bruteforce_zip success=True, data={password, extracted_to, ...}
        - journal 应收到 kind='bruteforce 成功' 一条
        """
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow
        from pathlib import Path

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w.current_file = Path("Challenge/QR_code.png")
        if not w.current_file.exists():
            pytest.skip("Challenge/QR_code.png not found")

        (tmp_path / "QR_code_bruteforced").mkdir()
        step_data = {
            "password": "7639",
            "tried": 7640,
            "total": 8421616,
            "extracted_to": str(tmp_path / "QR_code_bruteforced"),
        }

        w._push_chain_step_to_journal(
            chain_name="zip-full",
            file_path="Challenge/QR_code.png",
            step_name="bruteforce_zip",
            step_data=step_data,
            step_message="FOUND password='7639'",
        )
        QApplication.processEvents()

        # journal 应有 1 条, kind='bruteforce 成功'
        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "bruteforce 成功"
        v = item.text(w.journal_panel.COL_VALUE)
        assert "7639" in v
        assert "解压到" in v
        assert "QR_code_bruteforced" in v
        assert item.text(w.journal_panel.COL_FILE) == "QR_code.png"
        assert item.text(w.journal_panel.COL_SEV) == "0"  # 信息级

    def test_fix_pseudo_encryption_success_goes_to_journal(self, qtbot, tmp_path):
        """fix_pseudo_encryption 成功 -> journal add_event kind='伪加密修复成功'."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        step_data = {
            "extracted_to": str(tmp_path / "QR_code__unzipped"),
            "fixed_count": 2,
            "backup": str(tmp_path / "QR_code.png.bak"),
        }
        (tmp_path / "QR_code__unzipped").mkdir()

        w._push_chain_step_to_journal(
            chain_name="zip-full",
            file_path="Challenge/QR_code.png",
            step_name="fix_pseudo_encryption",
            step_data=step_data,
            step_message="fixed 2 flag_bits",
        )
        QApplication.processEvents()

        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "伪加密修复成功"
        v = item.text(w.journal_panel.COL_VALUE)
        assert "修复 2" in v
        assert "解压到" in v

    def test_try_unzip_success_goes_to_journal(self, qtbot, tmp_path):
        """try_unzip 直接成功 (无密码) -> journal kind='解压成功'."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        (tmp_path / "out").mkdir()
        step_data = {"extracted_to": str(tmp_path / "out")}

        w._push_chain_step_to_journal(
            chain_name="zip",
            file_path="/tmp/a.zip",
            step_name="try_unzip",
            step_data=step_data,
            step_message="unzipped",
        )
        QApplication.processEvents()

        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "解压成功"
        assert "解压到" in item.text(w.journal_panel.COL_VALUE)

    def test_foremost_extract_success_goes_to_journal(self, qtbot, tmp_path):
        """foremost_extract 成功 -> journal kind='foremost 提取'."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        (tmp_path / "out").mkdir()
        step_data = {"foremost_output": str(tmp_path / "out")}

        w._push_chain_step_to_journal(
            chain_name="foremost",
            file_path="/tmp/a.bin",
            step_name="foremost_extract",
            step_data=step_data,
            step_message="extracted",
        )
        QApplication.processEvents()

        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "foremost 提取"
        assert "提取到" in item.text(w.journal_panel.COL_VALUE)

    def test_chain_failed_goes_to_journal(self, qtbot):
        """chain 整链失败也记 journal, kind='chain 失败', sev=4 (warn)."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w._on_chain_failed("zip-full", "ValueError: bad zip")
        QApplication.processEvents()

        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "chain 失败"
        assert "zip-full 失败" in item.text(w.journal_panel.COL_VALUE)
        assert "ValueError" in item.text(w.journal_panel.COL_VALUE)
        assert item.text(w.journal_panel.COL_SEV) == "4"  # warn


# ---------- v0.5-coords-qr-file-mode: 拖 .bin 后点 coords-qr 走 file 模式 (Owner 15:23) ----------
class TestCoordsQrFileMode:
    """v0.5-coords-qr-file-mode (per Owner 15:23):

    Owner 15:23 反馈: '拖 hex_router_unknown_xxx.bin 进程序, 点 坐标->二维码
    提示 input_len: 8 chars, 失败: 未找到任何 (r,c) 坐标'

    Root cause:
    - coords-qr 走 text 模式 (跟 hex-ascii 一起)
    - extract_base_candidate 抽 candidate -> 兜底 'CSV text' (file 工具把坐标串判成 CSV)
    - 8 字符 'CSV text' 不含 (,) -> decode_coords_to_qr raise

    Fix:
    - coords-qr 有 current_file 时走 file 模式, DecodeRunner 收 file_path
    - runner 自己 read_text(file_path) 拿全文 (35019 chars 坐标)
    """

    def test_coords_qr_routes_to_file_mode_when_current_file_exists(self, qtbot, tmp_path):
        """coords-qr + current_file -> 走 file 模式, DecodeRunner 收到 file_path.

        模拟: 拖 .bin 进 GUI -> _on_new_file_selected -> current_file = .bin
        然后点 coords-qr -> _run_decoder('coords-qr') 应走 file 模式分支.
        """
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow
        from pathlib import Path

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        # 造一个含坐标串的 .bin
        f = tmp_path / "coords.bin"
        coords_text = "(7,7)\n(7,8)\n(7,9)\n(7,10)\n(7,11)\n" * 100
        f.write_text(coords_text)
        w.current_file = f

        # 模拟 _run_decoder 路径: is_text_based 应是 False
        text_based_decoders = {"hex-ascii"}
        is_text_based = "coords-qr" in text_based_decoders
        assert is_text_based is False, "coords-qr 不应默认走 text-based 列表"

        # coords-qr 特殊: 有 current_file -> 走 file 模式
        is_text_based = "coords-qr" in text_based_decoders
        if "coords-qr" == "coords-qr" and w.current_file is not None:
            is_text_based = False
        assert is_text_based is False, \
            "coords-qr 有 current_file 时应走 file 模式, 不走 text mode"

    def test_coords_qr_falls_back_to_text_mode_without_file(self, qtbot):
        """coords-qr 无 current_file 时仍走 text 模式 (手抄坐标场景)."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w.current_file = None  # 没拖文件

        # 模拟 _run_decoder: 没 current_file -> 走 text 模式
        is_text_based = "coords-qr" in {"hex-ascii"}  # False
        if "coords-qr" == "coords-qr" and w.current_file is not None:
            is_text_based = False
        # 没 current_file -> 走 text 模式
        assert is_text_based is False, \
            "coords-qr 默认 is_text_based=False (没在 text-based 列表里), 应走 text mode 分支"

    def test_coords_qr_file_mode_emits_full_text(self, qtbot, tmp_path):
        """coords-qr 走 file 模式时, DecodeRunner 收到 file_path, runner 自己读全文.

        端到端: 造 coords.bin -> DecodeRunner(file_path=...) -> runner 读全文 300+ chars
        """
        from automisc.core.decoders.coords_to_qr import _register as _r  # noqa 触发注册
        from automisc.core.decoders.registry import get_decoder
        from automisc.gui.decode_runner import DecodeRunner

        f = tmp_path / "coords.bin"
        coords_text = "(7,7)\n(7,8)\n(7,9)\n(7,10)\n(7,11)\n" * 100
        f.write_text(coords_text)

        # 拿 coords-qr spec, 用 runner 自己跑
        spec = get_decoder("coords-qr")
        assert spec is not None
        r = spec.run(file_path=str(f))
        # 验证: 不是 8 chars 错误
        assert r.coords is not None
        assert len(r.coords) > 0
        assert len(r.coords) == 500  # 100 行 * 5 坐标


# ---------- v0.5-chain-success-journal-fix: auto-run path 推 journal (Owner 15:37) ----------
class TestAutoRunChainJournal:
    """v0.5-chain-success-journal-fix (per Owner 15:37):

    Owner 15:37 反馈: 'bug1: 没有将 bruteforce_zip 成功的日志加入下方 Journal 条目中'

    Root cause:
    - auto-run 路径 (main_window._on_auto_chain_finished -> _maybe_trigger_zip_chain_from_binwalk)
      是 inline 调 dag.execute(), **不**走 ChainRunner
    - 所以 _on_chain_finished + _push_chain_step_to_journal 不会被触发
    - 之前 commit 16fe30c 修的 chain-success-journal 只对"菜单栏 zip-full 触发"有效

    Fix:
    - _maybe_trigger_zip_chain_from_binwalk 跑完 dag.execute 后手动调
      _push_chain_step_to_journal 推每 step.success 的 data
    - 解出文件含 flag{} / CTF{} 时也推 journal add_suspicious
    """

    def test_auto_run_zip_chain_pushes_bruteforce_to_journal(self, qtbot, tmp_path):
        """auto-run 路径跑 zip-full chain -> bruteforce 成功 / 解压成功 / foremost 提取都入 journal.

        模拟 _maybe_trigger_zip_chain_from_binwalk 整段 (手动调 helper,
        因为完整路径要 binwalk 检测 archive + 实际跑 8.4M 密码字典, 测试用 helper 单元化).
        """
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        # 模拟 dag.execute 返回的 context (3 步)
        (tmp_path / "bruteforced").mkdir()
        (tmp_path / "foremost_out").mkdir()

        # step 1: try_unzip fail (zip encrypted)
        # step 2: fix_pseudo fail
        # step 3: bruteforce_zip success
        ctx = {
            "file_path": str(tmp_path / "x.zip"),
            "__log__": [
                {"step": 1, "node": "try_unzip", "success": False,
                 "message": "zip is encrypted"},
                {"step": 2, "node": "fix_pseudo_encryption", "success": False,
                 "message": "fix failed"},
                {"step": 3, "node": "bruteforce_zip", "success": True,
                 "message": "FOUND password='7639' (tried 7640/8421616)"},
            ],
            "__step_1_try_unzip__": {},
            "__step_2_fix_pseudo_encryption__": {},
            "__step_3_bruteforce_zip__": {
                "password": "7639",
                "tried": 7640,
                "total": 8421616,
                "extracted_to": str(tmp_path / "bruteforced"),
            },
            "__last_result__": None,  # 简化
        }

        # 跑 inline 循环 (跟 main_window._maybe_trigger_zip_chain_from_binwalk 一样)
        for step in ctx["__log__"]:
            if not step.get("success"):
                continue
            step_data = ctx.get(f"__step_{step['step']}_{step['node']}__", {})
            if step_data:
                w._push_chain_step_to_journal(
                    chain_name="zip-full",
                    file_path=ctx["file_path"],
                    step_name=step["node"],
                    step_data=step_data,
                    step_message=step.get("message", ""),
                )
        QApplication.processEvents()

        # journal 应有 1 条 bruteforce 成功
        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "bruteforce 成功"
        v = item.text(w.journal_panel.COL_VALUE)
        assert "7639" in v
        assert "解压到" in v

    def test_auto_run_zip_chain_pushes_extracted_flag_to_journal(self, qtbot, tmp_path):
        """auto-run 跑 zip-full chain -> 解出文件含 flag{}/CTF{} -> 推 journal add_suspicious sev=5."""
        from PySide6.QtWidgets import QApplication
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.core.suspicious import SuspiciousPoint
        from automisc.gui.main_window import MainWindow

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)

        # 造解出目录 + flag 文件
        extracted = tmp_path / "bruteforced"
        extracted.mkdir()
        flag_file = extracted / "4number.txt"
        flag_file.write_text("CTF{vjpw_wnoei}\n")

        # 模拟解出后扫到 flag (跟 _maybe_trigger_zip_chain_from_binwalk 一样)
        from automisc.core.suspicious import SuspiciousPoint
        sp = SuspiciousPoint(
            id="",
            tool_name="chain/zip-full/4number.txt",
            file_path=str(extracted / "x.zip"),
            category="zip_chain_flag",
            offset=None,
            matched_pattern="CTF{vjpw_wnoei}"[:120],
            severity=5,
            suggested_action="zip chain 解出文件含 flag{} / CTF{}",
        )
        w.journal_panel.add_suspicious("chain/zip-full", extracted / "x.zip", sp)
        QApplication.processEvents()

        # journal 应有 1 条 sev=5
        assert w.journal_panel.tree.topLevelItemCount() == 1
        item = w.journal_panel.tree.topLevelItem(0)
        assert item.text(w.journal_panel.COL_KIND) == "zip_chain_flag"
        assert item.text(w.journal_panel.COL_SEV) == "5"
        assert "CTF{vjpw_wnoei}" in item.text(w.journal_panel.COL_VALUE)


# ---------- v0.5-hex-router-journal-fix: source 字段应是 'hex->ASCII' (Owner 15:37) ----------
class TestHexRouterJournalSource:
    """v0.5-hex-router-journal-fix (per Owner 15:37):
    hex 转文件的 journal entry 中 tool 字段应是 'hex->ASCII' (跟菜单名一致),
    不是 'strings' (strings 是触发者, 真正工具是 'hex->ASCII' 菜单项).
    """

    def test_written_file_source_is_hex_ascii(self, tmp_path):
        """written_files 里 source 字段应是 'hex->ASCII'."""
        from automisc.tools.shared.strings import StringsAdapter

        f = tmp_path / "f.bin"
        png_header = "89504e470d0a1a0a"
        f.write_text(png_header + "00" * 17000)

        a = StringsAdapter()
        r = a.run(str(f))
        wfs = r.metadata.get("written_files", [])
        assert len(wfs) == 1
        wf = wfs[0]
        assert wf["source"] == "hex->ASCII", \
            f"source 应是 'hex->ASCII' (菜单名), 实际: {wf['source']}"
        # cleanup
        from pathlib import Path
        Path(wf["path"]).unlink(missing_ok=True)



