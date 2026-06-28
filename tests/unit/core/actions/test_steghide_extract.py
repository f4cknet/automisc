"""测试 core/actions/steghide_extract.py (v0.5-stegseek-remove 重构)

替代原 test_stegseek.py 中 SteghideExtractAction 测试, 改测新文件.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.actions.steghide_extract import SteghideExtractAction
from automisc.tools.paths import resolve_tool_binary


def _steghide_available() -> bool:
    if shutil.which("steghide"):
        return True
    if resolve_tool_binary("steghide"):
        return True
    return False


# require_steghide_binary 作为 class-level 装饰器 (不 autouse, 部分测试不依赖 binary)
require_steghide_binary = pytest.mark.skipif(
    not _steghide_available(),
    reason="steghide not in PATH nor extend-tools/bin/win-x64/",
)


# ---------- 基本元数据 (不依赖 binary) ----------

class TestSteghideExtractActionMetadata:
    def test_action_name(self):
        """action name 保持 'steghide_extract' (跟原 SteghideExtractAction 一致)."""
        a = SteghideExtractAction()
        assert a.name == "steghide_extract"


# ---------- 错参数 / 缺 binary 兜底 ----------

class TestSteghideExtractErrors:
    def test_missing_file(self, tmp_path):
        a = SteghideExtractAction()
        r = a.run({"file_path": str(tmp_path / "no_such.jpg"), "__password__": "test"})
        assert r.success is False
        assert "not found" in r.message

    def test_password_not_provided(self, tmp_path):
        """__password__ is None (用户没输入) → fail."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideExtractAction()
        r = a.run({"file_path": str(p)})  # 不传 __password__
        assert r.success is False
        assert "not provided" in r.message

    def test_steghide_binary_not_found(self, tmp_path):
        """steghide binary 不存在 → graceful fail."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideExtractAction()
        with patch("automisc.core.actions.steghide_extract.subprocess.run", side_effect=FileNotFoundError):
            r = a.run({"file_path": str(p), "__password__": "test"})
        assert r.success is False
        assert "steghide" in r.message.lower()


# ---------- 命中 / 错密码 ----------

class TestSteghideExtractHit:
    def test_correct_password_extracts(self, tmp_path):
        """正确密码 → success=True + 写 extracted.bin 到 samedir."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        fake_content = b"hidden data: flag{steghide_correct_pw}\n"
        password = "secret123"

        a = SteghideExtractAction()

        def fake_run(cmd, *args, **kwargs):
            # 找 out file
            out_idx = cmd.index("-xf") + 1
            out_path = cmd[out_idx]
            Path(out_path).write_bytes(fake_content)
            return __import__("subprocess").CompletedProcess(
                cmd, 0, "wrote extracted data", ""
            )

        with patch("automisc.core.actions.steghide_extract.subprocess.run", side_effect=fake_run):
            r = a.run({"file_path": str(p), "__password__": password})

        assert r.success is True
        assert "flag{steghide_correct_pw}" in r.data["extracted_content"]
        # 验证输出写到 samedir (per v0.5-output-samedir)
        out_file = Path(r.data["extracted_file"])
        assert out_file.exists()
        assert out_file.parent.parent == p.parent  # <stem>__steghide_extract/ 下

    def test_empty_password_legitimate(self, tmp_path):
        """空密码合法 (CVE-2021-27211) - 跟 None 区分."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        fake_content = b"empty_pw hit\n"
        a = SteghideExtractAction()

        def fake_run(cmd, *args, **kwargs):
            out_idx = cmd.index("-xf") + 1
            out_path = cmd[out_idx]
            # 验证 cmd 传的 password 是 ""
            assert cmd[cmd.index("-p") + 1] == "", "应传空密码"
            Path(out_path).write_bytes(fake_content)
            return __import__("subprocess").CompletedProcess(
                cmd, 0, "wrote extracted data", ""
            )

        with patch("automisc.core.actions.steghide_extract.subprocess.run", side_effect=fake_run):
            r = a.run({"file_path": str(p), "__password__": ""})  # 空字符串

        assert r.success is True

    def test_wrong_password(self, tmp_path):
        """错密码 → success=False + 错误信息."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideExtractAction()

        def fake_run(cmd, *args, **kwargs):
            return __import__("subprocess").CompletedProcess(
                cmd, 1, "", "could not extract any data with that passphrase!"
            )

        with patch("automisc.core.actions.steghide_extract.subprocess.run", side_effect=fake_run):
            r = a.run({"file_path": str(p), "__password__": "wrong"})

        assert r.success is False
        assert "密码错误" in r.message
