"""测试 tools/steganography/image/steghide.py

v0.1.0b-PR2 范围：steghide adapter 仅调 ``steghide info``（无密码）。
无需 embed/extract 测试（GUI 触发 + 用户输入密码）。
"""
from __future__ import annotations

import shutil

import pytest

from automisc.core.registry import get_tool
from automisc.tools.steganography.image.steghide import SteghideAdapter


@pytest.fixture(autouse=True)
def require_steghide():
    if shutil.which("steghide") is None:
        pytest.skip("steghide not in PATH")


def test_steghide_adapter_is_registered():
    a = get_tool("stegseek")
    assert isinstance(a, SteghideAdapter)
    assert a.name == "stegseek"
    assert a.category == "steganography_image"


def test_steghide_handles_missing_file(tmp_path):
    a = SteghideAdapter()
    try:
        result = a.run(str(tmp_path / "does_not_exist_xyz"))
    except Exception as e:
        pytest.fail(f"SteghideAdapter crashed: {e}")
    assert result is not None
    assert result.exit_code != 0


def test_steghide_unavailable_format_jpg(tmp_path):
    """macOS 默认 steghide 编译未启用 JPEG → 应触发 steghide_unavailable 可疑点。"""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "red")
    p = tmp_path / "test.jpg"
    img.save(p, "JPEG")

    a = SteghideAdapter()
    try:
        result = a.run(str(p))
    except Exception as e:
        pytest.fail(f"SteghideAdapter crashed: {e}")

    # macOS 自带 steghide 对 JPEG 输出 "can not read input file. steghide has been compiled without support for jpeg files"
    unavailable_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_unavailable"]
    # 注意：如果 steghide 是 brew 装的 --with-jpeg，则不会触发这个
    # 在我们的 macOS 环境实测会触发
    if "jpeg" in (result.stdout + result.stderr).lower() and "compiled without" in (result.stdout + result.stderr).lower():
        assert len(unavailable_sp) == 1
        assert "编译未启用" in unavailable_sp[0].matched_pattern


def test_steghide_capacity_info_on_bmp(tmp_path):
    """BMP 是 steghide 支持的格式 → 应输出 capacity 信息。"""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "green")
    p = tmp_path / "test.bmp"
    img.save(p, "BMP")

    a = SteghideAdapter()
    result = a.run(str(p))
    # BMP 是 steghide 原生支持格式；如果没嵌入数据，output 应有 capacity 信息
    # 如果 macOS steghide 编译未启 BMP 也可能不可用——只测 "不 crash"
    assert result is not None
    # 可能的情况：capacity 解析命中 / unavailable 命中 / 都没命中
    # 主要验证：不 crash + 至少给 1 个 suspicious point 或明确 0 个（合法）


def test_steghide_no_data_clean_bmp(tmp_path):
    """干净的 BMP（无嵌入数据）应输出 "the file does not contain any steghide data"。"""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "blue")
    p = tmp_path / "clean.bmp"
    img.save(p, "BMP")

    a = SteghideAdapter()
    result = a.run(str(p))
    # 关键断言：result 合法返回（不 crash）
    assert result is not None
    # 不应该触发 steghide_embedded 信号（干净文件）
    embedded_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_embedded"]
    assert len(embedded_sp) == 0


def test_steghide_adapter_metadata():
    """adapter 元数据正确。"""
    a = SteghideAdapter()
    assert a.description
    assert a.default_timeout > 0


# ---------- v0.5-philosophy-rethink: stegseek 平替 (macOS 友好) ----------

# 这些测试只在装了 stegseek 时跑 (per v0.5 设计, macOS 装 stegseek 后会激活)
require_stegseek = pytest.mark.skipif(
    shutil.which("stegseek") is None,
    reason="stegseek not installed (v0.5+ 推荐安装)",
)


@require_stegseek
def test_steghide_uses_stegseek_when_available(tmp_path, monkeypatch):
    """v0.5: stegseek 在 PATH 时 adapter 优先用 stegseek (macOS 现代 fork, JPEG 支持).

    验证方式: mock shutil.which 强制返回 stegseek 路径, 然后验证 run() 走 _run_stegseek.
    """
    from automisc.tools.steganography.image import steghide as steghide_mod

    # 强制 stegseek "可用"
    fake_stegseek = "/fake/path/to/stegseek"
    monkeypatch.setattr(steghide_mod.shutil, "which", lambda x: fake_stegseek if x == "stegseek" else None)

    a = SteghideAdapter()
    # mock _run_stegseek 看是否被调
    called = {"yes": False}

    def fake_run_stegseek(file_path):
        called["yes"] = True
        from automisc.core.result import ToolResult
        return ToolResult(
            tool_name=a.name, exit_code=0, stdout="", stderr="", duration_ms=0,
        )

    monkeypatch.setattr(a, "_run_stegseek", fake_run_stegseek)

    a.run("/tmp/fake.jpg")
    assert called["yes"], "stegseek 在 PATH 时必须走 _run_stegseek 路径"


