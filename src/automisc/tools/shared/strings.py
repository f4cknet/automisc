"""strings adapter（per ``tools.md`` §3.12 + v0.5+ rule_scanner 集成）

``strings -n 4``：提取 ≥4 字节可打印字符串。

**v0.5+ 重构**（per Owner 2026-06-14）：
- 跑完 strings 后用 ``core.utils.rule_scanner`` 逐行扫
- 命中 base64/base32/hex/binary/keyword → SuspiciousPoint
- severity: sensitive_keyword=5, base64/32/hex/binary=4
- **跳过** 旧 `scan_output_for_suspicious` 避免与 rule_scanner 重复 (其他 adapter 仍用旧路径)
- 输出按 命中类型 + 行号 + 内容 打印（owner 可手动进制转换）

**v0.5-truncate-output 改造** (2026-06-14 10:46):
- **不再** 存 raw stdout 到 ToolResult.stdout (大文件 strings 1000+ 行, 占满 GUI 窗口)
- 改存 **rendered** 版本: 命中行 + summary (匹配 N / 总 N 行), 加上 stderr
- GUI/CLI 用户想看 raw? 暂时隐藏; 后续可加 `--raw-stdout` flag (v0.5-候选)

**后续 v0.5+ 工具**: 进制转换 (base64/base32/hex/binary -> ascii) 由 rule_scanner.suggested_action 提示.
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.core.utils.rule_scanner import classify_text
from automisc.tools.base import ToolAdapter


# category -> 人类可读名
_CATEGORY_LABELS = {
    "sensitive_keyword": "敏感关键词",
    "base64": "Base64 串",
    "base32": "Base32 串",
    "hex": "十六进制串",
    "binary": "二进制串",
}


@register_tool
class StringsAdapter(ToolAdapter):
    """`strings` 命令 adapter —— 提取可打印字符串 + rule_scanner 扫可疑 text。"""

    name = "strings"
    category = "shared"
    description = "提取文件中的可打印字符串（≥4 字节）+ 自动扫可疑 base64/hex/binary/keyword"

    # 1 行最多报 N 个 suspicious (避免 strings 输出 1000 行时刷屏)
    MAX_MATCHES_PER_LINE = 3
    # 1 文件最多报 N 个 suspicious (兜底)
    MAX_MATCHES_TOTAL = 50
    # v0.5-truncate-output: 渲染版最多保留多少个 suspicious 命中行 (防窗口占满)
    MAX_RENDERED_HITS = 20

    def run(self, file_path: str) -> ToolResult:
        # -a: scan the whole file, not just the initialized data section of object files
        # -n 4: sequences of >= 4 printable chars
        cmd = [self.binary_path or "strings", "-a", "-n", "4", file_path]
        exit_code, raw_stdout, stderr, duration_ms = self._run_subprocess(cmd)

        # v0.5+ 增强: rule_scanner 逐行扫 (跳过旧路径避免重复)
        suspicious = self._scan_with_rule_scanner(file_path, raw_stdout)

        # v0.5-truncate-output: 渲染版 stdout (只显示命中行 + summary, 不显示 raw)
        # v0.5-hex-router-journal: 返回 tuple (rendered, written_files)
        #   written_files 给 GUI caller 推 journal + status bar, 不再混进 stdout
        rendered_stdout, written_files = self._render_output(
            raw_stdout, suspicious, file_path=file_path
        )

        result = ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=rendered_stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
        # 推 written_files 到 metadata
        for wf in written_files:
            result.add_written_file(
                path=wf["path"], kind=wf["kind"], source=wf.get("source", "strings")
            )
        return result

    def _scan_with_rule_scanner(
        self, file_path: str, stdout: str
    ) -> list[SuspiciousPoint]:
        """v0.5+: rule_scanner 逐行扫, 返回 SuspiciousPoint 列表."""
        results: list[SuspiciousPoint] = []
        if not stdout:
            return results

        for line_no, line in enumerate(stdout.splitlines(), start=1):
            if not line.strip():
                continue
            matches = classify_text(line)
            if not matches:
                continue
            # 1 行最多报 MAX_MATCHES_PER_LINE 个
            for m in matches[: self.MAX_MATCHES_PER_LINE]:
                if len(results) >= self.MAX_MATCHES_TOTAL:
                    return results
                category_label = _CATEGORY_LABELS.get(m.category, m.category)
                if m.category in ("base64", "base32", "hex", "binary"):
                    suggested = (
                        f"line {line_no} 命中 {m.category}: {m.value[:80]}\n"
                        f"  └─ 后续 v0.5+ 工具: hex/binary -> ascii 转换 (迭代计划中)\n"
                        f"  └─ base64 可试: `automisc decode base64-image --file <txt>`"
                    )
                else:
                    suggested = (
                        f"line {line_no} 命中 {m.category}: {m.value[:80]} "
                        f"(severity=5 owner 重点看)"
                    )
                # v0.5-hex-router (per Owner 13:39): hex 命中保留完整 m.value (不截断 120)
                # 让 _render_output 判断 "len >= 200" 是否自动 trigger hex_router
                # 其他类 (base64/base32/keyword) 仍截断 120 (防 GUI 占满)
                if m.category == "hex":
                    matched_pattern = m.value  # 完整 hex 串
                else:
                    matched_pattern = m.value[:120]
                results.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category=f"{category_label}_line{line_no}",
                        offset=None,
                        matched_pattern=matched_pattern,
                        severity=m.severity,
                        suggested_action=suggested,
                    )
                )
        return results

    def _render_output(self, raw_stdout: str, suspicious: list[SuspiciousPoint], file_path: str = ""):
        """v0.5-truncate-output: 渲染版 stdout.

        Args:
            raw_stdout: strings 命令原始输出
            suspicious: rule_scanner 命中 list (含 line_no via category "<label>_lineN")
            file_path: 输入文件路径 (用于提示 "想看原文: strings -a -n 4 <file>")

        Returns:
            v0.5-hex-router-journal (per Owner 14:43) tuple:
                (rendered_stdout: str, written_files: list[dict])
            - rendered_stdout: header + 命中行 (max MAX_RENDERED_HITS) + summary
              (省略 raw 中未命中行, 防大文件占满窗口)
            - written_files: [{"path", "kind", "source"}] 给 caller 推 journal + status bar

        v0.5-hex-router (2026-06-14 13:39 per Owner):
        - 短 hex 串 (< HEX_AUTO_ROUTER_MIN_LEN=200): 仍打印 L<line>: <前 200 字符>
        - 长 hex 串 (>= 200): **不打印** 实际内容, 提示 "已 hex_router 自动处理"
          (避免 35000 字符撑爆 GUI 窗口 + 强制 auto-run 走 DAG 流程)

        v0.5-hex-router-journal (per Owner 14:43):
        - 长 hex 写文件信息**不**再混进 stdout
        - 改走 written_files list, GUI caller 推 journal_panel.add_event()
        """
        from automisc.core.actions.hex_router import HEX_AUTO_ROUTER_MIN_LEN

        lines = raw_stdout.splitlines()
        total_lines = len(lines)
        # v0.5-hex-router-journal: 长 hex 写文件信息 (给 caller 推 journal)
        written_files: list[dict] = []

        if not suspicious:
            return (
                f"=== strings 摘要 (v0.5-truncate-output) ===\n"
                f"  total_lines: {total_lines}\n"
                f"  suspicious: 0\n"
                f"  └─ 无可疑特征, raw stdout 已省略 (想看原文: `strings -a -n 4 {file_path}`)\n",
                written_files,
            )

        # 提取 line_no from suspicious category (e.g. "hex_line42")
        hit_line_nos: set[int] = set()
        # v0.5-hex-router-journal: 收集 long hex 命中的 line + 自动 trigger hex_router
        # 不再在 stdout 拼 summary 段, 改用 written_files 给 caller
        for sp in suspicious:
            try:
                ln_str = sp.category.rsplit("_line", 1)[-1]
                hit_line_nos.add(int(ln_str))
            except (ValueError, IndexError):
                pass
            # v0.5-hex-router: 长 hex 串 -> auto route to file
            # 注: sp.category 是中文 label (e.g. "十六进制串_line1"), 匹配用中文
            if "十六进制" in sp.category or "hex" in sp.category.lower():
                hex_text = sp.matched_pattern  # 完整 hex 串 (不限 120 截断)
                if len(hex_text) >= HEX_AUTO_ROUTER_MIN_LEN:
                    # 自动 trigger
                    try:
                        from automisc.core.actions.hex_router import (
                            route_hex_to_file,
                        )
                        # v0.5-hex-router-samedir (per Owner 14:24):
                        # 传 input_path = 当前 strings 处理的 file_path
                        # hex_router 会写到 file_path.parent (samedir per v0.5-output-samedir)
                        # 而非 /tmp, 避免 14:24 反馈的
                        # 'saved=/private/var/folders/.../automisc_text_outputs/hex_router_xxx.bin'
                        router_result = route_hex_to_file(
                            hex_text, input_path=file_path
                        )
                        # v0.5-hex-router-journal (per Owner 14:43):
                        # 不再混进 stdout 拼 summary, 改走 written_files 给 caller 推 journal
                        # v0.5-hex-router-journal-fix (per Owner 15:37):
                        # tool 字段应是 'hex->ASCII' (跟菜单名一致), 不是 'strings'
                        # 因为 hex_router 是 strings 触发的内部子动作, 真正的"工具"是
                        # 'hex->ASCII' (menu 中 Tools 菜单的 🔢 Hex → ASCII 简称)
                        written_files.append({
                            "path": router_result.output_path,
                            "kind": "hex转文件",
                            "source": "hex->ASCII",
                        })
                    except Exception as e:  # noqa: BLE001
                        # 失败也记, kind 不同, 让 caller 推 journal
                        written_files.append({
                            "path": f"hex_router failed: {e}",
                            "kind": "hex转文件失败",
                            "source": "hex->ASCII",
                        })

        # 拼渲染版 (不再含 v0.5-hex-router summary 段, 改走 journal)
        out_lines = [
            f"=== strings 摘要 (v0.5-truncate-output) ===",
            f"  total_lines: {total_lines}",
            f"  suspicious:  {len(suspicious)} (raw stdout 1000+ 行已省略, 只显示命中行)",
        ]
        out_lines.extend([
            "",
            f"--- 命中行 (max {self.MAX_RENDERED_HITS} 显示) ---",
        ])

        shown = 0
        for line_no in sorted(hit_line_nos):
            if 1 <= line_no <= total_lines:
                if shown >= self.MAX_RENDERED_HITS:
                    out_lines.append(f"  ... 还有 {len(hit_line_nos) - shown} 行未显示")
                    break
                # v0.5-hex-router: hex 命中行, 如已 long-hex 路由, 不重复打印 35000 字符
                #                  仅短 hex 才显示 L<line>: <前 200 字符>
                line_content = lines[line_no - 1]
                is_long_hex = False
                # 找这个 line_no 对应的 sp, 判是否 long hex
                for sp in suspicious:
                    sp_ln = None
                    try:
                        sp_ln = int(sp.category.rsplit("_line", 1)[-1])
                    except (ValueError, IndexError):
                        pass
                    if sp_ln == line_no and ("十六进制" in sp.category or "hex" in sp.category.lower()) and len(sp.matched_pattern) >= HEX_AUTO_ROUTER_MIN_LEN:
                        is_long_hex = True
                        break
                if is_long_hex:
                    out_lines.append(
                        f"  L{line_no}: <hex_router 已自动处理, 见下方 Journal>"
                    )
                else:
                    out_lines.append(f"  L{line_no}: {line_content[:200]}")
                shown += 1

        return "\n".join(out_lines), written_files

