"""输出/输入区（中央 widget）— v0.5-IO-widget.

设计 (per Owner 2026-06-14):
- 中央 widget 同时支持:
  1. **工具输出** —— 跟之前一样 append_text/append_suspicious/append_chain_log...
  2. **人工输入** —— 拖入文件识别出 hex 后, 用户能清空 + 粘贴自己的 hex + 点 hex→ASCII 按钮出 text
  3. **Clear 按钮** —— 一键清空
  4. **Paste 按钮** —— 显式 paste
  5. **Hex→ASCII 按钮** —— 当前 input 区 text -> base_convert.convert_text_to_ascii
  6. **Read-only toggle** —— 切到 "input mode" 才能编辑, 切回 "output mode" 防止误改

布局:
```
+----------------------------------------+
| [Clear] [Paste] [Read-only OFF] [Hex→ASCII] |  <- 顶 bar
+----------------------------------------+
|                                        |
|  QPlainTextEdit (output + 可编辑 input)|
|                                        |
+----------------------------------------+
```

历史 API 兼容 (append_text / append_suspicious / append_result / ...):
- 全部保留, 不破坏现有 _on_chain_finished / _on_runner_finished 等调用
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint


# severity 颜色
SEVERITY_COLORS: dict[int, QColor] = {
    5: QColor(255, 64, 64),    # 致命 (flag) - 红
    4: QColor(255, 165, 0),    # 高 (webshell/加密 zip) - 橙
    3: QColor(255, 215, 0),    # 中 (隐藏文件) - 黄
    2: QColor(100, 200, 100),  # 低 - 绿
    1: QColor(150, 150, 150),  # 信息 - 灰
}


class InputOutputView(QWidget):
    """automisc 中央 widget (v0.5-IO-widget).

    提供:
    - append_text / append_suspicious / append_result (v0.1 兼容)
    - append_flag_candidate / append_lsb_text / append_chain_log / append_chain_summary (v0.5 兼容)
    - clear() / paste_clipboard() / run_hex_to_ascii() (v0.5+ 新)
    - toPlainText() (用于 hex→ASCII 输入)
    - read_only toggle (默认 True, 用户切换后可编辑)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 顶 bar: 按钮
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 4, 4, 4)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setToolTip("清空 output/input 区")
        self.btn_clear.clicked.connect(self.clear)
        bar.addWidget(self.btn_clear)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setToolTip("从剪贴板粘贴到光标位置")
        self.btn_paste.clicked.connect(self.paste_clipboard)
        bar.addWidget(self.btn_paste)

        # Read-only toggle
        self.btn_readonly = QPushButton("Read-only: ON")
        self.btn_readonly.setCheckable(True)
        self.btn_readonly.setChecked(True)
        self.btn_readonly.setToolTip("ON=锁住防止误改 (默认); OFF=可编辑用作 input")
        self.btn_readonly.toggled.connect(self._toggle_readonly)
        bar.addWidget(self.btn_readonly)

        bar.addStretch()

        # v0.5-hex-ascii-fix: 删除原顶 bar [Hex → ASCII] 按钮 (与菜单栏 hex-ascii 重复)
        # 原因 (per Owner 2026-06-14 09:50): "既然左侧菜单工具栏中有 hex 转 ascii, 那就没必要右上角放一个 hex->ascii 按钮了"

        layout.addLayout(bar)

        # 中央 text edit
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Menlo", 11))
        self.text_edit.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        self.text_edit.setMaximumBlockCount(5000)
        layout.addWidget(self.text_edit)

    # ---------- 兼容 OutputView API (历史 append_* 方法) ----------
    def append_text(self, text: str) -> None:
        """追加普通文本."""
        self.text_edit.appendPlainText(text.rstrip("\n"))

    def append_suspicious(self, sp: SuspiciousPoint) -> None:
        """追加 suspicious point (按 severity 高亮).

        v0.5-hex-router-fix (per Owner 14:11):
        - matched_pattern 截断 200 字符 (避免 650000 字符 hex 撑爆 GUI)
        - 长 hex 串 (>= 200 chars 且 '十六进制' 类别): 显示占位符 + 提示 '已自动处理'
        - sp.context 也截断 200
        """
        from automisc.core.actions.hex_router import HEX_AUTO_ROUTER_MIN_LEN

        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        color = SEVERITY_COLORS.get(sp.severity, QColor("white"))
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFontWeight(QFont.Bold)

        # v0.5-hex-router-fix: 长 hex 串 (>= HEX_AUTO_ROUTER_MIN_LEN) 显占位符
        is_long_hex = (
            ("十六进制" in sp.category or "hex" in sp.category.lower())
            and len(sp.matched_pattern) >= HEX_AUTO_ROUTER_MIN_LEN
        )
        if is_long_hex:
            display = "<hex_router 已自动处理, 见 strings 摘要>"
        else:
            display = sp.matched_pattern[:200]

        text = f"  [{sp.severity}] {sp.category}: {display}"
        if sp.context:
            text += f"  ({sp.context[:200]})"
        cursor.insertText(text, fmt)
        cursor.insertText("\n")

    def append_result(self, result: ToolResult) -> None:
        """完整结果输出 (stdout + suspicious_points)."""
        self.append_text(f"exit_code: {result.exit_code}")
        if result.stdout:
            self.append_text(result.stdout.rstrip("\n"))
        if result.stderr:
            self.append_text(f"[stderr] {result.stderr}")
        sp_count = len(result.suspicious_points)
        self.append_text(f"suspicious_points ({sp_count}):")
        for sp in result.suspicious_points:
            self.append_suspicious(sp)

    def append_flag_candidate(self, candidate: str, channel: str = "") -> None:
        """高亮打印 flag 候选 (v0.5-LSB-router 触发)."""
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(255, 64, 64))
        fmt.setFontWeight(QFont.Bold)
        fmt.setBackground(QColor(80, 0, 0))

        text = f"\n[!!! FLAG CANDIDATE !!!] {candidate}"
        if channel:
            text += f"  (channel={channel})"
        cursor.insertText(text, fmt)
        cursor.insertText("\n")

    def append_lsb_text(self, lsb_text: str, channel: str = "") -> None:
        """v0.5-bug-fix-3: LSB 抽到的整段 text 高亮 + 敏感词额外标记."""
        from automisc.core.utils.rule_scanner import _SENSITIVE_KEYWORDS
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        # 标题
        fmt_title = QTextCharFormat()
        fmt_title.setForeground(QColor(255, 215, 0))
        fmt_title.setFontWeight(QFont.Bold)
        header = f"\n[LSB text] channel={channel or '?'}, len={len(lsb_text)}\n"
        cursor.insertText(header, fmt_title)

        # 整段底色
        fmt_body = QTextCharFormat()
        fmt_body.setBackground(QColor(80, 60, 0))
        fmt_body.setForeground(QColor(255, 255, 200))
        cursor.insertText(lsb_text, fmt_body)

        # 敏感词额外高亮
        text_lower = lsb_text.lower()
        for kw in _SENSITIVE_KEYWORDS:
            start = 0
            while True:
                idx = text_lower.find(kw, start)
                if idx < 0:
                    break
                pos = cursor.position()
                cursor.setPosition(pos - len(lsb_text) + idx, QTextCursor.MoveAnchor)
                cursor.setPosition(
                    pos - len(lsb_text) + idx + len(kw), QTextCursor.KeepAnchor
                )
                fmt_kw = QTextCharFormat()
                fmt_kw.setBackground(QColor(180, 0, 0))
                fmt_kw.setForeground(QColor(255, 255, 0))
                fmt_kw.setFontWeight(QFont.Bold)
                fmt_kw.setFontUnderline(True)
                cursor.setCharFormat(fmt_kw)
                start = idx + len(kw)
                cursor.setPosition(pos, QTextCursor.MoveAnchor)
        cursor.insertText("\n")

    def append_chain_log(self, log: list[dict]) -> None:
        """渲染 DAG chain 日志."""
        for step in log:
            status = "OK  " if step["success"] else "FAIL"
            line = f"  [{step['step']}] {step['node']:<20s} {status}   {step['message']}"
            self.append_text(line)
        self.append_text("")

    def append_chain_summary(self, context: dict) -> None:
        """渲染 chain 总结 + flag_candidate."""
        log = context.get("__log__", [])
        total = len(log)
        ok = sum(1 for s in log if s.get("success"))

        self.append_text(f"\n--- chain summary ---")
        self.append_text(f"  total:   {total} steps")
        self.append_text(f"  success: {ok}")
        self.append_text(f"  failure: {total - ok}")

        last_step = context.get("__last_result__")
        if last_step and last_step.data:
            flag_candidate = last_step.data.get("flag_candidate")
            if flag_candidate:
                lsb_text = last_step.data.get("lsb_text", {})
                channel = lsb_text.get("channel", "") if lsb_text else ""
                self.append_flag_candidate(flag_candidate, channel=channel)

            extracted = last_step.data.get("extracted_files", [])
            if extracted:
                self.append_text(f"  extracted_files: {len(extracted)}")
                for f in extracted[:5]:
                    self.append_text(f"    - {f}")

        if last_step and last_step.data and "--debug" in str(context):
            import json
            self.append_text("\n[debug] last step data:")
            self.append_text(json.dumps(last_step.data, indent=2, default=str)[:2000])

    # ---------- v0.5-IO-widget 新增 ----------
    def clear(self) -> None:
        """清空 output/input 区."""
        self.text_edit.clear()
        self.append_text("[cleared]")

    def paste_clipboard(self) -> None:
        """从剪贴板粘贴到当前光标位置.

        行为:
        - 总是先 clear, 再 paste (替代模式 - 用户意图是"用粘贴板内容替换")
        - paste 后追加 newline 让 run_hex_to_ascii 选最后一行能选中
        - 如果 read-only, 自动切到可编辑模式 (因为用户要粘贴)
        """
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if not text:
            self.append_text("[paste] clipboard is empty")
            return
        # 如果 read-only, 自动切到可编辑模式 (因为用户要粘贴)
        if self.text_edit.isReadOnly():
            self._toggle_readonly(False)
        # 总是先 clear 旧内容 (per Owner 2026-06-14 设计:
        # "用户可以删除 input 窗口所有内容, 然后把那串数粘贴进去")
        self.text_edit.clear()
        cursor = self.text_edit.textCursor()
        cursor.insertText(text)
        # 末尾补 newline 让 run_hex_to_ascii 选最后一行能拿到完整内容
        if not text.endswith("\n"):
            cursor.insertText("\n")
        self.append_text(f"[pasted {len(text)} chars]")

    def run_hex_to_ascii(self) -> None:
        """把当前 input 区文本当 hex/binary/base64/base32 → ASCII.

        v0.5-hex-ascii-fix (2026-06-14): 此方法现在**仅供 main_window 内部用**,
        顶 bar 按钮已删 (per Owner "既然菜单栏有了就没必要").
        GUI 用户应通过菜单栏 Tools -> 🔢 进制转换 -> Hex → ASCII 触发.

        Owner 2026-06-14 真实场景:
          1. 拖 meihuai.jpg -> 跑 tools, strings 报 hex
          2. 用户在 output 里看到 hex
          3. 用户点 [Clear] + 点 [Read-only: OFF] + 点 [Paste] 粘自己复制的 hex
          4. 点菜单 [Hex → ASCII] -> output (7,7) 等 text
        """
        from automisc.core.decoders.base_convert import (
            BaseConvertError,
            detect_and_decode,
        )

        text = self.text_edit.toPlainText().strip()
        if not text or text == "[cleared]":
            self.append_text("[hex→ascii] input is empty; please paste some hex/binary/base64/base32 text first")
            return

        candidate = self.extract_base_candidate()
        if not candidate:
            self.append_text("[hex→ascii] no candidate found; please select text or paste base-encoded input")
            return

        try:
            fmt, decoded = detect_and_decode(candidate)
        except BaseConvertError as e:
            self.append_text(f"[hex→ascii] failed: {e}")
            self.append_text(f"  input: {candidate[:100]!r}")
            return

        # 高亮打印
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt_obj = QTextCharFormat()
        fmt_obj.setForeground(QColor(0, 255, 128))  # 亮绿
        fmt_obj.setFontWeight(QFont.Bold)
        text_out = f"\n[Hex → ASCII] detected={fmt}\n  input:  {candidate[:100]}{'...' if len(candidate) > 100 else ''}\n  output: {decoded}\n"
        cursor.insertText(text_out, fmt_obj)

    def extract_base_candidate(self) -> str | None:
        """从 input 区抽 candidate (selection 优先, 否则最后像 base 的行).

        v0.5-hex-ascii-fix: 抽出为公共方法, 让 main_window._run_decoder
        (菜单栏 hex-ascii) 和 InputOutputView.run_hex_to_ascii 共享同一逻辑.

        v0.5-brainfuck-candidate-fix (per Owner 2026-06-20 20:19 实战反馈):
        - 之前 `looks_like_base` 只检查"全 [0-9a-zA-Z+/= \n\r\t] 字符" + 长度 ≥ 2
        - 太宽松: 把 GUI [drop] recommendation 行 "           5  xxd              hex dump"
          (纯数字 + 空格 + 短英文, 28 chars) 误判成 base candidate
        - owner 拖文件 + auto-run 跑完 + 点 brainfuck decoder → 抽到这行 → 跑空
        - 修法: 真正 base 必含特征字符 +/= 之一 (光字母数字不够, 太容易撞 GUI 日志)
                短行 (< 8 chars) 直接排除 (base 至少 8 chars, GUI 推荐行常 10-30 chars)
                数字开头行 (≥ 3 个连续数字开头) 排除 (GUI log 行特征)

        Returns:
            candidate string 或 None (空 input)

        Logic:
        1. 用户有 selection -> 用 selection
        2. 否则过每一行, 跳过 log 装饰 ([xxx] / === / --- / 空行), 找最后"看起来像
           base-encoded"的非空行
        3. 都没找到 -> 用最后非空行 (兜底)
        """
        import re
        text = self.text_edit.toPlainText().strip()
        if not text or text == "[cleared]":
            return None

        # 1. selection 优先
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            sel = cursor.selectedText().strip()
            if sel:
                return sel

        # 2. 找最后像 base 的行 (加固, per Owner 20:19 实战反馈)
        def looks_like_base(s: str) -> bool:
            if not s:
                return False
            if s.startswith("[") or s.startswith("=") or s.startswith("---"):
                return False
            # v0.5-brainfuck-candidate-fix: 数字开头的行不算 (GUI log 行特征)
            #   e.g. "           10  file             通用文件类型识别"
            #   e.g. "           5  xxd              hex dump"
            if re.match(r"^\s*\d+\s+\d", s):  # "数字 空格 数字" 开头的 log 行
                return False
            # v0.5-brainfuck-candidate-fix + 兼容 caesar 测试: 全大写无空格密文
            #   e.g. "KHOOR" (caesar shift=3 → HELLO) — 全大写字母 + 长度 ≥ 4 + 无空格
            #   之前的 len < 8 阈值排除了这种, 修法: 加密文特例
            if re.match(r"^[A-Z]{4,}$", s):
                return True
            # 长度 < 8 太短不算 (base 至少 8 chars, 排除短纯英文/短纯数字)
            if len(s) < 8:
                return False
            # 真正 base/hex/binary 候选, 满足以下之一:
            #   - 含 base64 特征字符 +/=
            #   - 全是 hex 字符 (0-9 a-f A-F)
            #   - 全是 binary 字符 (0/1)
            # 否则就是普通英文 (e.g. "xxd hex dump" 纯字母空格) 不算
            has_base64_char = bool(re.search(r"[+/=]", s))
            is_all_hex = bool(re.match(r"^[0-9a-fA-F]+$", s))
            is_all_binary = bool(re.match(r"^[01]+$", s))
            if not (has_base64_char or is_all_hex or is_all_binary):
                return False
            # 全字符是 base64/base32 字符集
            return bool(re.match(r"^[0-9a-zA-Z+/= \n\r\t]+$", s)) and not s.startswith("//") and not s.startswith("#")

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        base_lines = [ln for ln in lines if looks_like_base(ln)]
        if base_lines:
            return base_lines[-1]
        if lines:
            return lines[-1]
        return None

    def toPlainText(self) -> str:
        """兼容 QPlainTextEdit 接口 + 历史 test (w.output_view.toPlainText())."""
        return self.text_edit.toPlainText()

    def setPlainText(self, text: str) -> None:
        """兼容 QPlainTextEdit 接口."""
        self.text_edit.setPlainText(text)

    def appendPlainText(self, text: str) -> None:
        """兼容 QPlainTextEdit 接口."""
        self.text_edit.appendPlainText(text)

    # QPlainTextEdit 风格 properties — 让 test 能直接 w.output_view.toPlainText() 工作
    @property
    def isReadOnly(self) -> bool:
        return self.text_edit.isReadOnly()

    def setReadOnly(self, ro: bool) -> None:
        self.text_edit.setReadOnly(ro)
        # 同步按钮状态
        self.btn_readonly.setChecked(ro)
        self.btn_readonly.setText(f"Read-only: {'ON' if ro else 'OFF'}")

    def _toggle_readonly(self, checked: bool) -> None:
        """切换 read-only 模式."""
        self.text_edit.setReadOnly(checked)
        self.btn_readonly.setText(f"Read-only: {'ON' if checked else 'OFF'}")
        if not checked:
            self.append_text("[input mode ON] 可编辑, 用于粘贴待解码文本 (点 [Hex → ASCII] 转换)")


# 旧名 alias — 避免破坏外部 import (tests 等)
OutputView = InputOutputView
