"""测试 tools/base.py — subprocess.run 加 errors='replace' 防 UnicodeDecodeError.

背景: Owner 实测 (2026-06-20 12:50) foremost / unzip 跑 binary 文件
触发 UnicodeDecodeError ('utf-8' codec can't decode byte 0xa5/0xd5):
- Python 3.13 subprocess 默认 errors='strict', binary 工具输出非 UTF-8 字节时挂掉
- 修法: subprocess.run 加 errors='replace' (无效字节 → U+FFFD, 日志完整可见)

为什么 'replace' 不是 'ignore':
- 'ignore' 静默丢字节 → foremost 解出 123456cry.jpg 但日志看不到关键片段
- 'replace' 把无效字节 → U+FFFD → 日志完整, 人眼能看出"这有乱码"
- 'backslashreplace' 太啰嗦, 不适合 foremost 输出
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.result import ToolResult
from automisc.tools.base import ToolAdapter


class _MinimalAdapter(ToolAdapter):
    name = "_minimal"
    category = "test"

    def run(self, file_path: str) -> ToolResult:
        cmd = [self.binary_path or "echo", "hi"]
        ec, out, err, dur = self._run_subprocess(cmd)
        return ToolResult(
            tool_name=self.name, exit_code=ec, stdout=out, stderr=err, duration_ms=dur,
        )


class _MinimalAdapterWithInput(ToolAdapter):
    name = "_minimal_input"
    category = "test"

    def run(self, file_path: str) -> ToolResult:
        cmd = [self.binary_path or "cat"]
        ec, out, err, dur = self._run_subprocess_with_input(cmd, "test input")
        return ToolResult(
            tool_name=self.name, exit_code=ec, stdout=out, stderr=err, duration_ms=dur,
        )


# ---------- 验证 errors='replace' 真的传入 subprocess.run ----------

def test_run_subprocess_passes_errors_replace():
    """_run_subprocess 调 subprocess.run 时必须传 errors='replace'.

    这是修 UnicodeDecodeError 的关键 — Python 3.13 默认 errors='strict'
    会抛 UnicodeDecodeError 挂掉整个 adapter (foremost/unzip 跑 binary 文件时).
    """
    a = _MinimalAdapter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["echo"], returncode=0, stdout="hi", stderr="",
        )
        a._run_subprocess(["echo", "hi"])

    # 验证调用 kwargs 含 errors='replace'
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("errors") == "replace", (
        f"_run_subprocess 没传 errors='replace', call_kwargs={call_kwargs}"
    )
    # 也确认 text=True 保留 (decoded 模式)
    assert call_kwargs.get("text") is True


def test_run_subprocess_with_input_passes_errors_replace():
    """_run_subprocess_with_input 同样必须传 errors='replace'."""
    a = _MinimalAdapterWithInput()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["cat"], returncode=0, stdout="test input", stderr="",
        )
        a._run_subprocess_with_input(["cat"], "test input")

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("errors") == "replace", (
        f"_run_subprocess_with_input 没传 errors='replace', call_kwargs={call_kwargs}"
    )


# ---------- 集成: 真 subprocess 跑 binary 输出 (不 mock) ----------

def test_run_subprocess_handles_non_utf8_bytes(tmp_path: Path):
    """binary 工具输出非 UTF-8 字节 (e.g. 0xa5, 0xd5) 不再抛 UnicodeDecodeError.

    模拟: 'printf' 输出含 0xa5 字节 → 之前 Python 3.13 会抛 UnicodeDecodeError,
    现在 errors='replace' 把 0xa5 → U+FFFD, _run_subprocess 正常返回.
    """
    a = _MinimalAdapter()
    # 构造输出含 UTF-8 非法字节的命令
    # python3 -c 'print(bytes([0xa5, 0x68, 0x69]).decode("utf-8", errors="replace"))'
    # → U+FFFD + hi
    cmd = [
        "python3", "-c",
        "import sys; sys.stdout.buffer.write(bytes([0xa5, 0x68, 0x69]))",
    ]
    # 验证 python3 可用
    import shutil
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    # 之前: UnicodeDecodeError
    # 现在: stdout = "\ufffdhi" (replace 模式)
    ec, out, err, dur = a._run_subprocess(cmd)
    assert ec == 0, f"unexpected exit: {err}"
    # 0xa5 被替换为 U+FFFD, 0x68 0x69 是 "hi"
    assert "\ufffd" in out or "hi" in out, (
        f"output should contain replacement char or 'hi', got: {out!r}"
    )


# ---------- 集成: 真 adapter 跑 (用真实 foremost --help 验证不挂) ----------

def test_foremost_adapter_help_does_not_crash():
    """foremost --help 输出含 binary 字符, 不应挂掉 (per errors='replace' 修复)."""
    from automisc.tools.shared.foremost import ForemostAdapter
    import shutil

    if not shutil.which("foremost"):
        pytest.skip("foremost not installed")

    a = ForemostAdapter()
    # 不跑真实雕文件, 只调 foremost --help 验证 adapter _run_subprocess 不抛 UnicodeDecodeError
    cmd = ["foremost", "-h"]
    ec, out, err, dur = a._run_subprocess(cmd)
    # foremost --help 应该正常返回 (exit 0 或 1 都 OK, 不抛异常即可)
    assert ec in (0, 1), f"unexpected exit code: {ec}"
    # 至少 stdout 或 stderr 应该有内容
    assert out or err, "foremost -h returned empty output"


def test_unzip_adapter_help_does_not_crash():
    """unzip 输出的版本信息偶尔含非 UTF-8 字符, 不应挂掉."""
    from automisc.tools.misc.archive.unzip import UnzipAdapter
    import shutil

    if not shutil.which("unzip"):
        pytest.skip("unzip not installed")

    a = UnzipAdapter()
    # unzip -v 输出版本信息, 含 "Zip" 等英文 + 偶尔 binary 控制字符
    cmd = ["unzip", "-v"]
    ec, out, err, dur = a._run_subprocess(cmd)
    assert ec == 0, f"unexpected exit: {err}"
    # 至少应有版本信息
    assert "UnZip" in out or "Zip" in out, f"unzip -v output unexpected: {out[:100]!r}"
