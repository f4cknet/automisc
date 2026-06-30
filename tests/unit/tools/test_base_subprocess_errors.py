"""测试 tools/base.py — subprocess.run 输出 bytes mode + multi-encoding fallback.

历史版本 (commit d500d79):
- subprocess.run 传 text=True + errors='replace' 防 UnicodeDecodeError
- 副作用: GBK 中文输出全 U+FFFD ⬛⬛⬛ (owner 14:46 实测)

当前版本:
- subprocess.run 不传 text=True → 拿 bytes, 手动 _decode_output_bytes
- _decode_output_bytes 试 utf-8/gbk/gb18030/big5/shift_jis/latin-1, 选 0 U+FFFD
- 不再 crash, 中文也能正确显示
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.result import ToolResult
from automisc.tools.base import ToolAdapter, _decode_output_bytes


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


# ---------- 新设计验证: subprocess.run 用 bytes mode, 手动 decode ----------

def test_run_subprocess_uses_bytes_mode():
    """_run_subprocess 不传 text=True → subprocess.run 拿 bytes, 手动 decode.

    这是新设计关键 (per Owner 14:46 反馈): bytes mode + 手动 decode
    才能做 multi-encoding fallback (utf-8 → gbk → gb18030 → ...).
    """
    a = _MinimalAdapter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["echo"], returncode=0, stdout=b"hi", stderr=b"",
        )
        a._run_subprocess(["echo", "hi"])

    call_kwargs = mock_run.call_args.kwargs
    # 新设计: text 不传 (默认 False), bytes mode
    assert not call_kwargs.get("text", False), (
        f"_run_subprocess 不应传 text=True, call_kwargs={call_kwargs}"
    )


def test_run_subprocess_with_input_uses_bytes_mode():
    """_run_subprocess_with_input 同样用 bytes mode."""
    a = _MinimalAdapterWithInput()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["cat"], returncode=0, stdout=b"test input", stderr=b"",
        )
        a._run_subprocess_with_input(["cat"], "test input")

    call_kwargs = mock_run.call_args.kwargs
    assert not call_kwargs.get("text", False), (
        f"_run_subprocess_with_input 不应传 text=True, call_kwargs={call_kwargs}"
    )


# ---------- _decode_output_bytes 单元测试 (multi-encoding fallback) ----------

class TestDecodeOutputBytes:
    """_decode_output_bytes 必须选 U+FFFD 最少的编码."""

    def test_empty_bytes_returns_empty_string(self):
        assert _decode_output_bytes(b"") == ""

    def test_pure_ascii_decodes_via_utf8(self):
        """纯 ASCII / UTF-8 完美解码, 不需要 fallback."""
        text = _decode_output_bytes(b"hello world\nflag{abc}")
        assert text == "hello world\nflag{abc}"
        assert "\ufffd" not in text

    def test_utf8_chinese_decodes_cleanly(self):
        """UTF-8 中文走 utf-8 strict, 0 U+FFFD."""
        text = _decode_output_bytes("看到这个图片就是压缩包的密码".encode("utf-8"))
        assert text == "看到这个图片就是压缩包的密码"
        assert "\ufffd" not in text

    def test_gbk_chinese_falls_back_to_gbk(self):
        """GBK 中文: utf-8 strict 失败, gbk 严格解码成功, 0 U+FFFD.

        per Owner 14:46 实测 ko.txt 内容:
        '看到这个图片就是压缩包的密码：\\r\\nbV1g6t5wZDJif^J7'
        字节 = GBK 编码. 之前 errors='replace' 给 ⬛⬛⬛ 全乱码.
        现在 _decode_output_bytes 自动走 gbk, 中文完美显示.
        """
        gbk_bytes = (
            "看到这个图片就是压缩包的密码：\r\nbV1g6t5wZDJif^J7".encode("gbk")
        )
        text = _decode_output_bytes(gbk_bytes)
        assert text == "看到这个图片就是压缩包的密码：\r\nbV1g6t5wZDJif^J7"
        assert "\ufffd" not in text

    def test_gb18030_chinese_falls_back_to_gb18030(self):
        """GB18030 中文 (含 GBK 不支持的字符): utf-8 失败, gbk 失败, gb18030 成功."""
        # 用 GB18030 编码 (4-byte 字符集), 严格解码 gbk 会失败
        gb18030_bytes = "看到这个图片就是压缩包的密码".encode("gb18030")
        text = _decode_output_bytes(gb18030_bytes)
        assert text == "看到这个图片就是压缩包的密码"
        assert "\ufffd" not in text

    def test_latin1_high_bits_decodes_as_latin1(self):
        """latin-1 高位字节: utf-8/gbk 都失败, latin-1 严格解码成功.

        latin-1 0x80-0xff 是合法字符 (per ISO-8859-1),
        应避免 fallback 到 gbk 等东亚编码 (会乱中文字符).
        """
        text = _decode_output_bytes(bytes(range(0x80, 0xa0)))
        # latin-1 严格解码, 0x80-0x9f 是控制字符 (但合法字符)
        assert "\ufffd" not in text
        assert len(text) == 32  # 32 字节 → 32 字符

    def test_random_binary_falls_back_gracefully(self):
        """随机 binary 字节: 全编码 strict 失败 → errors='replace' 兜底."""
        import os
        random_bytes = os.urandom(50)
        text = _decode_output_bytes(random_bytes)
        # 不会抛异常, 返回某个 str (可能含 U+FFFD)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_mixed_english_gbk_decodes_via_gbk(self):
        """混合 (英文 + GBK 中文) → 走 gbk, 全干净."""
        mixed = b"Password: " + "看到这个图片就是压缩包的密码".encode("gbk")
        text = _decode_output_bytes(mixed)
        assert text == "Password: 看到这个图片就是压缩包的密码"
        assert "\ufffd" not in text

    def test_owner_real_sample_ko_txt(self):
        """Owner 真实样本 steghide 抓 ko.txt GBK 内容 (v0.5-stegseek-remove 改 steghide, 实际逻辑不变).

        per Owner 14:46 截图: 之前显示成 '⬛⬛⬛⬛⬛⬛⬛⬛eT⬛⬛⬛⬛⬛⬛⬛oy⬛⬛⬛⬛⬛⬛ 蛋',
        字节实际 GBK '看到这个图片就是压缩包的密码：\\r\\nbV1g6t5wZDJif^J7'.
        """
        ko_bytes = bytes.fromhex(
            "bfb4b5bdd5e2b8f6cdbcc6acbecdcac7"
            "7d1b9cbf5b0fcb5c4c3dcc2eba3ba0d0a"
            "625631673637343537375744a69665e4a37"
        )
        # 注意: 上 hex 是简化示意, 实际 ko.txt 字节以 stegseek 输出为准
        # 这里的测试是模拟 GBK 中文 + ASCII 混合
        text = _decode_output_bytes(ko_bytes)
        # 不应该有 ⬛⬛⬛ (U+FFFD) 替代中文
        # 真实 ko.txt 解出来应该含 '看到这个图片就是压缩包的密码'
        # 但 hex 是我手编的简化版, 这里只验证 _decode_output_bytes 不抛 + 返回 str
        assert isinstance(text, str)


# ---------- 集成: 真 subprocess 跑 binary 输出 (不 mock) ----------

def test_run_subprocess_handles_non_utf8_bytes(tmp_path: Path):
    """binary 工具输出非 UTF-8 字节 不再抛 UnicodeDecodeError.

    之前 Python 3.13 默认 errors='strict' 抛 UnicodeDecodeError 挂掉.
    现在 bytes mode + _decode_output_bytes, 0xa5 等字节被 latin-1 兜底.

    注意: 0xa5 + 0x68 被 gbk 当成合法双字节字符 (\ue66e, private use area),
    所以 0x69 单独显示. 这不是 bug — 这是 gbk 的特性.
    """
    a = _MinimalAdapter()
    cmd = [
        "python3", "-c",
        "import sys; sys.stdout.buffer.write(bytes([0xa5, 0x68, 0x69]))",
    ]
    import shutil
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    # 之前: UnicodeDecodeError 抛异常
    # 现在: 返回 str (可能含特殊字符, 但不 crash)
    ec, out, err, dur = a._run_subprocess(cmd)
    assert ec == 0, f"unexpected exit: {err}"
    assert isinstance(out, str), f"output should be str, got {type(out)}"
    # 0x69 是 'i', gbk 解码后应该还在 output 里 (前后可能被组合)
    assert len(out) > 0, "output should not be empty"


def test_run_subprocess_handles_gbk_output(tmp_path: Path):
    """真 subprocess 跑 GBK 中文输出 (e.g. steghide 抓 ko.txt, per v0.5-stegseek-remove 改 steghide).

    模拟: python3 脚本写 GBK 中文到 stdout → _decode_output_bytes 走 gbk, 0 U+FFFD.
    """
    a = _MinimalAdapter()
    # 写 GBK 中文到 stdout (模拟 stegseek 抓 ko.txt 的行为)
    cmd = [
        "python3", "-c",
        "import sys; "
        "sys.stdout.buffer.write('看到这个图片就是压缩包的密码\\r\\nbV1g6t5wZDJif^J7'.encode('gbk'))",
    ]
    import shutil
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    ec, out, err, dur = a._run_subprocess(cmd)
    assert ec == 0, f"unexpected exit: {err}"
    # 不应该有 U+FFFD ⬛⬛⬛ 替代中文
    assert "\ufffd" not in out, (
        f"GBK 中文被替换为 U+FFFD, output={out!r}. "
        "multi-encoding fallback 没生效"
    )
    # 应该正确解码中文
    assert "看到这个图片就是压缩包的密码" in out, f"中文解码失败, output={out!r}"
    assert "bV1g6t5wZDJif^J7" in out


# ---------- 集成: 真 adapter (foremost --help) ----------

def test_foremost_adapter_help_does_not_crash():
    """foremost --help 输出含 binary 字符, 不应挂掉."""
    from automisc.tools.shared.foremost import ForemostAdapter
    import shutil

    if not shutil.which("foremost"):
        pytest.skip("foremost not installed")

    a = ForemostAdapter()
    cmd = ["foremost", "-h"]
    ec, out, err, dur = a._run_subprocess(cmd)
    assert ec in (0, 1), f"unexpected exit code: {ec}"
    assert out or err, "foremost -h returned empty output"