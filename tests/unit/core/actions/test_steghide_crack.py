"""测试 core/actions/steghide_crack.py (v0.5-stegseek-remove 重构)

替代原 test_stegseek.py 中 StegseekCrackAction 测试, 改测 SteghideCrackAction.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.actions.steghide_crack import SteghideCrackAction
from automisc.tools.paths import resolve_tool_binary


def _steghide_available() -> bool:
    if shutil.which("steghide"):
        return True
    if resolve_tool_binary("steghide"):
        return True
    return False


# require_steghide_binary 用作 class-level 装饰器, 不 autouse
# 原因: 部分测试 (元数据, file not found) 不依赖 binary
require_steghide_binary = pytest.mark.skipif(
    not _steghide_available(),
    reason="steghide not in PATH nor extend-tools/bin/win-x64/",
)


# ---------- 基本元数据 (不依赖 binary) ----------

class TestSteghideCrackActionMetadata:
    def test_action_name(self):
        """action name 必须 'steghide_crack' (跟 _ACTION_REGISTRY 一致)."""
        a = SteghideCrackAction()
        assert a.name == "steghide_crack"

    def test_mini_wordlist_contains_empty_string(self):
        """mini wordlist 必须含空字符串 (CVE-2021-27211)."""
        from automisc.core.actions.steghide_crack import _MINI_WORDLIST, _get_mini_wordlist_path
        assert "" in _MINI_WORDLIST
        p = _get_mini_wordlist_path()
        assert Path(p).exists()
        content = Path(p).read_text(encoding="utf-8")
        assert "" in content.split("\n")

    def test_mini_wordlist_contains_common_passwords(self):
        """mini wordlist 包含 CTF 常见密码."""
        from automisc.core.actions.steghide_crack import _MINI_WORDLIST
        for pwd in ("123456", "password", "qwerty", "admin", "ctf"):
            assert pwd in _MINI_WORDLIST, f"mini wordlist missing common password: {pwd}"


# ---------- 错密码 / 缺参数 / 缺 binary 兜底 (mock, 不依赖 binary) ----------

class TestSteghideCrackErrors:
    def test_missing_file(self, tmp_path):
        """file_path 不存在 → success=False (不依赖 binary, 文件检查先于 binary)."""
        a = SteghideCrackAction()
        r = a.run({"file_path": str(tmp_path / "no_such.jpg")})
        assert r.success is False
        assert "not found" in r.message

    def test_steghide_binary_not_found(self, tmp_path):
        """steghide binary 不存在 → graceful fail (不 crash)."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideCrackAction()
        with patch("automisc.core.actions.steghide_crack.subprocess.run", side_effect=FileNotFoundError):
            r = a.run({"file_path": str(p), "__wordlist__": ""})
        assert r.success is False
        assert "steghide" in r.message.lower()

    def test_mini_wordlist_fallback(self, tmp_path):
        """__wordlist__ 缺失 → 用 mini wordlist 兜底."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideCrackAction()

        def fake_run(cmd, *args, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "could not extract")

        with patch("automisc.core.actions.steghide_crack.subprocess.run", side_effect=fake_run):
            r = a.run({"file_path": str(p)})  # 不传 __wordlist__

        assert r.success is False
        assert r.data.get("attempted", 0) >= 50


# ---------- 命中场景 ----------

class TestSteghideCrackHit:
    def test_hit_password_breaks_loop(self, tmp_path):
        """命中密码 → break + success=True + 返回提取内容."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        fake_content = b"secret data: flag{test_pw_hit}\n"

        a = SteghideCrackAction()

        call_count = {"n": 0}
        hit_pw = "qwerty"  # mini wordlist 中存在

        def fake_run(cmd, *args, **kwargs):
            call_count["n"] += 1
            # 找到 out file
            out_idx = cmd.index("-xf") + 1
            out_path = cmd[out_idx]
            password = cmd[cmd.index("-p") + 1]
            if password == hit_pw:
                # 命中
                Path(out_path).write_bytes(fake_content)
                return subprocess.CompletedProcess(cmd, 0, "wrote extracted data", "")
            return subprocess.CompletedProcess(cmd, 1, "", "could not extract")

        with patch("automisc.core.actions.steghide_crack.subprocess.run", side_effect=fake_run):
            r = a.run({
                "file_path": str(p),
                "__max_passwords__": 100,  # mini 100 全跑
            })

        assert r.success is True
        assert r.data["passphrase"] == hit_pw
        assert "flag{test_pw_hit}" in r.data["extracted_content"]
        # 命中后应 break, 不应跑完全部 100 个
        assert call_count["n"] < 100, "命中密码后应该 break, 不应跑完整个 wordlist"

    def test_max_passwords_limit(self, tmp_path):
        """__max_passwords__ 限制尝试数."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideCrackAction()

        call_count = {"n": 0}

        def fake_run(cmd, *args, **kwargs):
            call_count["n"] += 1
            return subprocess.CompletedProcess(cmd, 1, "", "could not extract")

        with patch("automisc.core.actions.steghide_crack.subprocess.run", side_effect=fake_run):
            r = a.run({
                "file_path": str(p),
                "__max_passwords__": 5,  # 只跑 5 个
            })

        assert r.success is False
        assert call_count["n"] == 5
        assert "max_passwords=5" in r.message
