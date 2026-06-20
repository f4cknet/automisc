"""测试 core/actions/stegseek.py (v0.5-steghide-GUI)

覆盖:
- StegseekCrackAction: bruteforce with wordlist
- SteghideExtractAction: extract with user-provided password

GUI 工具栏 Steghide 子菜单的 3 模式入口:
1. 自动检测 (空密码) — 走 StegseekCrackAction + 空 wordlist
2. 暴力破解 (带 wordlist) — QFileDialog 收 wordlist → StegseekCrackAction
3. 指定密码提取 — QInputDialog 收密码 → SteghideExtractAction
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.actions.stegseek import (
    StegseekCrackAction,
    SteghideExtractAction,
)


# ---------- StegseekCrackAction ----------

class TestStegseekCrackAction:
    """stegseek bruteforce mode — GUI 工具栏带 wordlist."""

    def test_action_is_named_correctly(self):
        """action name 必须 'stegseek_crack' (跟 _ACTION_REGISTRY 一致)."""
        a = StegseekCrackAction()
        assert a.name == "stegseek_crack"

    def test_missing_file_path_fails(self, tmp_path: Path):
        """file_path 缺失/不存在 → success=False."""
        a = StegseekCrackAction()
        ctx = {"file_path": str(tmp_path / "nonexistent.jpg"), "__wordlist__": "/tmp/x"}
        result = a.run(ctx)
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_missing_wordlist_fails(self, tmp_path: Path):
        """wordlist 缺失 → success=False (GUI dialog 必须传)."""
        a = StegseekCrackAction()
        test_file = tmp_path / "x.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0fake")
        ctx = {"file_path": str(test_file)}  # 无 __wordlist__
        result = a.run(ctx)
        assert result.success is False
        assert "wordlist" in result.message.lower()

    @pytest.mark.skipif(
        shutil.which("stegseek") is None,
        reason="stegseek not installed (v0.5 推荐安装)",
    )
    def test_cracked_password_returns_success(self, tmp_path: Path):
        """stegseek 抓到密码 → success=True, data 含 passphrase + extracted_content."""
        # 准备 stego 文件 + 空 wordlist (抓空密码 — 123456cry.jpg owner 实战)
        stego = Path("/Users/minzhizhou/Downloads/123456cry__foremost/zip/00000038_unzipped/asd/good-已合并.jpg")
        if not stego.exists():
            pytest.skip(f"owner 实战样本不存在: {stego}")

        # 空 wordlist
        empty_wl = tmp_path / "empty.txt"
        empty_wl.write_text("")

        a = StegseekCrackAction()
        result = a.run({
            "file_path": str(stego),
            "__wordlist__": str(empty_wl),
        })

        # 123456cry.jpg 的 good-已合并.jpg 用空密码 (stegseek 实测)
        assert result.success is True, f"应该成功: {result.message}"
        assert result.data.get("passphrase") == ""
        assert "ko.txt" in result.data.get("original_filename", "")
        # 提取内容含 qwe.zip 密码 (owner 实测结果)
        assert "bV1g6t5wZDJif^J7" in result.data.get("extracted_content", "")

    @pytest.mark.skipif(
        shutil.which("stegseek") is None,
        reason="stegseek not installed",
    )
    def test_no_match_returns_failure(self, tmp_path: Path):
        """stegseek 没找到密码 → success=False, message 说明."""
        # 干净 BMP (无嵌入数据)
        from PIL import Image
        clean_bmp = tmp_path / "clean.bmp"
        Image.new("RGB", (32, 32), "blue").save(clean_bmp, "BMP")

        wl = tmp_path / "wl.txt"
        wl.write_text("password1\npassword2\npassword3\n")

        a = StegseekCrackAction()
        result = a.run({
            "file_path": str(clean_bmp),
            "__wordlist__": str(wl),
        })

        # 干净文件 → stegseek 跑完未找到密码 → success=False (不写 SP 但 action return False)
        assert result.success is False
        assert "stegseek" in result.message.lower()
        assert "未找到" in result.message or "not found" in result.message.lower()


# ---------- SteghideExtractAction ----------

class TestSteghideExtractAction:
    """steghide extract mode — GUI 工具栏用户输入密码."""

    def test_action_is_named_correctly(self):
        a = SteghideExtractAction()
        assert a.name == "steghide_extract"

    def test_missing_file_path_fails(self, tmp_path: Path):
        a = SteghideExtractAction()
        result = a.run({"__password__": "x"})
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_missing_password_fails(self, tmp_path: Path):
        a = SteghideExtractAction()
        test_file = tmp_path / "x.jpg"
        test_file.write_bytes(b"\xff\xd8\xff\xe0fake")
        result = a.run({"file_path": str(test_file)})  # 无 __password__
        assert result.success is False
        assert "password" in result.message.lower()

    @pytest.mark.skipif(
        not (shutil.which("steghide") or shutil.which("stegseek")),
        reason="steghide/stegseek 都不可用",
    )
    def test_correct_password_extracts_content(self, tmp_path: Path):
        """正确密码 → success=True, data 含 extracted_content."""
        stego = Path("/Users/minzhizhou/Downloads/123456cry__foremost/zip/00000038_unzipped/asd/good-已合并.jpg")
        if not stego.exists():
            pytest.skip(f"owner 实战样本不存在: {stego}")

        a = SteghideExtractAction()
        result = a.run({
            "file_path": str(stego),
            "__password__": "",  # 正确密码是空
        })

        # 成功提取 (stegseek/steghide 都应该接受空密码)
        assert result.success is True, f"应该成功: {result.message}"
        assert result.data.get("extracted_content") is not None
        assert "bV1g6t5wZDJif^J7" in result.data.get("extracted_content", "")


# ---------- 集成: ChainRunner 注册 ----------

def test_stegseek_actions_registered_in_chain_runner():
    """StegseekCrackAction + SteghideExtractAction 必须在 _ACTION_REGISTRY.

    per v0.5-steghide-GUI: Steghide 子菜单的 3 模式入口都走 ChainRunner.
    """
    from automisc.gui.chain_runner import _ensure_action_registry, _ACTION_REGISTRY
    _ensure_action_registry()
    assert "stegseek_crack" in _ACTION_REGISTRY, (
        f"stegseek_crack 必须注册, 当前: {list(_ACTION_REGISTRY.keys())}"
    )
    assert "steghide_extract" in _ACTION_REGISTRY
