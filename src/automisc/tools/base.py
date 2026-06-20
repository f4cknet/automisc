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
        """检查外部工具是否在 PATH 可用。

        - ``binary_path`` 非空：检查文件是否存在
        - 否则走 ``shutil.which(self.name)``
        """
        if self.binary_path:
            return Path(self.binary_path).exists()
        return shutil.which(self.name) is not None

    # ---- 工具执行辅助 ----

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout: float | None = None,
    ) -> tuple[int, str, str, int]:
        """subprocess 包装（macOS PATH 显式指定 + stderr 分离 + 超时）。

        Returns:
            ``(exit_code, stdout, stderr, duration_ms)``
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        start = time.monotonic()

        # per Architecture.md §4.3：macOS subprocess PATH 沙箱处理
        # 显式追加 Homebrew 路径（Apple Silicon + Intel）
        import os
        env = os.environ.copy()
        homebrew_paths = "/opt/homebrew/bin:/usr/local/bin"
        current_path = env.get("PATH", "")
        if homebrew_paths not in current_path:
            env["PATH"] = f"{homebrew_paths}:{current_path}"

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                # 修 UnicodeDecodeError: binary tool (foremost/unzip/sevenz) 输出非 UTF-8 字节时,
                # 默认 errors='strict' 直接抛异常挂掉. 用 'replace' 把无效字节 → U+FFFD,
                # 日志完整可见 (per Owner "宁可多给错给, 也不能少给" 铁律).
                errors="replace",
                timeout=effective_timeout,
                env=env,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return proc.returncode, proc.stdout, proc.stderr, duration_ms
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
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        start = time.monotonic()

        import os
        env = os.environ.copy()
        homebrew_paths = "/opt/homebrew/bin:/usr/local/bin"
        current_path = env.get("PATH", "")
        if homebrew_paths not in current_path:
            env["PATH"] = f"{homebrew_paths}:{current_path}"

        try:
            proc = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                # 同 _run_subprocess: 修 binary tool 非 UTF-8 字节触发的 UnicodeDecodeError
                errors="replace",
                timeout=effective_timeout,
                env=env,
                check=False,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return proc.returncode, proc.stdout, proc.stderr, duration_ms
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