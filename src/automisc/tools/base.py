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

    v0.5-fix-find-suspicious-race-condition (per Owner 2026-06-29 22:57 拍板 A):
    - 持有嵌套 subprocess handle (`_current_proc`), 允许 orchestrator 强 terminate
    - 拖新文件时清旧 subprocess, 避免旧 steghide 30s timeout 段在 archive pool 之后
      写入新 output 区 (race condition)
    """

    name: str = ""
    category: str = ""
    description: str = ""
    binary_path: str | None = None

    # subprocess 默认超时（秒）；adapter 可在 run() 内覆盖
    default_timeout: float = 30.0

    # v0.5-fix-find-suspicious-race-condition: 当前 adapter 持有的 Popen handle
    # (None = 没在跑). orchestrator._last_adapter 持有, run_tool 入口先 _terminate_current_proc
    # idempotent 清旧. 详见 upgrade/v0.5-fix-find-suspicious-race-condition.md
    _current_proc: subprocess.Popen | None = None

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
        """subprocess 包装（跨平台 PATH + stderr 分离 + 超时 + race protection）。

        Returns:
            ``(exit_code, stdout, stderr, duration_ms)``

        输出解码: 多编码 fallback (`_decode_output_bytes`), 默认 utf-8 + GBK/gb18030 兜底.
        per Owner 14:46 实测: GBK 中文 (e.g. "看到这个图片就是压缩包的密码")
        默认 utf-8 解码失败 → 全局 fallback 让中文正确显示, 不再 ⬛⬛⬛.

        v0.5-platform-extend-tools (per Owner 2026-06-27 治理变更):
            - macOS: 显式追加 Homebrew 路径 (Apple Silicon + Intel)
            - Windows / Linux: 不动 (用系统 PATH + venv Scripts/ + extend-tools/bin/<platform>/)

        v0.5-fix-find-suspicious-race-condition (per Owner 2026-06-29 22:57 拍板 A):
            - 用 subprocess.Popen 替代 subprocess.run, 持有 handle (self._current_proc)
            - 允许 orchestrator._terminate_current_proc() 强 terminate (拖新文件时清旧)
            - run() 入口先 _terminate_current_proc() idempotent (重入保护, 旧 adapter 实例复用)
        """
        # 重入保护: 旧 adapter 实例可能复用 (per v0.1.1 ToolAdapter 单例模式),
        # 跑新工具前先清旧 subprocess, 避免 2 个 Popen 同时跑
        self._terminate_current_proc()

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

        proc: subprocess.Popen | None = None
        try:
            # Popen 持有 handle → allow 强 terminate (vs subprocess.run 同步阻塞)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            self._current_proc = proc
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                # v0.5-fix-find-suspicious-race-condition: 超时强 kill (之前只等)
                proc.kill()
                proc.wait()
                duration_ms = int((time.monotonic() - start) * 1000)
                return (
                    124,
                    "",
                    f"subprocess timeout after {effective_timeout}s",
                    duration_ms,
                )
            self._current_proc = None
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _decode_output_bytes(stdout_bytes)
            stderr = _decode_output_bytes(stderr_bytes)
            return proc.returncode, stdout, stderr, duration_ms
        except FileNotFoundError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return 127, "", f"executable not found: {e}", duration_ms
        finally:
            # 清理 handle (正常完成 / 异常 都清)
            self._current_proc = None

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
        # v0.5-fix-find-suspicious-race-condition: 同 _run_subprocess, Popen + handle
        self._terminate_current_proc()

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

        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            self._current_proc = proc
            try:
                stdout_bytes, stderr_bytes = proc.communicate(
                    input=input_text.encode("utf-8", errors="replace"),
                    timeout=effective_timeout,
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                duration_ms = int((time.monotonic() - start) * 1000)
                return (
                    124,
                    "",
                    f"subprocess timeout after {effective_timeout}s",
                    duration_ms,
                )
            self._current_proc = None
            duration_ms = int((time.monotonic() - start) * 1000)
            stdout = _decode_output_bytes(stdout_bytes)
            stderr = _decode_output_bytes(stderr_bytes)
            return proc.returncode, stdout, stderr, duration_ms
        except FileNotFoundError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return 127, "", f"executable not found: {e}", duration_ms
        finally:
            self._current_proc = None

    def _terminate_current_proc(self) -> None:
        """v0.5-fix-find-suspicious-race-condition: 强 kill 当前 adapter 持有的嵌套 subprocess (if any).

        调用场景:
        1. orchestrator.run_tool 入口 → 重入保护 (旧 adapter 实例复用, 跑新工具前先清)
        2. main_window._on_new_file_selected → 拖新文件时清旧 subprocess (避免 30s timeout 段
           在 archive pool 之后写入新 output 区)

        实现: terminate() 给 1s 优雅, 然后 kill() 强杀 (Win process tree 不一定跟 terminate 走).
        Idempotent: 多次调用不抛, 没 _current_proc 啥也不做.
        """
        if self._current_proc is None:
            return
        proc = self._current_proc
        # 先 poll 一次, 已结束就不必 kill
        if proc.poll() is not None:
            self._current_proc = None
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                # terminate 1s 没响应 → 强 kill
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except Exception:
                    pass
        except Exception:
            # Popen 已经死了 / 权限问题 / etc → 静默
            pass
        finally:
            self._current_proc = None

    # ---- 抽象方法 ----

    @abstractmethod
    def run(self, file_path: str) -> ToolResult:
        """执行工具 + 解析输出 + 提取可疑点。"""
        raise NotImplementedError