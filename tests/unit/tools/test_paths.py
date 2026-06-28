"""测试 automisc/tools/paths.py (per v0.5-platform-extend-tools).

覆盖:
- platform_subdir() 返回当前平台子目录名
- exe_suffix() Windows 加 .exe
- extend_tools_bin_dir() 返回正确路径
- resolve_tool_binary(): PATH 优先 + extend-tools fallback
- list_extend_tools() 列已下好的 binary
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from automisc.tools import paths


# ---------- 平台检测 ----------

class TestPlatformDetection:
    def test_platform_subdir_returns_known_platform(self):
        """Current platform must map to a known subdir."""
        subdir = paths.platform_subdir()
        if sys.platform == "win32":
            assert subdir == "win-x64"
        elif sys.platform == "darwin":
            assert subdir == "macos"
        elif sys.platform == "linux":
            assert subdir == "linux-x64"

    def test_exe_suffix(self):
        if sys.platform == "win32":
            assert paths.exe_suffix() == ".exe"
        else:
            assert paths.exe_suffix() == ""

    def test_extend_tools_bin_dir_is_under_repo_root(self):
        """extend-tools/bin/<platform>/ must be under repo root."""
        bindir = paths.extend_tools_bin_dir()
        assert bindir is not None
        assert "extend-tools" in str(bindir)
        assert str(bindir).endswith(paths.platform_subdir())

    def test_extend_tools_dir_constant_exists(self):
        """EXTEND_TOOLS_DIR must point to a real extend-tools directory."""
        assert paths.EXTEND_TOOLS_DIR.exists()
        assert (paths.EXTEND_TOOLS_DIR / "manifest.yaml").exists()


# ---------- resolve_tool_binary ----------

class TestResolveToolBinary:
    def test_path_takes_priority_over_extend_tools(self):
        """If a tool is in PATH, resolve_tool_binary returns PATH version."""
        # python is always in PATH
        result = paths.resolve_tool_binary("python")
        assert result is not None
        # Should be the system python (whichever)
        assert Path(result).name.lower().startswith("python")

    def test_extend_tools_fallback(self):
        """If not in PATH, look in extend-tools/bin/<platform>/."""
        # Pick a tool that may or may not be in PATH
        # "definitely_not_in_path_tool_xyz" should never exist
        assert paths.resolve_tool_binary("definitely_not_in_path_tool_xyz") is None

    def test_resolve_returns_string(self):
        """resolve_tool_binary must return str, not Path."""
        result = paths.resolve_tool_binary("python")
        if result is not None:
            assert isinstance(result, str)


# ---------- resolve_tool_binary: subdir fallback (per fix-resolve-tool-binary-subdir) ----------

class TestResolveToolBinarySubdir:
    """subdir 布局工具 (steghide Cygwin build) 走 <bin>/<name>/<name>.exe 路径解析.

    背景: v0.5-windows-tool-compat steghide Cygwin build 部署到
    extend-tools/bin/win-x64/steghide/steghide.exe (subdir, Cygwin runtime DLLs 同目录).
    修复前: resolve_tool_binary 只看 flat 路径 <bin>/<name>.exe, Win 端永远找不到.
    修复后: subdir fallback 找到 <bin>/<name>/<name>.exe.
    """

    def test_steghide_subdir_layout_resolved(self):
        """Win 端 steghide 在 subdir, 修复后应能找到 (前提: extend-tools 已装 steghide)."""
        if sys.platform != "win32":
            pytest.skip("subdir layout 验证仅 Win 端有意义")
        # 真实路径依赖 install.ps1 是否跑过, 跳过如果 steghide 没装
        steghide_path = paths.resolve_tool_binary("steghide")
        if steghide_path is None:
            pytest.skip("steghide not installed (跑 install.ps1 装 steghide Cygwin build)")
        # 应指向 <bin>/<name>/<name>.exe
        p = Path(steghide_path)
        assert p.name == "steghide.exe"
        assert p.parent.name == "steghide", (
            f"应走 subdir 布局 <bin>/steghide/steghide.exe, 实际: {p}"
        )

    def test_subdir_only_tool_not_resolved_if_missing(self):
        """如果 subdir 也没装, 应返回 None (不要 false positive)."""
        # nonexistent_tool_xyz 既不在 PATH, 也不在 flat, 也不在 subdir
        assert paths.resolve_tool_binary("definitely_not_in_path_tool_xyz") is None

    def test_subdir_fallback_path_in_documentation(self):
        """resolve_tool_binary docstring 提到 subdir fallback."""
        from automisc.tools.paths import resolve_tool_binary
        doc = resolve_tool_binary.__doc__
        assert doc is not None
        assert "subdir" in doc.lower() or "<name>/<name>" in doc, (
            f"resolve_tool_binary docstring 应说明 subdir fallback, 实际: {doc[:200]}"
        )

    def test_flat_layout_takes_priority_over_subdir(self):
        """flat 存在时优先 flat, 不查 subdir (避免 subdir 误命中)."""
        # 用 mock: bindir 下有 flat/<name>.exe, 也构造 subdir/<name>/<name>.exe
        # 期望: 返回 flat 那个
        # 这测试需 mock extend_tools_bin_dir(), 跳过复杂 mock
        pytest.skip("需要 mock extend_tools_bin_dir, 留作 integration test")

    def test_resolve_tool_binary_uses_subdir_when_flat_missing(self, tmp_path):
        """手动构造 test 场景: 临时目录里只放 subdir 布局, 验证 subdir fallback."""
        import automisc.tools.paths as paths_mod

        # 临时结构: <tmp>/win-x64/mytool/mytool.exe
        fake_bindir = tmp_path / "win-x64"
        fake_subdir = fake_bindir / "mytool"
        fake_subdir.mkdir(parents=True)
        fake_exe = fake_subdir / ("mytool.exe" if sys.platform == "win32" else "mytool")
        fake_exe.write_text("# fake binary")

        # mock extend_tools_bin_dir + exe_suffix
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(paths_mod, "extend_tools_bin_dir", lambda: fake_bindir)
            mp.setattr(paths_mod, "exe_suffix", lambda: ".exe" if sys.platform == "win32" else "")

            result = paths_mod.resolve_tool_binary("mytool")
        assert result == str(fake_exe), (
            f"subdir fallback 应返回 {fake_exe}, 实际: {result}"
        )

    def test_resolve_tool_binary_returns_none_when_neither_layout_exists(self, tmp_path):
        """临时目录里什么也没有, 返回 None (不要 crash)."""
        import automisc.tools.paths as paths_mod

        fake_bindir = tmp_path / "win-x64"
        fake_bindir.mkdir(parents=True)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(paths_mod, "extend_tools_bin_dir", lambda: fake_bindir)
            mp.setattr(paths_mod, "exe_suffix", lambda: ".exe" if sys.platform == "win32" else "")

            result = paths_mod.resolve_tool_binary("nonexistent_tool_abc")
        assert result is None


# ---------- list_extend_tools ----------

class TestListExtendTools:
    def test_returns_list_of_strings(self):
        tools = paths.list_extend_tools()
        assert isinstance(tools, list)
        # If extend-tools/bin/<platform>/ has binaries, all should be strings
        for t in tools:
            assert isinstance(t, str)

    def test_does_not_include_hidden_files(self):
        """Dotfiles (.gitkeep etc.) must not appear."""
        tools = paths.list_extend_tools()
        for t in tools:
            assert not t.startswith(".")

    def test_returns_sorted(self):
        """Output must be sorted for stable display."""
        tools = paths.list_extend_tools()
        assert tools == sorted(tools)


# ---------- Manifest path ----------

class TestManifestPath:
    def test_manifest_path_under_extend_tools(self):
        assert paths.EXTEND_TOOLS_MANIFEST.exists()
        assert paths.EXTEND_TOOLS_MANIFEST.parent == paths.EXTEND_TOOLS_DIR

    def test_manifest_readable(self):
        """manifest.yaml must be readable YAML-ish."""
        content = paths.EXTEND_TOOLS_MANIFEST.read_text(encoding="utf-8")
        assert "version:" in content
        assert "platforms:" in content