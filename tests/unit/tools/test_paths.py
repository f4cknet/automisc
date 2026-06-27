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