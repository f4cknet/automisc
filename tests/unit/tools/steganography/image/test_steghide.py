"""测试 tools/steganography/image/steghide.py (v0.5-stegseek-remove 重构)

v0.5-stegseek-remove (2026-06-28) 重构:
- name: 'stegseek' -> 'steghide'
- 删 stegseek 优先逻辑 (Win 端不可用, Owner 拍板删)
- 新 _try_empty_password_extract 兜底 (CVE-2021-27211)

测试策略:
- 元数据 / 注册测试不依赖 binary, 一直跑
- 真实 binary 调用的测试用 @pytest.mark.skipif 守护
- Mock 测试 (resolve_tool_binary patch) 不依赖 binary, 一直跑
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.core.registry import get_tool
from automisc.tools.paths import resolve_tool_binary
from automisc.tools.steganography.image.steghide import SteghideAdapter


def _steghide_available() -> bool:
    """Check steghide binary via PATH or extend-tools fallback (per v0.5-platform-extend-tools)."""
    if shutil.which("steghide"):
        return True
    if resolve_tool_binary("steghide"):
        return True
    return False


require_steghide_binary = pytest.mark.skipif(
    not _steghide_available(),
    reason="steghide not in PATH nor extend-tools/bin/win-x64/",
)


# ---------- 不依赖 binary 的元数据 / 注册测试 ----------

def test_steghide_adapter_is_registered():
    """v0.5-stegseek-remove: adapter name='steghide' (从 'stegseek' 改)."""
    a = get_tool("steghide")
    assert isinstance(a, SteghideAdapter)
    assert a.name == "steghide"
    assert a.category == "steganography_image"


def test_steghide_adapter_metadata():
    """adapter 元数据正确."""
    a = SteghideAdapter()
    assert a.description
    assert a.default_timeout > 0


@require_steghide_binary
def test_steghide_handles_missing_file(tmp_path):
    a = SteghideAdapter()
    try:
        result = a.run(str(tmp_path / "does_not_exist_xyz"))
    except Exception as e:
        pytest.fail(f"SteghideAdapter crashed: {e}")
    assert result is not None
    assert result.exit_code != 0


@require_steghide_binary
def test_steghide_capacity_info_on_bmp(tmp_path):
    """BMP 是 steghide 支持的格式 → 应输出 capacity 信息."""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "green")
    p = tmp_path / "test.bmp"
    img.save(p, "BMP")

    a = SteghideAdapter()
    result = a.run(str(p))
    assert result is not None


@require_steghide_binary
def test_steghide_no_data_clean_bmp(tmp_path):
    """干净的 BMP（无嵌入数据）→ 不应触发 steghide_embedded 信号."""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "blue")
    p = tmp_path / "clean.bmp"
    img.save(p, "BMP")

    a = SteghideAdapter()
    result = a.run(str(p))
    embedded_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_embedded"]
    assert len(embedded_sp) == 0


# ---------- v0.5-stegseek-remove: 空密码 extract 兜底 (CVE-2021-27211) ----------

class TestEmptyPasswordExtract:
    """`_try_empty_password_extract` 是 Win 端 silent miss 的修复核心.

    之前 steghide info 命中但 extract 没自动跑, Owner 实战 123456cry.jpg /
    meihuai.jpg 都是空密码, 之前 Win 端漏报. v0.5-stegseek-remove 加这一步.

    这些测试 mock _run_subprocess / resolve_tool_binary, 不需要真实 binary.
    """

    def test_empty_pw_extract_success_writes_sev5_sp(self, tmp_path):
        """空密码 extract 成功 → 写 steghide_extracted SP severity=5."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        fake_content = b"qwe.zip password: bV1g6t5wZDJif^J7\n"

        a = SteghideAdapter()

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "info" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0,
                    b"", b"capacity: 1.0KB\nembeds: 1 files",
                )
            out_idx = cmd.index("-xf") + 1
            out_path = cmd[out_idx]
            Path(out_path).write_bytes(fake_content)
            return subprocess.CompletedProcess(cmd, 0, b"", b"wrote extracted data")

        with patch("automisc.tools.steganography.image.steghide.resolve_tool_binary", return_value="/fake/steghide"), \
             patch("automisc.tools.steganography.image.steghide.subprocess.run", side_effect=fake_subprocess_run):
            result = a.run(str(p))

        extracted_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_extracted"]
        assert len(extracted_sp) == 1
        sp = extracted_sp[0]
        assert sp.severity == 5
        assert "空密码" in sp.matched_pattern
        assert "bV1g6t5wZDJif^J7" in sp.matched_pattern

    def test_empty_pw_extract_wrong_password_no_sp(self, tmp_path):
        """空密码 extract 失败 (错密码) → 不写 SP (避免 noise)."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideAdapter()

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "info" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0,
                    b"", b"capacity: 1.0KB\nembeds: 1 files",
                )
            return subprocess.CompletedProcess(
                cmd, 1, b"", b"could not extract any data with that passphrase!",
            )

        with patch("automisc.tools.steganography.image.steghide.resolve_tool_binary", return_value="/fake/steghide"), \
             patch("automisc.tools.steganography.image.steghide.subprocess.run", side_effect=fake_subprocess_run):
            result = a.run(str(p))

        extracted_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_extracted"]
        assert len(extracted_sp) == 0, (
            f"空密码失败时不该写 steghide_extracted SP: {result.suspicious_points}"
        )

    def test_empty_pw_extract_no_steghide_binary(self, tmp_path):
        """steghide binary 不存在 → graceful return (不 crash, 写 unavailable SP)."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideAdapter()

        with patch("automisc.tools.steganography.image.steghide.resolve_tool_binary", return_value=None):
            result = a.run(str(p))

        assert result is not None
        unavailable_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_unavailable"]
        assert len(unavailable_sp) == 1

    def test_steghide_binary_uses_resolve_tool_binary(self, tmp_path):
        """v0.5-platform-extend-tools: adapter 走 resolve_tool_binary (PATH 优先 → extend-tools fallback)."""
        from PIL import Image
        img = Image.new("RGB", (32, 32), "red")
        p = tmp_path / "test.jpg"
        img.save(p, "JPEG")

        a = SteghideAdapter()

        with patch("automisc.tools.steganography.image.steghide.resolve_tool_binary") as mock_rtb:
            mock_rtb.return_value = None
            a.run(str(p))
            assert mock_rtb.called, "必须走 resolve_tool_binary (extend-tools fallback)"
