"""trid adapter（per v0.5-trid-toolbar spec）

``TrID/32 v2.24`` (Marco Pontello, 2003-16)：基于 binary signature pattern
的文件类型签名识别器，跟 ``file`` / libmagic 互补 — ``file`` 看 magic bytes,
``trid`` 看 data frequency signature,输出 N 个候选 + 概率。

实战场景：
- 扩展名伪装识别 (file 后缀 .png 但 trid 100% ZIP) → sev=4 可疑
- 跟 file 互补 (file 单行定性, trid 多候选概率)

**完全离线约束** (per STRUCTURE.md §1)：
- trid 默认从 mark0.net 在线拉 defs
- adapter **显式** ``-d:<abs_path_to_triddefs.trd>`` 锁本地 defs
- defs 包路径从 ``trid.exe`` 同目录推导 (``TrID/triddefs.trd``)

**v0.5-trid-toolbar 决策**：
- 不进 auto-run 图片池 (per AGENTS §5.2, ``file`` 已在 shared 履行同类职责)
- 不实现 ``-ce`` (rename extension, **写文件** — 违反"半自动不抢 flag")
- 不实现 ``-ns`` / ``-@`` / ``-v`` / ``-ae`` (over-engineering, Owner 没要)
"""
from __future__ import annotations

import re
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# trid 候选行 2 种格式:
#   "  90.5% (.EXE) FreeBASIC 1.0x Win32 Executable (792408/92/73)"  — 3 段 pointer/count/rest
#   "100.0% (.PNG) Portable Network Graphics (16000/1)"             — 2 段 pointer/count
# 容忍 pct 前单空格（trid 输出真实格式）。
# desc 不含 " (" 前缀, `\s+\(...\)` 强制 separator;
# rest 段 optional (3 段格式才有, 2 段格式无).
_CANDIDATE_RE = re.compile(
    r"^\s*(?P<pct>\d+(?:\.\d+)?)%\s+"
    r"\(\.(?P<ext>[A-Z0-9]+)\)\s+"
    r"(?P<desc>.+?)"
    r"\s+\("
    r"(?P<sig_id>\d+)/(?P<sig_count>\d+)"
    r"(?:/(?P<sig_rest>\d+))?"
    r"\)\s*$"
)

# trid header / banner / Collecting 行（用于过滤，parse 阶段跳过）.
_HEADER_MARKERS = (
    "TrID/32",
    "Definitions found",
    "Analyzing...",
    "Collecting data from file",
)


def _file_ext(file_path: str) -> str:
    """从文件路径提取纯扩展名（小写），无扩展名返回空串."""
    p = Path(file_path)
    if p.suffix:
        return p.suffix.lstrip(".").lower()
    return ""


