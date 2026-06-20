"""steghide adapter（per ``tools.md`` §3.5）

``steghide``：JPEG/BMP/WAV/AU 隐写检测。

**v0.5-philosophy-rethink 实战反馈 (2026-06-20)**:
- macOS 自带 steghide 编译时**未启用 JPEG 支持** (`otool -L` 没 libjpeg.dylib),
  对 JPEG 报 "can not read input file"
- 网上 writeup 用 Linux/Windows 的 steghide (官方源带 libjpeg)
- 修法: 优先用 **stegseek** (现代 fork, 原生 JPEG 支持 + 快 1000 倍)
- adapter 名字仍是 `steghide` (registry / pool 不变), 但实际跑 `stegseek` 二进制

**stegseek vs steghide**:
- stegseek 0.6 (`/Users/minzhizhou/.local/bin/stegseek`): JPEG/BMP/WAV/AU 全支持
  - `--crack <file> <wordlist> <out>` — 秒级 bruteforce (空 wordlist 抓空密码)
  - `--seed <file> <out>` — 慢但无密码 (4.3B seeds, 12+ 分钟)
- steghide 0.6: macOS 编译不带 JPEG, Linux/Windows 通常带
- 实测 123456cry.jpg (good-已合并.jpg) → stegseek 空 wordlist 抓到空密码,
  提取出 ko.txt 含 qwe.zip 密码 (`bV1g6t5wZDJif^J7`)

**adapter 设计** (v0.5-philosophy-rethink 边界):
- 主流程: 优先 stegseek, fallback steghide
- 检测策略: 空 wordlist (抓空密码 — CTF 常见)
- 不自动大 wordlist bruteforce (owner 决策 1 "auto_run 不抢 flag")
- 不跑 steghide extract (雕/抽 — 留给 GUI 工具栏/CLI 手工)

**v0.1.0b-PR2 范围 (历史, 仍 fallback 路径)**:
- 原 `steghide info` —— **不需要密码**就能报告文件是否含嵌入数据
- GUI 触发 `steghide extract -p <password>` 写到指定 outdir (用户操作)
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


# stegseek 输出格式
_STEGSEEK_PASSPHRASE_RE = re.compile(r'Found passphrase:\s*"([^"]*)"')
_STEGSEEK_FILENAME_RE = re.compile(r'Original filename:\s*"([^"]*)"')
_STEGSEEK_NO_DATA_HINTS = [
    "the file could not be decoded",
    "no data was extracted",
    "does not contain any stego data",
]

# steghide info 成功时的关键行（无密码也能获取的信息, 兼容 fallback 路径）
_STEGHIDE_CAPACITY_RE = re.compile(r"capacity:\s*(?P<cap>\d+\.?\d*)\s*(?P<unit>[KMG]B)")
_STEGHIDE_EMBED_RE = re.compile(r"embeds:\s*(?P<n>\d+)\s+files?")

# 错密码的强信号（说明文件 100% 含嵌入数据, fallback 路径）
_HAS_DATA_HINTS = [
    "could not extract any data with that passphrase",
    "the embedded data has been encrypted",
]

# steghide 调用失败的常见原因（macOS 编译限制 + 无 tty, fallback 路径）
_UNAVAILABLE_HINTS = [
    "can not read input file",  # 格式不支持
    "could not get terminal attributes",  # 无 tty 环境
]


@register_tool
class SteghideAdapter(ToolAdapter):
    """`steghide` adapter —— 检测文件是否含 steghide 嵌入数据.

    v0.5-philosophy-rethink: 内部优先 stegseek (macOS 现代 fork, JPEG 支持).
    adapter 名字仍叫 `steghide` (registry / pool 不变), 但调 `stegseek` 二进制.
    """

    name = "steghide"
    category = "steganography_image"
    description = (
        "JPEG/BMP/WAV/AU 隐写检测 — macOS 优先用 stegseek (现代 fork, JPEG 支持), "
        "fallback steghide (Linux/Windows)"
    )

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # v0.5-philosophy-rethink: 优先 stegseek, fallback steghide
        if shutil.which("stegseek"):
            return self._run_stegseek(file_path)
        return self._run_steghide_fallback(file_path)

    # ---------- v0.5: stegseek 主路径 (macOS 友好) ----------

    def _run_stegseek(self, file_path: str) -> ToolResult:
        """调 stegseek 检测 + 空 wordlist crack (抓空密码).

        不自动大 wordlist bruteforce (per owner 决策 1 "auto_run 不抢 flag").
        失败时: 报 SP 提示用户手工 bruteforce.
        """
        # 空 wordlist 文件 (抓空密码 — CTF 常见)
        empty_wordlist = self._ensure_empty_wordlist()

        # 临时输出文件
        out_fd, out_path = tempfile.mkstemp(suffix=".bin", prefix="stegseek_")
        os.close(out_fd)

        try:
            # -f flag 在 --crack 后 (避免 overwrite 提示触发 stegseek 的 tty check)
            # 删 out_path 如果存在 (双保险: stegseek 也用 -f 但旧文件可能还留着)
            Path(out_path).unlink(missing_ok=True)
            cmd = ["stegseek", "--crack", "-f", file_path, empty_wordlist, out_path]
            exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

            # stegseek 把所有 info 输出写到 stderr (not stdout!)
            # 合并 stdout + stderr 后 parse
            combined_output = stdout + "\n" + stderr
            suspicious: list[SuspiciousPoint] = []

            # 1. 找到密码 (空或非空) → 提取成功
            passphrase_match = _STEGSEEK_PASSPHRASE_RE.search(combined_output)
            if passphrase_match:
                passphrase = passphrase_match.group(1)
                filename_match = _STEGSEEK_FILENAME_RE.search(combined_output)
                original_filename = filename_match.group(1) if filename_match else "?"

                # 读提取内容
                try:
                    content_bytes = Path(out_path).read_bytes()
                    content_preview = content_bytes.decode(
                        "utf-8", errors="replace"
                    )[:500]
                except Exception:
                    content_preview = "(unable to read extracted file)"

                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="steghide_extracted",
                        offset=None,
                        matched_pattern=(
                            f"stegseek 找到密码: \"{passphrase}\"\n"
                            f"原始文件名: {original_filename}\n"
                            f"提取内容 ({len(content_bytes)} bytes): "
                            f"{content_preview}"
                        ),
                        severity=5,
                        suggested_action=(
                            f"已用密码 \"{passphrase}\" 提取嵌入数据 "
                            f"(原始文件名: {original_filename})\n"
                            f"提取内容预览: {content_preview[:200]}"
                        ),
                    )
                )
                return ToolResult(
                    tool_name=self.name,
                    exit_code=0,
                    stdout=stdout,
                    stderr=stderr,
                    suspicious_points=suspicious,
                    duration_ms=duration_ms,
                )

            # 2. 无嵌入数据 (stegseek 明确告知, 输出在 stderr)
            combined_lower = combined_output.lower()
            if any(hint in combined_lower for hint in _STEGSEEK_NO_DATA_HINTS):
                return ToolResult(
                    tool_name=self.name,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    suspicious_points=[],
                    duration_ms=duration_ms,
                )

            # 3. stegseek 跑完未提取成功 — 不写 SP
            # 原因: stegseek "Could not find a valid passphrase" 在 clean 文件
            #       和 "需要大 wordlist" 的情况下报同样的错 (二义性).
            #       写 steghide_embedded SP 会让 clean 文件误报.
            #       让用户从 journal 看 stegseek exit_code + output 决定是否手工 bruteforce.
            return ToolResult(
                tool_name=self.name,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                suspicious_points=suspicious,
                duration_ms=duration_ms,
            )
        finally:
            # cleanup temp out file
            try:
                Path(out_path).unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _ensure_empty_wordlist() -> str:
        """返回空 wordlist 路径 (CTF 常见空密码)."""
        wl_path = Path(tempfile.gettempdir()) / "stegseek_empty_wordlist.txt"
        if not wl_path.exists():
            wl_path.write_text("")
        return str(wl_path)

    # ---------- 原 steghide 路径 (Linux/Windows fallback) ----------

    def _run_steghide_fallback(self, file_path: str) -> ToolResult:
        """fallback: 调 steghide info (Linux/Windows 系统, steghide 编译带 JPEG).

        macOS 默认 steghide 编译不带 JPEG, 会报 "can not read input file"
        → 视为 steghide_unavailable SP 提示 (per v0.1 原始设计).
        """
        cmd = [self.binary_path or "steghide", "info", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

        # 信号 1：文件含嵌入数据（错密码信号）
        for hint in _HAS_DATA_HINTS:
            if hint in combined:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="steghide_embedded",
                        offset=None,
                        matched_pattern=f"steghide: {hint}",
                        severity=5,
                        suggested_action=(
                            "文件确认含 steghide 嵌入！建议在 GUI 中触发 "
                            "`steghide extract -p <password>` 提取（口令爆破可用 stegseek）"
                        ),
                    )
                )
                break

        # 信号 2：容量信息（无嵌入数据时输出）
        for m in _STEGHIDE_CAPACITY_RE.finditer(stdout):
            cap = m.group("cap") + m.group("unit")
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="steghide_capacity",
                    offset=None,
                    matched_pattern=f"steghide capacity: {cap}",
                    severity=1,
                    suggested_action="记录容量，便于估算嵌入数据大小",
                )
            )

        # 信号 3：嵌入文件数
        for m in _STEGHIDE_EMBED_RE.finditer(stdout):
            n = m.group("n")
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="steghide_embeds",
                    offset=None,
                    matched_pattern=f"steghide embeds: {n} files",
                    severity=3,
                    suggested_action=f"steghide 嵌入了 {n} 个文件，建议提取查看",
                )
            )

        # 信号 4：steghide 不支持格式（macOS 编译限制）/ 无 tty
        for hint in _UNAVAILABLE_HINTS:
            if hint in combined:
                if hint == "can not read input file":
                    matched = "steghide 编译未启用此格式支持（macOS 限制）"
                    action = (
                        "macOS 自带 steghide 编译时未启用此格式；"
                        "建议装 stegseek 替代（adapter 已自动优先 stegseek, "
                        "但本机未找到 stegseek 二进制）"
                    )
                else:  # could not get terminal attributes
                    matched = "steghide 需要 tty 环境（无 GUI 终端时不可用）"
                    action = (
                        "steghide 在 GUI/终端 tty 环境调用正常；"
                        "当前 subprocess 环境无 tty 触发其 isatty() 校验失败"
                    )
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="steghide_unavailable",
                        offset=None,
                        matched_pattern=matched,
                        severity=1,
                        suggested_action=action,
                    )
                )
                break

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
