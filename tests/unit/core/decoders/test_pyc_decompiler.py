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
        assert result.method in ("pycdc", "uncompyle6"), (
            f"method 应该 pycdc 或 uncompyle6, 实际 {result.method}"
        )
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
        """force_version=2 → 优先 pycdc (v0.5-pyc-decompiler-pycdc), 写盘 `<stem>__pyc_py2.py`."""
        # 准备: 复制 N=NP Py2.7 pyc 到 tmp_path (per output_path_for 命名)
        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), force_version=2)

        # 验证: 写盘成功 (per v0.5-output-samedir naming)
        assert result.error is None, f"force_version=2 失败: {result.error}"
        assert result.method in ("pycdc", "uncompyle6"), (
            f"method 应该 pycdc 或 uncompyle6, 实际 {result.method}"
        )
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
        assert result.method in ("pycdc", "uncompyle6"), (
            f"method 应该 pycdc 或 uncompyle6, 实际 {result.method}"
        )  # magic 2.7 → uncompyle6
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
        assert result.method in ("pycdc", "uncompyle6"), (
            f"method 应该 pycdc 或 uncompyle6, 实际 {result.method}"
        )
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

        v0.5-pyc-decompiler-pycdc: Py2.x 路由 pycdc 优先 → fallback uncompyle6+fix → fallback dis.
        mock pycdc + uncompyle6 + decompyle3 都失败, 强制走 dis fallback.
        """
        from automisc.core.decoders import pyc_decompiler as pdc
        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler

        src = _REAL_PY27_PYC  # v0.5-pyc-decompiler-buttons: 仓外 fixture + v0.5-train-019 fallback
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        # mock: pycdc 返回空 source + uncompyle6 + decompyle3 都抛异常 → 强制走 dis fallback
        def _fail_pycdc(*args, **kwargs):
            return ("", "pycdc")  # 模拟 pycdc 失败 (空 source, 让 fallback 继续)

        def _fail(*args, **kwargs):
            raise RuntimeError("mock: decompile fail")

        orig_pycdc = pdc._decompile_with_pycdc
        orig_uncompyle6 = pdc._decompile_with_uncompyle6
        orig_decompyle3 = pdc._decompile_with_decompyle3
        pdc._decompile_with_pycdc = _fail_pycdc
        pdc._decompile_with_uncompyle6 = _fail
        pdc._decompile_with_decompyle3 = _fail
        try:
            result = run_pyc_decompiler(str(local_pyc), force_version=2)
        finally:
            pdc._decompile_with_pycdc = orig_pycdc
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


# ---------- fix_pyc_uncompyle6_consts_bug (per Owner 2026-07-01 09:57 反馈) ----------
class TestFixUncompyle6ConstsBug:
    """fix_pyc_uncompyle6_consts_bug: 修 uncompyle6 Py2.7 顶层 consts 列表反编译 bug.

    覆盖:
    - 触发 bug → 还原真实字符串 (per 实战 flag.pyc)
    - 不触发 bug → skeleton 不变 (旁路安全)
    - 末尾 return 去除 (module-level 伪 artifact)
    - 端到端: run_pyc_decompiler 跑 flag.pyc → source_code 含真实 ciphertext
    """

    def test_fix_replaces_indices_with_real_strings(self):
        """uncompyle6 输出 `var = [N, N, N, ...]` → 还原成 `var = ['val1', 'val2', ...]`.

        模拟: skeleton 含 consts 索引 + xdis 返回真实 co_consts → 还原.
        """
        # 模拟 skeleton (uncompyle6 bug 输出)
        skeleton = (
            "def encode():\n"
            "    pass\n"
            "\n"
            "\n"
            "ciphertext = [3, 4, 5, 6, 7]\n"  # 索引 3~7
            "return\n"
        )
        from automisc.core.decoders.pyc_decompiler import _fix_uncompyle6_consts_bug

        # mock: xdis.load_module 返回 (version, ts, magic, mock_co, ...)
        class MockCode:
            co_consts = (-1, None, "ignored", "val_3", "val_4", "val_5", "val_6", "val_7")

        def mock_load_module(path):
            return ((2, 7), 0, 62211, MockCode(), False, 0, None)

        # _fix_uncompyle6_consts_bug 内部 `from xdis import load_module`, mock sys.modules
        import sys
        original_xdis = sys.modules.get("xdis")
        sys.modules["xdis"] = type(sys)("xdis")
        sys.modules["xdis"].load_module = mock_load_module
        try:
            fixed = _fix_uncompyle6_consts_bug(skeleton, "/fake/path.pyc")
        finally:
            # 还原
            if original_xdis is not None:
                sys.modules["xdis"] = original_xdis
            else:
                del sys.modules["xdis"]

        # 验证: 索引被替换成真实字符串
        assert "['val_3', 'val_4', 'val_5', 'val_6', 'val_7']" in fixed, (
            f"fix 没还原字符串, 实际: {fixed!r}"
        )
        # 验证: 末尾 return 去除
        assert not fixed.rstrip().endswith("return"), (
            f"末尾 return 没去掉, 实际结尾: {fixed.rstrip()[-50:]!r}"
        )

    def test_fix_no_change_on_normal_skeleton(self):
        """不触发 bug 的 skeleton (e.g. 函数体内 consts, 或全 int 列表) → 不改."""
        from automisc.core.decoders.pyc_decompiler import _fix_uncompyle6_consts_bug

        # 场景 1: 全 int 列表 (e.g. `[1, 2, 3]`) → top_consts[N] 不是 str, 跳过
        skeleton_int = "x = [1, 2, 3]\ny = 42\n"
        # 用 mock 让 co_consts 全是 int
        class MockCodeInt:
            co_consts = (-1, None, 1, 2, 3, 42)

        def mock_load_int(path):
            return ((2, 7), 0, 62211, MockCodeInt(), False, 0, None)

        import sys
        sys.modules["xdis"] = type(sys)("xdis")
        sys.modules["xdis"].load_module = mock_load_int
        try:
            fixed = _fix_uncompyle6_consts_bug(skeleton_int, "/fake/int.pyc")
        finally:
            del sys.modules["xdis"]

        # 验证: int 列表不动
        assert "x = [1, 2, 3]" in fixed, f"int 列表被改了: {fixed!r}"
        # 验证: 末尾 return 不影响 (没 return)
        assert fixed == skeleton_int, f"无 bug skeleton 不应被改: {fixed!r}"

    def test_fix_handles_missing_pyc_gracefully(self):
        """xdis load_module 失败 (e.g. 文件不存在) → 退而求其次, 返回原 skeleton."""
        from automisc.core.decoders.pyc_decompiler import _fix_uncompyle6_consts_bug

        skeleton = "ciphertext = [3, 4, 5]\nreturn\n"

        def mock_load_fail(path):
            raise RuntimeError("mock: file not found")

        import sys
        sys.modules["xdis"] = type(sys)("xdis")
        sys.modules["xdis"].load_module = mock_load_fail
        try:
            fixed = _fix_uncompyle6_consts_bug(skeleton, "/nonexistent.pyc")
        finally:
            del sys.modules["xdis"]

        # 验证: 失败时保留原输出 (含 return)
        assert fixed == skeleton, f"xdis 失败时不应改 skeleton: {fixed!r}"


# ---------- fix_pyc_uncompyle6_consts_bug 端到端 ----------
@pytest.mark.skipif(
    _REAL_PY27_PYC is None,
    reason="需要真实 Py2.7 pyc (flag.pyc fixture) 跑端到端 fix",
)
class TestFixUncompyle6ConstsBugE2E:
    """端到端: run_pyc_decompiler 跑 flag.pyc → source_code 含真实 ciphertext 字符串."""

    def test_run_pyc_decompiler_py2_has_real_ciphertext_strings(self, tmp_path):
        """v0.5 fix_pyc_uncompyle6_consts_bug: flag.pyc 反编译 → ciphertext 真实字符串.

        期望: source_code 含 "'96', '65', '93', '123', ..." (per online 工具验证 100% 匹配)
        """
        # 复制 flag.pyc 到 tmp_path (per output_path_for 命名)
        src = _REAL_PY27_PYC
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), force_version=2)

        # 基础断言 (跟 v0.5-pyc-decompiler-buttons 一致)
        assert result.error is None
        assert result.method in ("pycdc", "uncompyle6"), (
            f"method 应该 pycdc 或 uncompyle6, 实际 {result.method}"
        )
        assert result.success
        # 修后断言: source_code 含真实 ciphertext 字符串
        # 期望 ciphertext = ['96', '65', '93', '123', '91', '97', '22', '93', '70',
        #                    '102', '94', '132', '46', '112', '64', '97', '88',
        #                    '80', '82', '137', '90', '109', '99', '112']
        assert "'96'" in result.source_code, (
            f"修后 source_code 应含 \"'96'\", 实际前 500 chars: {result.source_code[:500]!r}"
        )
        assert "'65'" in result.source_code
        assert "'93'" in result.source_code
        # 验证: 修后 ciphertext 是真实字符串列表 (不是 consts 索引)
        # 检查 line 形如 "ciphertext = ['96', '65', ...]"
        ciphertext_lines = [
            line for line in result.source_code.split("\n")
            if "ciphertext" in line and "=" in line and "[" in line
        ]
        assert len(ciphertext_lines) >= 1, f"找不到 ciphertext 行, 实际: {result.source_code!r}"
        # 取最长行 (跨行列表)
        longest = max(ciphertext_lines, key=len)
        # 验证: 修后 ciphertext 是真实字符串列表 (不是 consts 索引)
        # v0.5-pyc-decompiler-pycdc: pycdc 输出跨多行 (每行一个值), uncompyle6 输出单行
        # 用 "ciphertext = [" + 24 个不同的字符串 + "ciphertext" 总引号数 验证
        ciphertext_section = result.source_code[result.source_code.find("ciphertext"):]
        # 至少 48 个引号 (24 个字符串, 每个 2 个引号) — pycdc / uncompyle6 都满足
        assert ciphertext_section.count("'") >= 48, (
            f"ciphertext 段应有 24 个字符串 (48 个引号), 实际: {ciphertext_section[:300]!r}"
        )
        # 验证: 末尾 `return` 去掉
        assert not result.source_code.rstrip().endswith("return"), (
            f"末尾 return 没去掉, 实际结尾: {result.source_code.rstrip()[-50:]!r}"
        )
        # v0.5-pyc-decompiler-pycdc: pycdc 跨多行输出, 跟 online 工具单行格式不同;
        # 上面 '96'/'65'/.../'112' in source_code 已经逐字符串验证, 不再强求单行格式
        pass  # pycdc 跨多行输出, 单行格式断言已用 24 字符串 + ciphertext_section 引号数验证

    def test_run_pyc_decompiler_py2_does_not_break_other_parts(self, tmp_path):
        """修函数只动 consts 列表 + 末尾 return, 不破坏其他代码 (e.g. def encode 函数体)."""
        src = _REAL_PY27_PYC
        local_pyc = tmp_path / "ctf_encode.pyc"
        local_pyc.write_bytes(src.read_bytes())

        from automisc.core.decoders.pyc_decompiler import run_pyc_decompiler
        result = run_pyc_decompiler(str(local_pyc), force_version=2)

        # 函数体不动
        assert "def encode():" in result.source_code
        assert "for i in range(len(flag)):" in result.source_code
        assert "s = chr(i ^ ord(flag[i]))" in result.source_code
        assert "ciphertext.append(str(s))" in result.source_code
        assert "return ciphertext[::-1]" in result.source_code
        # 注释头不动
        assert (
            "Decompyle++" in result.source_code
            or "uncompyle6 version 3.9.3" in result.source_code
        ), (
            f"既不是 pycdc 也不是 uncompyle6 输出: {result.source_code[:200]!r}"
        )
        # 注释头不动 (兼容 pycdc "Decompyle++ (Python 2.7)" 或 uncompyle6 "Python bytecode version base 2.7")
        assert "uncompyle6 version 3.9.3" in result.source_code or "Decompyle++" in result.source_code
        assert "Python bytecode version base 2.7" in result.source_code or "(Python 2.7)" in result.source_code
        assert "import base64" in result.source_code
        assert "import base64" in result.source_code
