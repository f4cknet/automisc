"""v0.5-truncate-output + v0.5-short-circuit-on-flag 单测.

Owner 触发 (2026-06-14 10:46):
> 我回测了 steg.png 这道题, lsb 已经命中了纯 text, 原则上不应该再去 strings 了,
> 并且 stirngs | grep 没能匹配到可疑特征也打印出来了, 如果一个图片比较大怎么办,
> 打印 strings 就占满了窗口

覆盖:
- strings adapter: 渲染版 stdout (max 20 命中行 + summary, 不含未命中行)
- grep adapter: 渲染版 stdout (max 20 命中行 + summary)
- strings/grep 无命中 -> 一行 summary 提示
- AutoRunner.short_circuit: severity>=5 终止链
- main_window._on_auto_short_circuited 渲染 "[short-circuit]"
"""
from __future__ import annotations

import pytest

from automisc.core.utils.rule_scanner import _SENSITIVE_KEYWORDS
from automisc.tools.shared.strings import StringsAdapter
from automisc.tools.forensics.log.grep import GrepAdapter


# ---------- strings 渲染版 ----------
class TestStringsRenderedOutput:
    def test_no_suspicious_renders_summary(self, tmp_path):
        """strings 输出 1000 行但无命中 -> 渲染版只显示 summary."""
        a = StringsAdapter()
        big = tmp_path / "big.txt"
        # 1000 行普通 ASCII, 不含任何 base64/hex/binary/keyword
        big.write_text("\n".join(f"line {i} hello world" for i in range(1000)))
        r = a.run(str(big))
        rendered = r.stdout
        # 不应包含 raw stdout (1000 行 "line N hello world")
        assert "line 0 hello world" not in rendered
        assert "line 999 hello world" not in rendered
        # 应含 summary
        assert "strings 摘要" in rendered
        assert "total_lines: 1000" in rendered
        assert "suspicious: 0" in rendered
        # suspicious_points 列表也空
        assert r.suspicious_points == []

    def test_with_suspicious_renders_hits(self, tmp_path):
        """strings 命中 base64 + hex -> 渲染版只显示命中行."""
        a = StringsAdapter()
        f = tmp_path / "mixed.txt"
        # 30 行普通 + 5 行含 base64 + 3 行含 hex
        lines = [f"line {i} normal text" for i in range(30)]
        # base64 串 (>= 30 chars)
        lines.append("aGVsbG8gd29ybGQgdGhpcyBpcyBhIGJhc2U2NCBzdHJpbmcxMjM0NTY3ODkw")  # "hello world this is a base64 string1234567890"
        lines.append("VGVzdGluZyBiYXNlNjQgZW5jb2RlZCB0ZXh0IGFiY2RlZmdoaWprbG1ub3Bx")  # another
        # hex 串
        lines.append("28372c37290a")  # (7,7)
        lines.append("deadbeefcafebabe1234567890abcdef")
        f.write_text("\n".join(lines))
        r = a.run(str(f))
        rendered = r.stdout
        # 渲染版头部
        assert "strings 摘要" in rendered
        assert "total_lines:" in rendered
        assert "suspicious:" in rendered
        # 不应打印"line 0 normal text"等未命中行
        assert "line 0 normal text" not in rendered
        # suspicious_points 列表应含 base64/hex
        assert len(r.suspicious_points) >= 2
        # 至少有一行带 L 编号 (命中行)
        assert any(f"L{n}:" in rendered for n in range(31, 40))

    def test_total_lines_summary(self, tmp_path):
        """100 行 strings -> rendered 报告 total_lines=100."""
        a = StringsAdapter()
        f = tmp_path / "f.txt"
        f.write_text("\n".join("plain text " * 5 for _ in range(100)))
        r = a.run(str(f))
        assert "total_lines: 100" in r.stdout


# ---------- grep 渲染版 ----------
class TestGrepRenderedOutput:
    def test_no_match_renders_summary(self, tmp_path):
        """grep 0 命中 -> 渲染版只一行 summary."""
        a = GrepAdapter()
        f = tmp_path / "log.txt"
        f.write_text("2024-01-01 normal log line\n" * 100)
        r = a.run(str(f))
        rendered = r.stdout
        # 不应含 raw stdout
        assert "2024-01-01 normal log line" not in rendered
        # summary
        assert "grep 摘要" in rendered
        assert "suspicious: 0" in rendered

    def test_with_match_renders_hits(self, tmp_path):
        """grep 命中关键字 -> 渲染版显示命中行."""
        a = GrepAdapter()
        f = tmp_path / "log_with_secret.txt"
        lines = ["2024-01-01 normal log"] * 50
        lines[10] = "10:user logged in with password=hunter2"
        lines[20] = "20:config contains secret_key=abc123"
        f.write_text("\n".join(lines))
        r = a.run(str(f))
        rendered = r.stdout
        assert "grep 摘要" in rendered
        # 实际 grep 输出可能 3 sps (line 10 + line 20 + flag generic match)
        assert "suspicious:" in rendered
        # 应含 L10/L20/L21 (具体看 grep 怎么算)
        assert "L" in rendered


