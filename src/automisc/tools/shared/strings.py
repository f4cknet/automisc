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
        rendered_stdout = self._render_output(raw_stdout, suspicious, file_path=file_path)

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=rendered_stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )

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
                results.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category=f"{category_label}_line{line_no}",
                        offset=None,
                        matched_pattern=m.value[:120],
                        severity=m.severity,
                        suggested_action=suggested,
                    )
                )
        return results

    def _render_output(self, raw_stdout: str, suspicious: list[SuspiciousPoint], file_path: str = "") -> str:
        """v0.5-truncate-output: 渲染版 stdout.

        Args:
            raw_stdout: strings 命令原始输出
            suspicious: rule_scanner 命中 list (含 line_no via category "<label>_lineN")
            file_path: 输入文件路径 (用于提示 "想看原文: strings -a -n 4 <file>")

        Returns:
            渲染版: header + 命中行 (max MAX_RENDERED_HITS) + summary
            (省略 raw 中未命中行, 防大文件占满窗口)
        """
        lines = raw_stdout.splitlines()
        total_lines = len(lines)

        if not suspicious:
            return (
                f"=== strings 摘要 (v0.5-truncate-output) ===\n"
                f"  total_lines: {total_lines}\n"
                f"  suspicious: 0\n"
                f"  └─ 无可疑特征, raw stdout 已省略 (想看原文: `strings -a -n 4 {file_path}`)\n"
            )

        # 提取 line_no from suspicious category (e.g. "hex_line42")
        hit_line_nos: set[int] = set()
        for sp in suspicious:
            try:
                # category 格式 "<label>_lineN"
                ln_str = sp.category.rsplit("_line", 1)[-1]
                hit_line_nos.add(int(ln_str))
            except (ValueError, IndexError):
                pass

        # 拼渲染版
        out_lines = [
            f"=== strings 摘要 (v0.5-truncate-output) ===",
            f"  total_lines: {total_lines}",
            f"  suspicious:  {len(suspicious)} (raw stdout 1000+ 行已省略, 只显示命中行)",
            "",
            f"--- 命中行 (max {self.MAX_RENDERED_HITS} 显示) ---",
        ]
        shown = 0
        for line_no in sorted(hit_line_nos):
            if 1 <= line_no <= total_lines:
                if shown >= self.MAX_RENDERED_HITS:
                    out_lines.append(f"  ... 还有 {len(hit_line_nos) - shown} 行未显示")
                    break
                out_lines.append(f"  L{line_no}: {lines[line_no - 1][:200]}")
                shown += 1

        return "\n".join(out_lines)

