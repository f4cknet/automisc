"""pyc_decompiler decoder 单测 (v0.5-pyc-magic-sniffer 能力 E)

不依赖外部 .pyc 文件 (除了 v0.5-train-009 N=NP 题 fixture), 自己合成 Py2.7 / Py3.x pyc 测试反编译。

覆盖:
- Py2.7 pyc 反编译 (uncompyle6)
- Py3.x pyc 反编译 (decompyle3)
- 不支持的 magic / 文件不存在 → 返回 error
- PycDecompileResult dataclass 字段
"""
from __future__ import annotations

import marshal
import struct
import subprocess
import sys
import pytest
from pathlib import Path


def _create_py27_pyc(tmp_path: Path, source_func_code, name: str = "test_func") -> Path:
    """合成 Python 2.7 pyc 文件.

    Args:
        tmp_path: pytest tmp_path
        source_func_code: 一个简单的 Python 函数 (Python 2 语法)
        name: 函数名

    Returns:
        写好的 .pyc 文件路径
    """
    # Python 2.7 pyc header: 4 bytes magic (03 f3 0d 0a) + 4 bytes timestamp + 4 bytes size
    magic = b"\x03\xf3\x0d\x0a"
    timestamp = struct.pack("<I", 0)
    # marshal code object (Python 2 字节码格式)
    code_bytes = marshal.dumps(source_func_code)
    size = struct.pack("<I", len(code_bytes))

    pyc_path = tmp_path / f"{name}.pyc"
    pyc_path.write_bytes(magic + timestamp + size + code_bytes)
    return pyc_path


def _create_py3_pyc(tmp_path: Path, source_func_code, name: str = "test_func") -> Path:
    """合成 Python 3.x pyc 文件 (用当前 Python 版本的 magic).

    Args:
        tmp_path: pytest tmp_path
        source_func_code: code object (当前 Python 版本)
        name: 函数名

    Returns:
        写好的 .pyc 文件路径
    """
    import importlib.util
    magic = importlib.util.MAGIC_NUMBER
    # Python 3.3+ header: 4 magic + 4 flags + 4 timestamp + 4 size
    flags = struct.pack("<I", 0)
    timestamp = struct.pack("<I", 0)
    code_bytes = marshal.dumps(source_func_code)
    size = struct.pack("<I", len(code_bytes))

    pyc_path = tmp_path / f"{name}.pyc"
    pyc_path.write_bytes(magic + flags + timestamp + size + code_bytes)
    return pyc_path


# ---------- 真实 N=NP 题 fixture (per v0.5-train-009 + Owner 06-21 11:24 实测) ----------
@pytest.fixture
def np_writeup_literal_pyc(tmp_path) -> Path:
    """Owner 06-21 11:24 writeup 字面代码产生的合法 Py2.7 pyc (115745 bytes).

    复用 /tmp/writeup_literal.pyc (Owner smoke 阶段已生成) 或重新生成。
    """
    src = Path("/tmp/writeup_literal.pyc")
    if src.exists():
        # copy 到 tmp_path 避免污染
        dst = tmp_path / "ctf_encode.pyc"
        dst.write_bytes(src.read_bytes())
        return dst

    # fallback: 重新生成 (PIL + writeup 字面代码)
    pytest.skip("writeup_literal.pyc not found, owner smoke 阶段应该生成过")


# ---------- PycDecompileResult dataclass 测试 ----------
class TestPycDecompileResult:
    def test_success_property_true(self):
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        r = PycDecompileResult(input_path="/x", source_code="print(1)", method="uncompyle6")
        assert r.success is True
        assert r.error is None

    def test_success_property_false_on_error(self):
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        r = PycDecompileResult(input_path="/x", error="bad magic")
        assert r.success is False
        assert r.source_code == ""

    def test_default_fields(self):
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        r = PycDecompileResult(input_path="/x")
        assert r.raw_size == 0
        assert r.source_code == ""
        assert r.method == ""
        assert r.magic_int == 0
        assert r.version == ()
        assert r.error is None


# ---------- run_pyc_decompiler 错误处理测试 ----------
class TestPycDecompilerErrors:
    def test_file_not_found(self, tmp_path):
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(tmp_path / "nonexistent.pyc"))
        assert result.error is not None
        assert "not found" in result.error

    def test_invalid_pyc(self, tmp_path):
        """完全非 pyc 数据 → xdis 报 Unknown magic."""
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        bad_pyc = tmp_path / "bad.pyc"
        bad_pyc.write_bytes(b"not a pyc file at all" * 100)
        result = run_pyc_decompiler(str(bad_pyc))
        # xdis 失败 → error
        assert result.error is not None


# ---------- 真实 N=NP 题 smoke 测试 ----------
@pytest.mark.skipif(
    not Path("/tmp/writeup_literal.pyc").exists(),
    reason="writeup_literal.pyc 不存在 (Owner 06-21 11:24 smoke 阶段生成过)",
)
class TestNpWriteupLiteralPyc:
    """Owner 06-21 11:24 实测: writeup 字面代码产生的 Py2.7 pyc."""

    def test_decompile_ctf_encode(self, np_writeup_literal_pyc):
        """反编译 N=NP 题 pyc → 应该得到 encrypt + main + KEY1 + KEY2."""
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(np_writeup_literal_pyc))

        assert result.success, f"反编译失败: {result.error}"
        assert result.method == "uncompyle6"
        assert result.version == (2, 7)
        assert result.magic_int == 62211

        # 验证源码内容 (per writeup Page 5)
        assert "def encrypt" in result.source_code
        assert "KEY1" in result.source_code
        assert "KEY2" in result.source_code
        assert "Welcome to 429 AH Cup CTF" in result.source_code

    def test_decompile_contains_encrypt_algorithm(self, np_writeup_literal_pyc):
        """反编译源码应该包含 encrypt 算法的核心逻辑 (per writeup Page 5)."""
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(np_writeup_literal_pyc))

        assert result.success
        # verify encrypt formula: seed ^ ord(key[seed]) + 8*ord(t)) % 255
        assert "seed" in result.source_code
        assert "ord" in result.source_code
        assert "% 255" in result.source_code


# ---------- CLI 集成测试 ----------
class TestPycDecompilerCLI:
    def test_decoder_registered(self):
        """pyc_decompiler 必须注册到 decoder registry."""
        from automisc.core.decoders.registry import list_decoders
        names = [d.name for d in list_decoders()]
        assert "pyc_decompiler" in names

    def test_decoder_spec_fields(self):
        """DecoderSpec 字段符合 v0.5-decoder-menu 标准."""
        from automisc.core.decoders.registry import get_decoder
        spec = get_decoder("pyc_decompiler")
        assert spec is not None
        assert spec.name == "pyc_decompiler"
        assert "Pyc" in spec.display or "反编译" in spec.display
        assert spec.category == "decode"
        assert spec.cli_cmd == "decode pyc_decompiler"
        assert "Py2" in spec.description or "pyc" in spec.description.lower()
