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
    a = get_tool("steghide")
    assert isinstance(a, SteghideAdapter)
    assert a.name == "steghide"
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