@register_tool
class TridAdapter(ToolAdapter):
    """``trid`` adapter —— 基于 signature pattern 的文件类型识别器."""

    name = "trid"
    category = "shared"
    description = "基于 signature pattern 识别文件类型（候选列表 + 概率，候选 vs 后缀 mismatch → sev=4）"

    # trid 加载 5.8MB defs + 扫文件 — 5-30s 范围，给 60s 兜底
    default_timeout = 60.0

    def run(self, file_path: str) -> ToolResult:
        # 1) 解析 binary: 走 resolve_tool_binary (per v0.5-platform-extend-tools)
        #    macOS 命中 PATH (brew);Win 命中 extend-tools/bin/win-x64/TrID/trid.exe
        #    (异名 subdir fallback, per v0.5-extend-tools-subdir-flexible)
        from automisc.tools.paths import resolve_tool_binary

        if self.binary_path:
            trid_bin = self.binary_path
        else:
            trid_bin = resolve_tool_binary(self.name) or self.name

        # 2) 显式锁本地 defs (per §完全离线约束 above)
        #    defs 包跟 trid.exe 同目录 (per Owner 部署 layout)
        trid_dir = Path(trid_bin).parent
        defs_path = trid_dir / "triddefs.trd"
        if not defs_path.exists():
            # defs 包缺失 (Owner 误删/未部署) — 仍调 trid, 让 trid 走默认 (在线),
            # stderr 会报, ToolResult 仍包含该 stderr 提示手工补 defs
            defs_arg: str | None = None
        else:
            defs_arg = f"-d:{defs_path.resolve()}"

        # 3) 命令: trid -d:<abs_defs> -n:5 <file>
        #    -n:5 限制输出最多 5 候选 (top 概率优先), 防超大 stdout
        cmd: list[str]
        if defs_arg is not None:
            cmd = [trid_bin, defs_arg, "-n:5", file_path]
        else:
            cmd = [trid_bin, "-n:5", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        # 4) 解析候选行 + 写 SP
        suspicious, top_candidate = self._parse_candidates(file_path, stdout)

        # 5) 后缀 vs top candidate mismatch → sev=4 ⚠️ (per spec §4.3)
        #    仅 top 候选存在时判定; 0 候选不入 mismatch (走 no_candidates)
        file_ext = _file_ext(file_path)
        if top_candidate is not None and file_ext:
            trid_ext = top_candidate["ext"].lower()
            if trid_ext and trid_ext != file_ext:
                mismatch_sp = SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="file_type_mismatch",
                    offset=None,
                    matched_pattern=(
                        f"扩展名 .{file_ext} 但 trid top 候选 "
                        f".{trid_ext} ({top_candidate['desc']}, "
                        f"{top_candidate['pct']}%)"
                    ),
                    severity=4,
                    suggested_action=(
                        f"疑似扩展名伪装 — 改后缀为 .{trid_ext} 重跑确认, "
                        f"或对比 file / xxd 头 16 字节判定真格式"
                    ),
                    context=f"top candidate from trid -n:5",
                )
                suspicious.append(mismatch_sp)

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )

    def _parse_candidates(
        self, file_path: str, stdout: str
    ) -> tuple[list[SuspiciousPoint], dict | None]:
        """解析 trid stdout → SuspiciousPoint 列表 + top candidate.

        Args:
            file_path: 输入文件路径 (SP.context)
            stdout: trid.exe stdout (per §4.2 spec)

        Returns:
            (suspicious_points, top_candidate)

            - top_candidate: 概率最高的候选 dict {pct, ext, desc} 或 None
              (trid 0 命中时返回 None, 不入 file_type_mismatch 判定)
            - suspicious_points:
              * 0 命中 → 1 条 sev=1 SP (`no_candidates`)
              * 命中 ≥1 → 1 条 sev=1 SP (`file_type_trid`, 描述 top 候选)
              * top pct < 50% → 加 1 条 sev=3 SP (`file_type_low_confidence`)
        """
        candidates: list[dict] = []
        for line in stdout.splitlines():
            # 跳过 banner / header / Collecting 行
            stripped = line.strip()
            if not stripped or any(m in line for m in _HEADER_MARKERS):
                continue
            m = _CANDIDATE_RE.match(line)
            if not m:
                continue
            candidates.append(
                {
                    "pct": float(m.group("pct")),
                    "ext": m.group("ext"),
                    "desc": m.group("desc").strip(),
                    "sig_id": m.group("sig_id"),
                }
            )

        suspicious: list[SuspiciousPoint] = []

        if not candidates:
            # 0 命中: 极冷门格式 / 二进制损坏 / defs 包过时
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="no_candidates",
                    offset=None,
                    matched_pattern="trid 未识别（0 候选命中）",
                    severity=1,
                    suggested_action=(
                        "trid 未识别（极冷门格式 / 二进制损坏 / defs 包过时）\n"
                        "  对照 xxd 头 16 字节 vs KNOWN_MAGIC, 或 strings | grep 找 magic"
                    ),
                )
            )
            return suspicious, None

        # 按概率排序
        candidates.sort(key=lambda c: c["pct"], reverse=True)
        top = candidates[0]

        # top candidate SP (sev=1, 默认)
        suspicious.append(
            SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="file_type_trid",
                offset=None,
                matched_pattern=(
                    f".{top['ext']} — {top['desc']} ({top['pct']}%, "
                    f"{len(candidates)} 候选)"
                ),
                severity=1,
                suggested_action=(
                    f"trid 判定最可能 .{top['ext']} ({top['desc']}, 概率 {top['pct']}%)\n"
                    f"  共 {len(candidates)} 候选, 完整输出见 stdout"
                ),
            )
        )

        # top 概率 < 50% → 加低置信度警告
        if top["pct"] < 50.0 and len(candidates) >= 2:
            second = candidates[1]
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="file_type_low_confidence",
                    offset=None,
                    matched_pattern=(
                        f"top 概率仅 {top['pct']}%, 第二候选 ."
                        f"{second['ext']} ({second['pct']}%)"
                    ),
                    severity=3,
                    suggested_action=(
                        f"trid 识别不确定, top .{top['ext']} ({top['pct']}%) "
                        f"vs .{(second['ext']).lower()} ({second['pct']}%)\n"
                        f"  对照 file 命令 / xxd 头 16 字节辅助判定, "
                        f"或 foremost binwalk 雕文件看内嵌格式"
                    ),
                )
            )

        return suspicious, top


__all__ = ["TridAdapter"]
