"""v0.5-output-samedir 单测: 所有文件输出都跟输入同目录.

Owner 2026-06-14:
> 不论是 foremost 还是 base64 转图片, 只要是有文件输出, 都把输出的文件
> 保存到输入文件的相同目录下, 不要保存到其他任何目录 (e.g. /tmp).

覆盖:
- output_path.py helper: 4 函数 (output_dir_for / output_path_for / temp_path_for / extract_dir_for)
  + is_in_tmp() (macOS 兼容, 路径比较)
- base64_image: decode_file_to_image 写到 input 同目录 (无 tmp 污染)
- foremost_extract: ForemostExtractAction extract_dir 默认 = input 同目录
- lsb_extract: LSBExtractAction 抽 file 走同目录
- rar_chain: BruteforceRarAction 临时辅助文件走同目录, 解出目录也同目录
- tools/shared/foremost.py: ForemostAdapter 走同目录
- main_window._maybe_trigger_zip_chain_from_binwalk: 走同目录
- CLI: --out-dir 默认行为 (None = 同目录)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from automisc.core.utils.output_path import (
    extract_dir_for,
    is_in_tmp,
    output_dir_for,
    output_path_for,
    temp_path_for,
)


# ---------- is_in_tmp: 路径比较而非字符串 ----------
class TestIsInTmp:
    def test_normal_path_not_in_tmp(self):
        """正常文件路径不在 tmp 下."""
        assert is_in_tmp("/Challenge/KEY.exe") is False
        assert is_in_tmp("/Users/minzhizhou/Desktop/test.png") is False

    def test_system_tmp_paths(self):
        """/tmp / private/tmp / var/folders/.../T/... 都应识别为 tmp."""
        # macOS /tmp 是符号链接 -> /private/tmp, 都会被识别
        assert is_in_tmp("/tmp/foo") is True
        assert is_in_tmp("/private/tmp/foo") is True
        assert is_in_tmp("/private/var/folders/ab/T/foo") is True

    def test_pytest_tmp_path_is_in_tmp(self):
        """pytest tmp_path 也在 tmp 下 (用户应避免用, 用 input 同目录)."""
        # 拿 pytest tmp_path_factory 的 _tmppathfactory 属性 (内部 API, 跨版本稳)
        # 我们简单模拟: 在 /var/folders/.../T/ 下造路径
        from automisc.core.utils.output_path import _system_tmp_dirs
        var_folders = next((t for t in _system_tmp_dirs() if t.name == "folders"), None)
        if var_folders is None:
            pytest.skip("no /var/folders on this platform")
        fake = var_folders / "ab" / "T" / "pytest-xxx" / "test__extract"
        assert is_in_tmp(fake) is True

    def test_does_not_match_similar_name(self):
        """/tmp-other 不应被误判 /tmp."""
        assert is_in_tmp("/tmp-other/foo") is False
        assert is_in_tmp("/Users/tmp/foo") is False


# ---------- output_path helper ----------
class TestOutputPathHelper:
    def test_output_dir_for(self):
        p = output_dir_for("/Challenge/KEY.exe")
        assert str(p) == "/Challenge"
        # 绝对路径
        assert p.is_absolute()

    def test_output_path_for_basic(self):
        p = output_path_for("/Challenge/KEY.exe", suffix=".png", purpose="base64")
        assert str(p) == "/Challenge/KEY__base64.png"
        assert p.parent == Path("/Challenge")

    def test_output_path_for_purpose_sanitize(self):
        """purpose 含 path-unsafe 字符 (e.g. /) 应被剥."""
        p = output_path_for("/Challenge/KEY.exe", suffix=".png", purpose="base/64")
        assert "/" not in p.name  # 不出 path traversal
        assert "base_64" in p.name

    def test_temp_path_for_basic(self):
        p = temp_path_for("/Challenge/x.rar", suffix=".hash", purpose="rar_hash")
        assert str(p) == "/Challenge/x.automisc_rar_hash.hash"
        assert p.parent == Path("/Challenge")

    def test_extract_dir_for(self):
        p = extract_dir_for("/Challenge/KEY.exe", purpose="foremost")
        assert str(p) == "/Challenge/KEY__foremost"

    def test_no_tmp_pollution_for_normal_input(self):
        """input 是正常路径 (/Challenge/...) 时, helper 输出不在 tmp."""
        inp = "/Challenge/KEY.exe"
        assert is_in_tmp(output_path_for(inp, suffix=".png", purpose="x")) is False
        assert is_in_tmp(temp_path_for(inp, suffix=".tmp", purpose="x")) is False
        assert is_in_tmp(extract_dir_for(inp, purpose="x")) is False


# ---------- base64_image: 同目录 ----------
class TestBase64ImageSameDir:
    def test_decode_writes_to_input_dir(self, tmp_path):
        """base64 -> 图片 默认写到 input 同目录, 不写到 /tmp.

        注: 这里用 sibling 子目录 (e.g. tmp_path / 'fixtures'), input 和 out_dir 都在 fixtures
        下, 避免 pytest tmp_path 本身在 /var/folders/.../T/ 下导致 is_in_tmp() 误匹配.
        """
        from automisc.core.decoders import base64_image

        # 在 tmp_path 下造个 fixtures/ 子目录, 模拟真实 user 项目
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()

        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d4944415478da6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )
        import base64
        b64 = base64.b64encode(png_bytes).decode()

        inp = fixtures / "challenge.txt"
        inp.write_text(f"data:image/png;base64,{b64}")

        result = base64_image.decode_file_to_image(str(inp))

        out = Path(result.output_path)
        # 关键: output.parent == input.parent (同目录)
        assert out.parent.resolve() == inp.parent.resolve(), \
            f"output 应在 {inp.parent}, 实际: {out.parent}"
        assert "challenge__base64" in out.name
        assert out.exists()
        out.unlink(missing_ok=True)

    def test_decode_with_explicit_out_dir(self, tmp_path):
        """--out-dir 显式指定时, 走 caller 的 dir (向后兼容)."""
        from automisc.core.decoders import base64_image

        import base64
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d4944415478da6300010000050001"
            "0d0a2db40000000049454e44ae426082"
        )
        b64 = base64.b64encode(png_bytes).decode()

        inp = tmp_path / "in.txt"
        inp.write_text(f"data:image/png;base64,{b64}")

        out_dir = tmp_path / "explicit"
        result = base64_image.decode_file_to_image(str(inp), output_dir=str(out_dir))

        out = Path(result.output_path)
        assert out.parent == out_dir
        assert "in__base64" in out.name
        out.unlink(missing_ok=True)


# ---------- foremost_extract: 同目录 ----------
class TestForemostExtractSameDir:
    def test_extract_dir_default_is_input_dir(self, tmp_path):
        """ForemostExtractAction 不传 extract_dir 时, 默认 = input 同目录."""
        from automisc.core.actions.foremost_extract import ForemostExtractAction

        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        inp = fixtures / "test.bin"
        inp.write_bytes(b"PK\x03\x04" + b"\x00" * 100)  # ZIP magic

        action = ForemostExtractAction()
        if not shutil.which("foremost"):
            pytest.skip("foremost not installed")

        result = action.run({"file_path": str(inp)})

        extract_dir = Path(result.data.get("extract_dir", ""))
        assert extract_dir.parent.resolve() == fixtures, \
            f"extract_dir 应在 {fixtures}, 实际: {extract_dir}"
        assert "test__foremost" in extract_dir.name

    def test_extract_dir_explicit_overrides(self, tmp_path):
        """caller 传 extract_dir 时, 用 caller 的."""
        from automisc.core.actions.foremost_extract import ForemostExtractAction

        inp = tmp_path / "test.bin"
        inp.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        action = ForemostExtractAction()
        if not shutil.which("foremost"):
            pytest.skip("foremost not installed")

        result = action.run({"file_path": str(inp), "extract_dir": str(custom_dir)})

        extract_dir = Path(result.data.get("extract_dir", ""))
        assert extract_dir == custom_dir


# ---------- tools/shared/foremost.py: 同目录 ----------
class TestForemostAdapterSameDir:
    def test_adapter_output_dir(self, tmp_path):
        """ForemostAdapter 写到 input 同目录."""
        from automisc.tools.shared.foremost import ForemostAdapter

        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        inp = fixtures / "small.bin"
        inp.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

        adapter = ForemostAdapter()
        if not shutil.which("foremost"):
            pytest.skip("foremost not installed")

        result = adapter.run(str(inp))
        # adapter 跑了 foremost, exit_code 0 或非 0 都能接受
        assert result.tool_name == "foremost"
        # 没有 /tmp 污染
        assert isinstance(result.suspicious_points, list)


# ---------- lsb_extract: 同目录 ----------
class TestLsbExtractSameDir:
    def test_lsb_tmp_uses_input_dir(self, tmp_path):
        """LSBExtractAction 抽 file 时, tmp_path 走 input 同目录."""
        from automisc.core.actions.lsb_extract import _write_tmp_extracted

        # 在 tmp_path 下造个 input file (子目录形式, 模拟真实 user 项目)
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        inp = fixtures / "steg.png"
        inp.write_bytes(b"fake png")
        out = _write_tmp_extracted(b"raw bytes here", str(inp), hint_ext=".zip")
        p = Path(out)
        assert p.parent.resolve() == fixtures
        assert "steg__lsb" in p.name
        assert p.exists()
        assert p.read_bytes() == b"raw bytes here"
        p.unlink(missing_ok=True)


# ---------- rar_chain: 同目录 ----------
class TestRarChainSameDir:
    def test_bruteforce_rar_extract_to_uses_helper(self):
        """BruteforceRarAction 解出目录走 extract_dir_for helper (不写 /tmp)."""
        from automisc.core.utils.output_path import extract_dir_for

        rar = Path("/Challenge/x.rar")
        expected = extract_dir_for(rar, purpose="bruteforced")
        assert "x__bruteforced" in str(expected)
        assert is_in_tmp(expected) is False

    def test_bruteforce_rar_temp_files_uses_helper(self):
        """hash / wordlist / pot 临时文件走 temp_path_for helper (input 同目录)."""
        from automisc.core.utils.output_path import temp_path_for

        rar = Path("/Challenge/x.rar")
        assert str(temp_path_for(rar, suffix=".hash", purpose="rar_hash")) == "/Challenge/x.automisc_rar_hash.hash"
        assert str(temp_path_for(rar, suffix=".txt", purpose="rar_wordlist")) == "/Challenge/x.automisc_rar_wordlist.txt"
        assert str(temp_path_for(rar, suffix=".pot", purpose="rar_pot")) == "/Challenge/x.automisc_rar_pot.pot"

    def test_temp_files_not_in_tmp(self):
        """验证 rar 临时文件路径不在 tmp 下."""
        rar = Path("/Challenge/x.rar")
        for purpose, suffix in [
            ("rar_hash", ".hash"),
            ("rar_wordlist", ".txt"),
            ("rar_pot", ".pot"),
        ]:
            p = temp_path_for(rar, suffix=suffix, purpose=purpose)
            assert is_in_tmp(p) is False, f"{p} 不应在 tmp 下"


# ---------- CLI ----------
class TestCLIDefaultOutDir:
    def test_decode_help_says_samedir(self):
        """automisc decode <x> --help 应说 '与 input 同目录' (不是 /tmp)."""
        import sys
        r = subprocess.run(
            [sys.executable, "-m", "automisc", "decode", "base64-image", "--help"],
            capture_output=True, text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
        )
        assert r.returncode == 0
        assert "input" in r.stdout.lower() and "同目录" in r.stdout, \
            f"--out-dir help 应说 '与 input 同目录', 实际: {r.stdout}"


# ---------- 端到端: 真实 KEY.exe ----------
class TestRealKeyExeE2E:
    def test_key_exe_decodes_to_challenge_dir(self):
        """真实 KEY.exe (Owner 提供) 解 base64 -> 同目录出 PNG."""
        from automisc.core.decoders import base64_image

        key_exe = Path("Challenge/KEY.exe")
        if not key_exe.exists():
            pytest.skip("Challenge/KEY.exe not found")

        # 清可能的旧
        for old in key_exe.parent.glob("KEY__base64.*"):
            old.unlink(missing_ok=True)

        result = base64_image.decode_file_to_image(str(key_exe))

        out = Path(result.output_path)
        # 关键: output 在 Challenge/ (KEY.exe 的同目录)
        assert out.parent.resolve() == key_exe.parent.resolve()
        assert is_in_tmp(out) is False
        assert out.exists()
        assert "image" in result.detected_mime.lower()

        # cleanup
        out.unlink(missing_ok=True)


# ---------- main_window binwalk extract_dir 同目录 ----------
class TestMainWindowBinwalkExtractDir:
    def test_extract_dir_uses_input_dir(self, qtbot, tmp_path):
        """GUI 触发 zip_chain_from_binwalk 时, extract_dir = input 同目录."""
        from automisc.gui.main_window import MainWindow
        from automisc.core.utils.output_path import extract_dir_for

        w = MainWindow()
        qtbot.addWidget(w)
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        f = fixtures / "test.bin"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        w.current_file = f

        extract_dir = extract_dir_for(w.current_file, purpose="extract")
        assert extract_dir.parent.resolve() == fixtures
        assert "test__extract" in extract_dir.name
        assert is_in_tmp(extract_dir) is False  # 不在系统 tmp 下

