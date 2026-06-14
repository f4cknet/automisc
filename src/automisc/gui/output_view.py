"""输出区（中央 QPlainTextEdit）— 工具 stdout + suspicious_points 高亮."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

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


class OutputView(QPlainTextEdit):
    """automisc 输出区（中央）。

    支持：
    - append_text  普通文本
    - append_suspicious  按 severity 高亮
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Menlo", 11))
        # 深色背景便于看高亮
        self.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        self.setMaximumBlockCount(5000)  # 限制最大行数

    def append_text(self, text: str) -> None:
        """追加普通文本."""
        self.appendPlainText(text.rstrip("\n"))

    def append_suspicious(self, sp: SuspiciousPoint) -> None:
        """追加 suspicious point（按 severity 高亮）."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        color = SEVERITY_COLORS.get(sp.severity, QColor("white"))
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFontWeight(QFont.Bold)

        # 实际 schema：category + matched_pattern + context
        text = f"  [{sp.severity}] {sp.category}: {sp.matched_pattern}"
        if sp.context:
            text += f"  ({sp.context})"
        cursor.insertText(text, fmt)
        cursor.insertText("\n")

    def append_result(self, result: ToolResult) -> None:
        """完整结果输出（stdout + suspicious_points）."""
        self.append_text(f"exit_code: {result.exit_code}")
        if result.stdout:
            self.append_text(result.stdout.rstrip("\n"))
        if result.stderr:
            self.append_text(f"[stderr] {result.stderr}")
        sp_count = len(result.suspicious_points)
        self.append_text(f"suspicious_points ({sp_count}):")
        for sp in result.suspicious_points:
            self.append_suspicious(sp)

    # ---------- v0.5 chain 输出辅助 (GUI 同步 CLI) ----------
    def append_flag_candidate(self, candidate: str, channel: str = "") -> None:
        """高亮打印 flag 候选 (v0.5-LSB-router 触发).

        Args:
            candidate: 候选 flag 字符串
            channel: LSB 通道 (e.g. "b1,rgb,lsb,xy")
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(255, 64, 64))  # 致命红
        fmt.setFontWeight(QFont.Bold)
        fmt.setBackground(QColor(80, 0, 0))  # 深红背景

        text = f"\n[!!! FLAG CANDIDATE !!!] {candidate}"
        if channel:
            text += f"  (channel={channel})"
        cursor.insertText(text, fmt)
        cursor.insertText("\n")

    def append_lsb_text(self, lsb_text: str, channel: str = "") -> None:
        """v0.5-bug-fix-3: LSB 抽到的整段 text 高亮显示 + 敏感词特别标记.

        Bug 现象: LSB 抽到 "...the secret key is: st3g0..." 整段被当普通颜色显示,
                  关键字 secret/key 不突出.
        修复: 整段用深黄底色高亮 + 敏感关键词 (key/flag/secret/ctf/password)
              用更深的红底+粗体额外标记.

        Args:
            lsb_text: LSB 抽到的整段 text
            channel: LSB 通道 (e.g. "b1,rgb,lsb,xy")
        """
        from automisc.core.utils.rule_scanner import _SENSITIVE_KEYWORDS
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # 标题
        fmt_title = QTextCharFormat()
        fmt_title.setForeground(QColor(255, 215, 0))  # 金黄
        fmt_title.setFontWeight(QFont.Bold)
        header = f"\n[LSB text] channel={channel or '?'}, len={len(lsb_text)}\n"
        cursor.insertText(header, fmt_title)

        # 整段底色 (浅黄)
        fmt_body = QTextCharFormat()
        fmt_body.setBackground(QColor(80, 60, 0))  # 深黄底
        fmt_body.setForeground(QColor(255, 255, 200))  # 浅黄字
        cursor.insertText(lsb_text, fmt_body)

        # 敏感词额外高亮 (在整段上覆盖)
        text_lower = lsb_text.lower()
        for kw in _SENSITIVE_KEYWORDS:
            start = 0
            while True:
                idx = text_lower.find(kw, start)
                if idx < 0:
                    break
                # 重新定位 cursor 到 idx
                pos = cursor.position()
                # 退到整段起点
                cursor.setPosition(pos - len(lsb_text) + idx, QTextCursor.MoveAnchor)
                cursor.setPosition(
                    pos - len(lsb_text) + idx + len(kw), QTextCursor.KeepAnchor
                )
                fmt_kw = QTextCharFormat()
                fmt_kw.setBackground(QColor(180, 0, 0))  # 深红底
                fmt_kw.setForeground(QColor(255, 255, 0))  # 黄字
                fmt_kw.setFontWeight(QFont.Bold)
                fmt_kw.setFontUnderline(True)
                cursor.setCharFormat(fmt_kw)
                start = idx + len(kw)
                # cursor 回到末尾
                cursor.setPosition(pos, QTextCursor.MoveAnchor)
        cursor.insertText("\n")

    def append_chain_log(self, log: list[dict]) -> None:
        """渲染 DAG chain 日志 (step / node / success / message).

        Args:
            log: DAG.execute 返回的 __log__ 字段
        """
        for step in log:
            status = "OK  " if step["success"] else "FAIL"
            line = f"  [{step['step']}] {step['node']:<20s} {status}   {step['message']}"
            self.append_text(line)
        self.append_text("")

    def append_chain_summary(self, context: dict) -> None:
        """渲染 chain 总结 + flag_candidate (如有)."""
        log = context.get("__log__", [])
        total = len(log)
        ok = sum(1 for s in log if s.get("success"))

        # summary
        self.append_text(f"\n--- chain summary ---")
        self.append_text(f"  total:   {total} steps")
        self.append_text(f"  success: {ok}")
        self.append_text(f"  failure: {total - ok}")

        # flag_candidate 高亮 (v0.5-LSB-router)
        last_step = context.get("__last_result__")
        if last_step and last_step.data:
            flag_candidate = last_step.data.get("flag_candidate")
            if flag_candidate:
                # 找 channel (从 lsb_text)
                lsb_text = last_step.data.get("lsb_text", {})
                channel = lsb_text.get("channel", "") if lsb_text else ""
                self.append_flag_candidate(flag_candidate, channel=channel)

            # extracted_files (binwalk / foremost / lsb file 通道)
            extracted = last_step.data.get("extracted_files", [])
            if extracted:
                self.append_text(f"  extracted_files: {len(extracted)}")
                for f in extracted[:5]:
                    self.append_text(f"    - {f}")

        # last_step.data 全部 dump (供调试)
        if last_step and last_step.data and "--debug" in str(context):
            import json
            self.append_text("\n[debug] last step data:")
            self.append_text(json.dumps(last_step.data, indent=2, default=str)[:2000])
