"""pytest 共享 fixture。"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_text_file(tmp_path: Path) -> Path:
    """创建一个含 flag / base64 / 关键字的文本 fixture。

    用于 6 个共享 adapter 的最小集成 smoke test。
    """
    content = (
        b"hello world\n"
        b"flag{test_fixture_flag_12345}\n"
        b"some password=secret123\n"
        b"aGVsbG8gd29ybGQgdGVzdA==\n"  # base64: "hello world test"
    )
    p = tmp_path / "fixture.txt"
    p.write_bytes(content)
    return p


@pytest.fixture
def tmp_png_file(tmp_path: Path) -> Path:
    """创建一个最小合法 PNG 文件（用于 foremost / binwalk 测试）。"""
    from PIL import Image  # 已在项目 Python 路径中
    img = Image.new("RGB", (8, 8), "red")
    p = tmp_path / "fixture.png"
    img.save(p, "PNG")
    return p


@pytest.fixture
def tmp_polyglot_file(tmp_path: Path) -> Path:
    """创建一个 polyglot 文件：PNG 头 + 嵌入 ZIP 注释。"""
    png_head = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077533de00000000c4944415478da636460f8cfc00000000400012b5e5e880000000049454e44ae426082"
    )
    # 在 PNG IEND 后追加 ZIP（per ctf-forensics/steganography.md "File overlays"）
    zip_tail = bytes.fromhex(
        "504b0304"  # ZIP local file header
        "14000000000000000000000000000000000000000000000000"
        "746573742e747874"  # filename "test.txt"
        "7374616e64617264"  # extra field
        "0a00"
        "00000000"
        "00000000"
        "0000000000000000"
        "504b01021e030a0000000000000000000000000000000000000000000000000000b4810000000000000000000000000000000000000054686973206973206120746573740a"
        "504b050600000000010001003b0000003b0000000000"
    )
    p = tmp_path / "fixture_polyglot.png"
    p.write_bytes(png_head + zip_tail)
    return p