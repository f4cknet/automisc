"""steghide adapter (per ``tools.md`` §3.5, v0.5-stegseek-remove 重构)

**用途**: JPEG/BMP/WAV/AU 隐写探测 (auto_run 6 工具之一).

**决策树 (per v0.5-stegseek-remove 2026-06-28)**:

```
输入: stego 文件
  1. steghide info (无密码探测) → 容量/嵌入数
  2. steghide extract -p "" (空密码探测, CVE-2021-27211 兜底) → 5s timeout
  3. 综合 SP:
     - 提取成功 → steghide_extracted SP sev=5
     - 容量/嵌入数 → steghide_capacity / steghide_embeds SP sev=1/3
     - 含嵌入但密码非空 → steghide_embedded SP sev=5 (提示用户 GUI 工具栏字典爆破)
  4. 不跑大 wordlist bruteforce (per Owner 决策 + 铁律 7 "auto_run 不抢 flag")
     留 GUI 工具栏 Steghide 子菜单手动 (SteghideCrackAction 走 wordlist loop)
```

**v0.5-philosophy-rethink 历史 (per 之前 stegseek 优先逻辑, 已废弃)**:
- 原 adapter name="stegseek" 内部调 stegseek 0.6 binary (macOS 友好, JPEG 支持)
- 实际 Win/Linux 走 steghide fallback
- 删 stegseek (per v0.5-stegseek-remove 2026-06-28 Owner 拍板, Win 端不可用 + 命名误导)
- 统一走 steghide (per v0.5-windows-only 治理, 项目 Win only)

**owner 实战命中** (per v0.5-train-009 / v0.5-train-010 / 123456cry.jpg):
- 123456cry.jpg (good-已合并.jpg) → steghide 实际跑空密码命中, 提取 ko.txt
  含 qwe.zip 密码 (bV1g6t5wZDJif^J7)
- Win 端之前 silent miss: steghide info 不含密码, 实际命中靠空密码 extract

**v0.5-stegseek-remove 改造 (2026-06-28)**:
- name 改回 "steghide" (从 "stegseek")
- 删 _run_stegseek 方法 (stegseek binary 不再调用)
- 改 _run_steghide_fallback 加空密码 extract 兜底 (CVE-2021-27211)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter
from automisc.tools.paths import resolve_tool_binary


# steghide info 成功时的关键行（无密码也能获取的信息）
_STEGHIDE_CAPACITY_RE = re.compile(r"capacity:\s*(?P<cap>\d+\.?\d*)\s*(?P<unit>[KMG]B)")
_STEGHIDE_EMBED_RE = re.compile(r"embeds:\s*(?P<n>\d+)\s*files?")
_STEGHIDE_ORIG_FILENAME_RE = re.compile(r'Original filename:\s*"([^"]*)"')

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
    """`steghide` adapter —— JPEG/BMP/WAV/AU 隐写探测 (auto_run 6 工具之一).

    v0.5-stegseek-remove: 删 stegseek 优先逻辑, 统一走 steghide.
    """

    name = "steghide"
    category = "steganography_image"
    description = (
        "JPEG/BMP/WAV/AU 隐写探测 (v0.5-stegseek-remove 重构) — "
        "steghide info + 空密码 extract 兜底 (CVE-2021-27211), "
        "5s timeout 内完成"
    )

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        return self._run_steghide(file_path)

    # ---------- v0.5-stegseek-remove: 统一 steghide 路径 ----------

    def _run_steghide(self, file_path: str) -> ToolResult:
        """steghide info (无密码探测) + 空密码 extract (CVE-2021-27211 兜底).

        1. 跑 steghide info → 容量/嵌入数 / 含嵌入数据信号
        2. 跑 steghide extract -p "" → 空密码命中探测 (CTF 常见, e.g. 123456cry.jpg good-已合并.jpg)
        3. 综合 SP 输出
        """
        steghide_bin = resolve_tool_binary("steghide")
        if not steghide_bin:
            return self._unavailable_result(
                "steghide 二进制未找到 (PATH 缺失或 extend-tools 未装)"
            )

        # 1) steghide info (无密码探测)
        cmd = [steghide_bin, "info", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)
        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

        # 信号 1: 文件含嵌入数据（错密码信号）
        has_embedded = False
        for hint in _HAS_DATA_HINTS:
            if hint in combined:
                has_embedded = True
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
                            "文件确认含 steghide 嵌入！建议在 GUI 工具栏 "
                            "Steghide 子菜单 → 字典暴力破解 (SteghideCrackAction) 尝试"
                        ),
                    )
                )
                break

        # 信号 2: 容量信息
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

        # 信号 3: 嵌入文件数
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

        # 信号 4: steghide 不支持格式 / 无 tty
        for hint in _UNAVAILABLE_HINTS:
            if hint in combined:
                if hint == "can not read input file":
                    matched = "steghide 编译未启用此格式支持（macOS 限制）"
                    action = (
                        "macOS 自带 steghide 编译时未启用此格式；"
                        "建议装 stegseek 替代 (但 per v0.5-stegseek-remove 已删 stegseek, "
                        "Win/Linux 端此格式不支持属正常)"
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

        # 2) 空密码 extract 兜底 (CVE-2021-27211, CTF 常见空密码场景)
        # 只在 has_embedded 命中 OR info 没说 "无嵌入" 时尝试 (节省 5s)
        empty_pw_sp = self._try_empty_password_extract(
            steghide_bin, file_path, has_embedded
        )
        if empty_pw_sp is not None:
            suspicious.append(empty_pw_sp)

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )

    def _try_empty_password_extract(
        self, steghide_bin: str, file_path: str, has_embedded: bool
    ) -> SuspiciousPoint | None:
        """尝试空密码 extract (CVE-2021-27211 兜底).

        Returns:
            SuspiciousPoint if 命中 (severity 5, 提取内容预览);
            None if 未命中 / 错密码 / 不支持 (caller 不写 SP).
        """
        # 临时输出文件
        out_fd, out_path = tempfile.mkstemp(
            suffix=".bin", prefix="steghide_empty_pw_"
        )
        os.close(out_fd)

        try:
            # -sf source -p "" (空密码) -xf out -f (force overwrite)
            cmd = [
                steghide_bin, "extract",
                "-sf", str(file_path),
                "-p", "",
                "-xf", str(out_path),
                "-f",
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,  # 空密码 extract 5s 上限 (CVE-2021-27211 场景秒级)
                    errors="replace",
                )
            except subprocess.TimeoutExpired:
                return None

            # 命中: exit 0 + output 文件存在 + 有内容
            if (
                proc.returncode == 0
                and Path(out_path).exists()
                and Path(out_path).stat().st_size > 0
            ):
                content = Path(out_path).read_bytes()
                content_preview = content.decode("utf-8", errors="replace")[:500]
                return SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="steghide_extracted",
                    offset=None,
                    matched_pattern=(
                        f"steghide 空密码命中 (CVE-2021-27211)!\n"
                        f"提取内容 ({len(content)} bytes): {content_preview}"
                    ),
                    severity=5,
                    suggested_action=(
                        f"steghide 用空密码提取成功! "
                        f"内容预览: {content_preview[:200]}"
                    ),
                )
            return None
        finally:
            Path(out_path).unlink(missing_ok=True)

    def _unavailable_result(self, reason: str) -> ToolResult:
        """steghide 不可用时的 fallback ToolResult."""
        return ToolResult(
            tool_name=self.name,
            exit_code=127,
            stdout="",
            stderr=reason,
            suspicious_points=[
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path="",
                    category="steghide_unavailable",
                    offset=None,
                    matched_pattern=reason,
                    severity=1,
                    suggested_action=(
                        "Win 端装 steghide 到 extend-tools/bin/win-x64/ "
                        "(per v0.5-windows-tool-compat manifest.yaml steghide v0.5.1-cygwin)"
                    ),
                )
            ],
            duration_ms=0,
        )
