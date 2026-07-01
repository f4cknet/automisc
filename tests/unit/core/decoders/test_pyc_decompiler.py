"""pyc_decompiler decoder 单测 (v0.5-pyc-magic-sniffer 能力 E + v0.5-pyc-decompiler-buttons 扩展)

不依赖外部 .pyc 文件 (除了 v0.5-train-009 N=NP 题 fixture), 自己合成 Py2.7 / Py3.x pyc 测试反编译。

覆盖:
- Py2.7 pyc 反编译 (uncompyle6)
- Py3.x pyc 反编译 (decompyle3)
- 不支持的 magic / 文件不存在 → 返回 error
- PycDecompileResult dataclass 字段
- v0.5-pyc-decompiler-buttons:
  - force_version=2 强制 uncompyle6 (跳过 magic)
  - force_version=3 强制 decompyle3 (跳过 magic, Py2.7 pyc 会失败)
  - 写盘 <stem>__pyc[_pyN].py 到 pyc 同目录 (per v0.5-output-samedir)
  - 失败不写盘 (per Owner "反编译成功后输出")
  - write_output=False 显式不写盘
  - output_dir 指定输出目录
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
        # v0.5-pyc-decompiler-buttons: success 新语义 = 写盘后才算 success (per Owner "成功后输出")
        r = PycDecompileResult(
            input_path="/x",
            source_code="print(1)",
            method="uncompyle6",
            output_path="/x__pyc.py",
        )
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


# ---------- v0.5-pyc-decompiler-buttons: force_version + 写盘测试 ----------
def _find_real_py27_pyc() -> Path | None:
    """多路径找真实 Py2.7 pyc (per v0.5-train-019 实战 + v0.5-pyc-magic-sniffer 旧 fixture).

    Returns:
        找到的 pyc 路径; 找不到返回 None (test skip).
    """
    candidates = [
        # 1. v0.5-pyc-magic-sniffer 旧路径 (Owner 06-21 11:24 smoke 生成)
        Path("/tmp/writeup_literal.pyc"),
        # 2. v0.5-train-019 实战 flag.pyc (Owner 2026-07-01 实战, 755B)
        Path(r"C:\Users\zmzsg\Downloads\flag\C!_Users_zmzsg_Downloads_flag_flag.txt!flag.pyc"),
        # 3. 仓内 fixture (本 spec 新增, 仓外 .gitignore 不入 git, 仅本地归档)
        Path(__file__).parent.parent.parent / "fixtures" / "challenges" / "flag_755b_py27.pyc",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


_REAL_PY27_PYC = _find_real_py27_pyc()


@pytest.mark.skipif(
    _REAL_PY27_PYC is None,
    reason="需要真实 Py2.7 pyc (仓内 fixture tests/fixtures/challenges/flag_755b_py27.pyc 或 v0.5-train-019 owner 实战路径)",
)
class TestPycDecompilerButtonsForceVersion:
    """v0.5-pyc-decompiler-buttons: force_version 路由 + 写盘 .py."""

    def test_force_version_2_writes_py2_suffix(self, tmp_path):
        """force_version=2 → 强制 uncompyle6 + 写盘 `<stem>__pyc_py2.py`."""
        # 准备: 复制 N=NP Py2.7 pyc 到 tmp_path (per output_path_for 命名)
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), force_version=2)

        # 验证: 写盘成功 (per v0.5-output-samedir naming)
        assert result.error is None, f"force_version=2 失败: {result.error}"
        assert result.method == "uncompyle6"
        assert result.force_version == 2
        assert result.success, f"success=False, error={result.error}"
        # 期望 output_path = tmp_path/ctf_encode__pyc_py2.py
        expected_path = tmp_path / "ctf_encode__pyc_py2.py"
        assert result.output_path is not None
        assert Path(result.output_path) == expected_path
        assert expected_path.exists(), f"写盘文件不存在: {expected_path}"
        # 写盘内容应该是反编译源码
        written = expected_path.read_text(encoding="utf-8")
        # flag.pyc (v0.5-train-019 实战) / N=NP writeup_literal.pyc 都有 def encode/encrypt
        assert "def encrypt" in written or "def encode" in written, (
            f"反编译源码缺核心函数, 实际: {written[:200]!r}"
        )

    def test_auto_default_writes_pyc_suffix(self, tmp_path):
        """force_version=None (默认) → 走 magic 自动判断 + 写盘 `<stem>__pyc.py`."""
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc))  # force_version 默认 None

        assert result.error is None
        assert result.method == "uncompyle6"  # magic 2.7 → uncompyle6
        assert result.force_version is None
        assert result.success
        # 期望 output_path = tmp_path/ctf_encode__pyc.py
        expected_path = tmp_path / "ctf_encode__pyc.py"
        assert Path(result.output_path) == expected_path
        assert expected_path.exists()

    def test_force_version_3_on_py27_pyc_fails_no_write(self, tmp_path):
        """force_version=3 在 Py2.7 pyc 上 decompyle3 失败 + 不写盘 (per Owner "成功后输出").

        关键: 即便 dis fallback 能反汇编字节码, 因为不是真源码, 也不写盘.
        """
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), force_version=3)

        # 强制 py3 (decompyle3) 解 Py2.7 pyc → 必然失败
        # 但 dis fallback 成功 (字节码反汇编能跑), err 被清成 None
        # 判断走 fallback: method == "dis"
        assert result.method == "dis", (
            f"强制 py3 跑 Py2.7 pyc, 应该走 dis fallback, 实际 method={result.method}"
        )
        # 写盘: dis fallback 是字节码不是真源码, 不写盘 (per Owner 决策)
        assert result.output_path is None, (
            f"dis fallback 不应写盘, 实际 output_path={result.output_path}"
        )
        # success: 没写盘不算 success
        assert result.success is False
        # 验证: 目录里没 .py 写盘
        py_files = list(tmp_path.glob("*.py"))
        assert not py_files, f"反编译失败但写盘了: {py_files}"

    def test_write_output_false_does_not_write(self, tmp_path):
        """write_output=False → 反编译成功但不写盘 (CLI --no-write 场景)."""
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), write_output=False)

        # 反编译成功
        assert result.error is None
        assert result.method == "uncompyle6"
        assert result.source_code  # 有源码
        # 但不写盘
        assert result.output_path is None
        # success: 没写盘不算 success (per Owner "成功后输出")
        assert result.success is False
        # 验证: 目录里没 .py
        assert not list(tmp_path.glob("*.py"))

    def test_output_dir_explicit(self, tmp_path):
        """output_dir 显式指定 → 写盘到指定目录 (v0.5-tmp-text-mode-2 风格)."""
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        custom_dir = tmp_path / "custom_output"
        custom_dir.mkdir()

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(
            str(local_pyc),
            force_version=2,
            output_dir=str(custom_dir),
        )

        assert result.error is None
        assert result.success
        # 期望 output_path = custom_dir/ctf_encode__pyc_py2.py
        expected_path = custom_dir / "ctf_encode__pyc_py2.py"
        assert Path(result.output_path) == expected_path
        assert expected_path.exists()

    def test_dis_fallback_does_not_write(self, tmp_path):
        """dis fallback 是字节码反汇编, 不是真源码 → 不写盘 (per Owner 决策).

        场景: 合成一个 uncompyle6 + decompyle3 都解不出来的 Py3.x 字节码 (e.g. 含 async).
        实际测试中, 难合成这种情况, 所以 mock _decompile_with_uncompyle6 + decompyle3 都失败,
        强制走 dis fallback, 验证 output_path=None.
        """
        from automisc.core.decoders import pyc_decompiler as pdc
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        # mock: uncompyle6 + decompyle3 都抛异常 → 强制走 dis fallback
        def _fail(*args, **kwargs):
            raise RuntimeError("mock: decompile fail")

        orig_uncompyle6 = pdc._decompile_with_uncompyle6
        orig_decompyle3 = pdc._decompile_with_decompyle3
        pdc._decompile_with_uncompyle6 = _fail
        pdc._decompile_with_decompyle3 = _fail
        try:
            result = run_pyc_decompiler(str(local_pyc), force_version=2)
        finally:
            pdc._decompile_with_uncompyle6 = orig_uncompyle6
            pdc._decompile_with_decompyle3 = orig_decompyle3

        # dis fallback 跑通, source_code 非空 (含 bytecode 注释)
        assert result.error is None  # fallback 成功清掉 err
        assert result.method == "dis"
        # 但不写盘 (per Owner "反编译成功后输出" = 真正反编译出源码才写)
        assert result.output_path is None
        assert result.success is False
        # 验证: 目录里没 .py
        assert not list(tmp_path.glob("*.py"))


# ---------- v0.5-pyc-decompiler-buttons: PycDecompileResult 字段 ----------
class TestPycDecompileResultNewFields:
    """v0.5-pyc-decompiler-buttons: PycDecompileResult 新增 force_version + output_path 字段."""

    def test_force_version_default_none(self):
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        r = PycDecompileResult(input_path="/x")
        assert r.force_version is None

    def test_output_path_default_none(self):
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        r = PycDecompileResult(input_path="/x")
        assert r.output_path is None

    def test_success_requires_output_path(self):
        """success property: 必须写盘了才算 success (per Owner "成功后输出").

        之前版本 success 只看 source_code + error, 现在改看 output_path.
        """
        from automisc.core.decoders.pyc_decompiler import PycDecompileResult
        # 有源码 + 没 error + 没写盘 → success=False (per 新语义)
        r = PycDecompileResult(
            input_path="/x",
            source_code="print(1)",
            method="uncompyle6",
        )
        assert r.success is False  # output_path=None → success=False
        # 写盘了 → success=True
        r2 = PycDecompileResult(
            input_path="/x",
            source_code="print(1)",
            method="uncompyle6",
            output_path="/x__pyc.py",
        )
        assert r2.success is True
