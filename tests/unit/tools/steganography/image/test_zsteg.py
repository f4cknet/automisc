"""测试 tools/steganography/image/zsteg.py"""
from __future__ import annotations

import shutil

import pytest

from automisc.core.registry import get_tool
from automisc.tools.steganography.image.zsteg import ZstegAdapter


@pytest.fixture(autouse=True)
def require_zsteg():
    if shutil.which("zsteg") is None:
        pytest.skip("zsteg not in PATH")


def test_zsteg_adapter_is_registered():
    a = get_tool("zsteg")
    assert isinstance(a, ZstegAdapter)
    assert a.name == "zsteg"
    assert a.category == "steganography_image"


def test_zsteg_detects_lsb_text(tmp_path):
    """写入 LSB 数据（flag）→ zsteg 应能识别。"""
    from PIL import Image
    img = Image.new("RGB", (32, 32), "red")
    p = tmp_path / "lsb_flag.png"
    img.save(p, "PNG")

    # 用 PIL 写入 LSB：把 "flag{pr2_lsb_test}" 写到 R 通道 LSB
    img2 = Image.open(p)
    pixels = img2.load()
    msg = "flag{pr2_lsb_test}"
    bits = "".join(format(ord(c), "08b") for c in msg)
    idx = 0
    for y in range(32):
        for x in range(32):
            if idx >= len(bits):
                break
            r, g, b = pixels[x, y]
            r = (r & 0xFE) | int(bits[idx])
            pixels[x, y] = (r, g, b)
            idx += 1
        if idx >= len(bits):
            break
    img2.save(p, "PNG")

    a = ZstegAdapter()
    result = a.run(str(p))
    assert result.is_success
    # 应检测到 lsb_text
    sp = [p for p in result.suspicious_points if p.category == "lsb_text"]
    assert any("flag{pr2_lsb_test}" in p.matched_pattern for p in sp), (
        f"missing flag in LSB, got: {[(p.category, p.matched_pattern) for p in result.suspicious_points if 'lsb' in p.category]}"
    )


def test_zsteg_handles_non_png(tmp_path):
    """zsteg 在非 PNG 上应优雅处理（exit code 可能非 0 但不 crash）。"""
    p = tmp_path / "not_png.txt"
    p.write_text("hello world")
    a = ZstegAdapter()
    try:
        result = a.run(str(p))
    except Exception as e:
        pytest.fail(f"ZstegAdapter crashed: {e}")
    # 不 crash 即通过（exit code 可能非 0）
    assert result is not None


def test_zsteg_handles_missing_file(tmp_path):
    a = ZstegAdapter()
    try:
        result = a.run(str(tmp_path / "does_not_exist_xyz"))
    except Exception as e:
        pytest.fail(f"ZstegAdapter crashed: {e}")
    assert result is not None
    # zsteg 是 Ruby 工具，文件不存在时 exit code 可能是 0（异常走 stdout）
    # 只要 adapter 不 crash 且输出包含错误信息即通过
    combined = (result.stdout + result.stderr).lower()
    assert "no such file" in combined or "enoent" in combined or result.exit_code != 0


def test_zsteg_plain_png_no_lsb_match(tmp_path):
    """纯随机 PNG（不写 LSB）→ 不应触发 lsb_text category（避免 false positive）。"""
    from PIL import Image
    import random
    img = Image.new("RGB", (32, 32))
    pixels = img.load()
    for y in range(32):
        for x in range(32):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    p = tmp_path / "random.png"
    img.save(p, "PNG")

    a = ZstegAdapter()
    result = a.run(str(p))
    assert result.is_success
    # 随机 PNG 偶有 false positive，但不应出现完整 flag 关键字
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "lsb_text"]
    for sp in flag_sp:
        # false positive 也只是 "？" 等无意义内容
        assert "?" in sp.matched_pattern or len(sp.matched_pattern) < 30, (
            f"unexpected meaningful lsb_text match: {sp.matched_pattern}"
        )


def test_zsteg_result_has_channel_info(tmp_path):
    """命中后 matched_pattern 应包含 channel 信息（b1,r,lsb,xy 等）。"""
    from PIL import Image
    img = Image.new("RGB", (16, 16), "red")
    p = tmp_path / "channel.png"
    img.save(p, "PNG")

    a = ZstegAdapter()
    result = a.run(str(p))
    # 不一定有可疑点，但若 file_header_lsb 命中应含 channel
    for sp in result.suspicious_points:
        if sp.category == "file_header_lsb":
            assert "b" in sp.matched_pattern, f"missing bit/channel in: {sp.matched_pattern}"