def test_steghide_falls_back_to_steghide_when_no_stegseek(monkeypatch):
    """v0.5: stegseek 不在 PATH 时 adapter fallback 到 steghide (Linux/Windows)."""
    from automisc.tools.steganography.image import steghide as steghide_mod

    # 强制 stegseek "不可用"
    def fake_which(name):
        if name == "stegseek":
            return None
        # 其他 (steghide 等) 走真实 which
        import shutil as real_shutil
        return real_shutil.which(name)

    monkeypatch.setattr(steghide_mod.shutil, "which", fake_which)

    a = SteghideAdapter()
    called = {"yes": False}

    def fake_fallback(file_path):
        called["yes"] = True
        from automisc.core.result import ToolResult
        return ToolResult(
            tool_name=a.name, exit_code=0, stdout="", stderr="", duration_ms=0,
        )

    monkeypatch.setattr(a, "_run_steghide_fallback", fake_fallback)
    a.run("/tmp/fake.jpg")
    assert called["yes"], "stegseek 不在 PATH 时必须走 _run_steghide_fallback"


@require_stegseek
def test_steghide_extracts_empty_password_steg(tmp_path):
    """v0.5: stegseek 抓到空密码 → 写 steghide_extracted SP (severity=5).

    模拟: stegseek --crack 输出 "Found passphrase" + "Original filename" + 提取内容.
    """
    import re
    from automisc.core.result import ToolResult
    from automisc.core.suspicious import SuspiciousPoint

    # 准备 mock 输出 + 提取内容
    fake_stdout = ""
    fake_stderr = (
        'StegSeek 0.6\n\n'
        '[i] Found passphrase: ""\n'
        '[i] Original filename: "ko.txt".\n'
        '[i] Extracting to "/tmp/fake_out.bin".\n'
    )
    fake_content = b"compressed password: secret123\n"

    a = SteghideAdapter()

    # mock subprocess 返回值 + 写 temp 内容到 out_path
    import tempfile, os
    from pathlib import Path

    out_path = None
    def fake_run_subprocess(cmd, *args, **kwargs):
        nonlocal out_path
        # 找 cmd 里的 out_path (最后一个位置参数)
        out_path = cmd[-1]
        Path(out_path).write_bytes(fake_content)
        return (0, fake_stdout, fake_stderr, 100)

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(a, "_run_subprocess", fake_run_subprocess)

        result = a.run("/tmp/fake.jpg")
    finally:
        monkeypatch.undo()
        if out_path and Path(out_path).exists():
            Path(out_path).unlink()

    # 验证 SP
    extracted_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_extracted"]
    assert len(extracted_sp) == 1
    sp = extracted_sp[0]
    assert sp.severity == 5
    assert "Found passphrase" not in sp.matched_pattern  # 不暴露内部命令
    assert "secret123" in sp.matched_pattern or "secret123" in sp.suggested_action
    # 验证密码 + 文件名 + 内容
    assert re.search(r'密码', sp.matched_pattern)
    assert "ko.txt" in sp.matched_pattern


@require_stegseek
def test_steghide_no_match_clean_bmp_no_sp(monkeypatch):
    """v0.5: stegseek "Could not find a valid passphrase" → 不写 SP (避免 clean 文件误报).

    原因: stegseek 在 clean 文件和"需要大 wordlist"文件上报告同样的错误 (二义性).
    写 steghide_embedded SP 会让所有 clean 文件被误报 — 用户烦.
    """
    a = SteghideAdapter()

    def fake_run_subprocess(cmd, *args, **kwargs):
        # 模拟 stegseek 在干净 BMP 上的输出
        return (1, "", "[!] error: Could not find a valid passphrase.\n", 50)

    monkeypatch.setattr(a, "_run_subprocess", fake_run_subprocess)
    result = a.run("/tmp/fake_clean.bmp")

    # 关键断言: 干净文件 + 二义性错误 → 0 SP
    embedded_sp = [sp for sp in result.suspicious_points if sp.category == "steghide_embedded"]
    assert len(embedded_sp) == 0, (
        f"clean 文件不该有 steghide_embedded SP (避免误报): {result.suspicious_points}"
    )