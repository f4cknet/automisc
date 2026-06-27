"""ToolAdapter 抽象基类（per ``Architecture.md`` §4.1）

所有工具 adapter 必须：
1. 继承 ``ToolAdapter``
2. 定义类属性 ``name`` / ``category`` / ``description``
3. 实现 ``run(file_path: str) -> ToolResult``

注册：使用 ``@register_tool`` 装饰器（per ``Architecture.md`` §6.2）。
"""
from __future__ import annotations

import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from automisc.core.result import ToolResult


# 多编码 fallback 候选 (per Owner 2026-06-20 14:46 实测 GBK 中文乱码 bug)
# 顺序: 优先 utf-8 (国际通用), 然后东亚编码 (CTF 中文常用), 最后 latin-1 (永远成功兜底)
_DECODE_CANDIDATES = ("utf-8", "gbk", "gb18030", "big5", "shift_jis", "latin-1")


def _decode_output_bytes(data: bytes) -> str:
    """subprocess 输出 bytes 解码 — 多编码 fallback 选 0 U+FFFD 那个.

    背景 (per Owner 2026-06-20 14:46 实测):
    - macOS subprocess 默认 utf-8 解码, GBK 中文显示成 ⬛⬛⬛ (U+FFFD)
    - commit d500d79 修: 加 errors='replace' → 不 crash 但中文还是 ⬛
    - 本 commit 修: 多编码 fallback, 选 GBK 解出"看到这个图片就是压缩包的密码"

    策略:
    1. 试每个候选编码 (strict 模式) — 完美解码 = 0 U+FFFD, 立刻返回
    2. strict 全失败 → 试 errors='replace', 选 U+FFFD 最少的
    3. latin-1 永远成功 (map each byte to char), 兜底

    Args:
        data: subprocess stdout/stderr 原始 bytes

    Returns:
        解码后的 str (中文/英文混合都正确显示)
    """
    if not data:
        return ""

    # 阶段 1: strict 解码, 找 0 U+FFFD 的
    for enc in _DECODE_CANDIDATES:
        try:
            text = data.decode(enc)  # strict 默认
            return text  # 0 replacements (strict 不允许 replace)
        except UnicodeDecodeError:
            continue

    # 阶段 2: 全失败 → errors='replace' 选 U+FFFD 最少
    best_text = ""
    best_replacement = float("inf")
    for enc in _DECODE_CANDIDATES:
        text = data.decode(enc, errors="replace")
        replacement = text.count("\ufffd")
        if replacement < best_replacement:
            best_replacement = replacement
            best_text = text
            if replacement == 0:
                break  # latin-1 永远 0, 这里兜底

    return best_text


class ToolAdapter(ABC):
    """工具 adapter 抽象基类。

    子类定义：
    - ``name``: str（**必须唯一**）
    - ``category``: str（如 "binary_analysis" / "image_stego" / "shared"）
    - ``description``: str（GUI 菜单显示）
    - ``binary_path``: str | None（覆盖默认 PATH 查找；None = 走 ``shutil.which``）

    子类实现：
    - ``run(file_path: str) -> ToolResult``
    """

    name: str = ""
    category: str = ""
    description: str = ""
    binary_path: str | None = None

    # subprocess 默认超时（秒）；adapter 可在 run() 内覆盖
    default_timeout: float = 30.0

    # ---- 工具可达性 ----

    def check_available(self) -> bool:
        """检查外部工具是否在 PATH 或 extend-tools/ 可用。

        v0.5-platform-extend-tools: 走 `paths.resolve_tool_binary` (PATH 优先 →
        extend-tools/bin/<platform>/ fallback). 原 v0.5 仅查 shutil.which, Windows 上
        装到 extend-tools/ 的 binary 会显示不可用.

        - ``binary_path`` 显式设置: 检查文件是否存在 (覆盖默认)
        - 否则走 `paths.resolve_tool_binary` (跨平台)
        """
        if self.binary_path:
            return Path(self.binary_path).exists()
        from automisc.tools.paths import resolve_tool_binary
        return resolve_tool_binary(self.name) is not None

    # ---- 工具执行辅助 ----

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout: float | None = None,
    ) -> tuple[int, str, str, int]:
        """subprocess 包装（跨平台 PATH + stderr 分离 + 超时）。

        Returns:
            ``(exit_code, stdout, stderr, duration_ms)``

        输出解码: 多编码 fallback (`_decode_output_bytes`), 默认 utf-8 + GBK/gb18030 兜底.
        per Owner 14:46 实测: GBK 中文 (e.g. "看到这个图片就是压缩包的密码")
        默认 utf-8 解码失败 → 全局 fallback 让中文正确显示, 不再 ⬛⬛⬛.

        v0.5-platform-extend-tools (per Owner 2026-06-27 治理变更):
            - macOS: 显式追加 Homebrew 路径 (Apple Silicon + Intel)
            - Windows / Linux: 不动 (用系统 PATH + venv Scripts/ + extend-tools/bin/<platform>/)
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        start = time.monotonic()

        import os
        import sys as _sys
        env = os.environ.copy()
        if _sys.platform == "darwin":
            # macOS only: 显式追加 Homebrew 路径 (Apple Silicon + Intel)
            # Windows 上 /opt/homebrew/bin 不存在, 不能加 (会破坏 PATH `:` 分隔符)
            homebrew_paths = "/opt/homebrew/bin:/usr/local/bin"
            current_path = env.get("PATH", "")
            if homebrew_paths not in current_path:
                env["PATH"] = f"{homebrew_paths}:{current_path}"

        try:
            # 不传 text=True → 拿 bytes, 手动 decode (避免默认 utf-8 strict 抛错)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=effective_timeout,
                env=env,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _decode_output_bytes(proc.stdout)
            stderr = _decode_output_bytes(proc.stderr)
            return proc.returncode, stdout, stderr, duration_ms
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                124,  # 与 `timeout` CLI 工具一致
                "",
                f"subprocess timeout after {effective_timeout}s",
                duration_ms,
            )
        except FileNotFoundError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return 127, "", f"executable not found: {e}", duration_ms

    def _run_subprocess_with_input(
        self,
        cmd: list[str],
        input_text: str,
        *,
        timeout: float | None = None,
    ) -> tuple[int, str, str, int]:
        """subprocess 包装 + 自动喂 stdin（绕过交互式 y/n prompt）。

        Returns:
            同 ``_run_subprocess``

        输出解码: 同 _run_subprocess, 多编码 fallback.
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        start = time.monotonic()

        import os
        import sys as _sys
        env = os.environ.copy()
        if _sys.platform == "darwin":
            # macOS only (Windows / Linux 不加 homebrew 路径)
            homebrew_paths = "/opt/homebrew/bin:/usr/local/bin"
            current_path = env.get("PATH", "")
            if homebrew_paths not in current_path:
                env["PATH"] = f"{homebrew_paths}:{current_path}"

        try:
            # 不传 text=True → bytes mode
            proc = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                timeout=effective_timeout,
                env=env,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _decode_output_bytes(proc.stdout)
            stderr = _decode_output_bytes(proc.stderr)
            return proc.returncode, stdout, stderr, duration_ms
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                124,
                "",
                f"subprocess timeout after {effective_timeout}s",
                duration_ms,
            )
        except FileNotFoundError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return 127, "", f"executable not found: {e}", duration_ms

    # ---- 抽象方法 ----

    @abstractmethod
    def run(self, file_path: str) -> ToolResult:
        """执行工具 + 解析输出 + 提取可疑点。"""
        raise NotImplementedError