# ---------- AutoRunner short-circuit ----------
# v0.5-journal-highlight-keywords Q12 (per Owner 2026-06-16 2:12 铁律):
# "可疑点越多越好, 永远跑完所有 max_tools 个工具"
# SHORT_CIRCUIT_SEVERITY = 99 → 永不触发 short-circuit
# 这些 test 验证新行为: 命中 severity=5 也不停, 跑完全部
class TestAutoRunnerShortCircuit:
    def test_short_circuit_on_flag(self, qtbot, tmp_path):
        """tool 命中 severity=5 → 仍跑完全部 max_tools 个工具 (per owner 铁律 Q12).

        SHORT_CIRCUIT_SEVERITY = 99 (永不 short-circuit), 即使 strings 命中 severity=5,
        binwalk/exiftool 仍要跑完 (宁可多给错给, 也不能少给).
        """
        from automisc.gui.auto_runner import AutoRunner, SHORT_CIRCUIT_SEVERITY
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.core.router import RouteRecommendation

        # 验证常量 = 99 (锁死铁律)
        assert SHORT_CIRCUIT_SEVERITY == 99

        # 造一个文件含 flag{test_short_circuit} 关键字
        f = tmp_path / "flag.txt"
        f.write_text("flag{test_short_circuit} hello world " * 5)

        core = CoreOrchestrator()
        # 推荐 3 个: strings (10), binwalk (5), exiftool (3)
        recs = [
            RouteRecommendation(tool_name="strings", score=10, reason=""),
            RouteRecommendation(tool_name="binwalk", score=5, reason=""),
            RouteRecommendation(tool_name="exiftool", score=3, reason=""),
        ]
        runner = AutoRunner(core, recs, str(f), max_tools=3)
        finished = []
        sc = []
        runner.chain_finished.connect(finished.append)
        runner.short_circuited.connect(lambda t, r: sc.append((t, r)))

        with qtbot.waitSignal(runner.chain_finished, timeout=10_000):
            runner.start()

        tools = [s.tool_name for s in finished[0]]
        # Q12: 全跑完, strings 命中也不停
        assert "strings" in tools
        assert "binwalk" in tools
        assert "exiftool" in tools
        # Q12: short_circuited 信号永不触发
        assert sc == []  

    def test_no_short_circuit_on_low_severity(self, qtbot, tmp_path):
        """tool 命中 severity=3 (普通) -> 不 short-circuit, 继续跑."""
        from automisc.gui.auto_runner import AutoRunner
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.core.router import RouteRecommendation

        # 普通文本不含敏感关键字, strings 应出 0 sp
        f = tmp_path / "plain.txt"
        f.write_text("just normal text\n" * 5)

        core = CoreOrchestrator()
        recs = [
            RouteRecommendation(tool_name="strings", score=10, reason=""),
            RouteRecommendation(tool_name="file", score=5, reason=""),
        ]
        runner = AutoRunner(core, recs, str(f), max_tools=2)
        finished = []
        sc = []
        runner.chain_finished.connect(finished.append)
        runner.short_circuited.connect(lambda t, r: sc.append(t))

        with qtbot.waitSignal(runner.chain_finished, timeout=10_000):
            runner.start()

        # strings + file 都跑了 (无 short-circuit)
        assert len(finished[0]) == 2
        assert sc == []


# ---------- main_window 渲染 short-circuit 信息 ----------
# v0.5-journal-highlight-keywords Q12: SHORT_CIRCUIT_SEVERITY=99 永不 short-circuit
# → output 永远**不**渲染 [short-circuit] 信息 (旧行为已删)
class TestMainWindowShortCircuitRender:
    def test_short_circuit_message_in_output(self, qtbot, tmp_path):
        """main_window: SHORT_CIRCUIT_SEVERITY=99 → output **不**渲染 [short-circuit] 信息.

        之前 v0.5-short-circuit-on-flag 设计 (severity>=5 终止链) 已删除 (per Owner 铁律
        "可疑点越多越好, 宁可多给错给, 也不能少给"). 现在 auto-run 永远跑完所有 max_tools,
        所以 [short-circuit] 永远不会出现在 output 区.
        """
        from automisc.gui.main_window import MainWindow
        from automisc.gui.auto_runner import AutoRunner
        from automisc.core.orchestrator import CoreOrchestrator
        from automisc.core.router import RouteRecommendation
        from PySide6.QtWidgets import QApplication

        f = tmp_path / "flag.txt"
        f.write_text("flag{my_super_flag_for_short_circuit_test}")

        w = MainWindow(core=CoreOrchestrator())
        qtbot.addWidget(w)
        w.current_file = f

        recs = [
            RouteRecommendation(tool_name="strings", score=10, reason=""),
            RouteRecommendation(tool_name="file", score=5, reason=""),
        ]
        runner = AutoRunner(w.core, recs, str(f), max_tools=2)
        runner.tool_finished.connect(w._on_auto_tool_finished)
        runner.chain_finished.connect(w._on_auto_chain_finished)
        runner.short_circuited.connect(w._on_auto_short_circuited)

        # 等 chain 结束
        signal_received = {"flag": False}
        runner.chain_finished.connect(
            lambda *args: signal_received.__setitem__("flag", True)
        )
        runner.start()
        qtbot.waitUntil(lambda: signal_received["flag"], timeout=10_000)
        QApplication.processEvents()

        out = w.output_view.toPlainText()
        # Q12: [short-circuit] 信息**永不**渲染 (旧行为已删)
        assert "[short-circuit]" not in out
        assert "后续 tools 跳过" not in out
        # strings + file 都跑了
        assert "strings" in out
        assert "file" in out
