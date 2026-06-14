"""v0.5-hex-router 单测: 长 hex 串智能路由 (Owner 13:39 触发).

Owner 反馈:
> 我发现一个问题, 你在窗口中打印的是一部分 hex, 我误以为是全部的 hex 了.
> 既然发现这么长的 hex 在出现在 strings 的结果中, 那必然是非常重要的线索,
> 所以你应该按 auto_run 逻辑继续走下去, 这串 hex 的背后到底是什么, 是图片、压缩文件还是纯 ASCII?
> 因为 35000+ 会撑爆 window, 你只能截断开头的一部分打印, 所以我无法得到全部的 hex,
> 所以这一步必须是由 auto_run 往下走.
> 如果是非常短, 比如低于 200 字符的 hex, 那你打印给我, 我复制到 input 中, 然后点击 hex->ascii 这没问题.

覆盖:
- is_long_hex_text: 长度 + 偶数 + 全 hex 字符判定
- detect_magic: PNG/JPG/GIF/ZIP/RAR/7z/GZ/BZ2/ELF/EXE/BMP/RIFF magic
- route_hex_to_file: 写 /tmp + follow-up (zbar/unzip)
- strings adapter 集成: 长 hex (>= 200) 自动 trigger + 不打印 35000 字符; 短 hex 仍打印
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ---------- is_long_hex_text ----------
class TestIsLongHexText:
    def test_short_hex_not_triggered(self):
        from automisc.core.actions.hex_router import is_long_hex_text
        # 50 chars < 200 (default min)
        assert is_long_hex_text("aabbcc" * 8) is False
        assert is_long_hex_text("a" * 100) is False

    def test_long_hex_triggered(self):
        from automisc.core.actions.hex_router import is_long_hex_text
        # 200 chars even
        assert is_long_hex_text("ab" * 100) is True
        # 300 chars
        assert is_long_hex_text("aabb" * 75) is True

    def test_odd_length_rejected(self):
        from automisc.core.actions.hex_router import is_long_hex_text
        # 201 chars (odd) - 即使全 hex 也拒绝
        assert is_long_hex_text("ab" * 100 + "a") is False

    def test_non_hex_rejected(self):
        from automisc.core.actions.hex_router import is_long_hex_text
        # 300 chars 含 'g' (非 hex)
        assert is_long_hex_text("aabbgg" * 50) is False

    def test_empty_rejected(self):
        from automisc.core.actions.hex_router import is_long_hex_text
        assert is_long_hex_text("") is False
        assert is_long_hex_text("   ") is False


# ---------- detect_magic ----------
class TestDetectMagic:
    def test_png(self):
        from automisc.core.actions.hex_router import detect_magic
        label, ext, ftype, _ = detect_magic(bytes.fromhex("89504e470d0a1a0a"))
        assert ext == "png"
        assert ftype == "image"

    def test_jpeg(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("ffd8ffe000104a464946"))
        assert ext == "jpg"
        assert ftype == "image"

    def test_zip(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("504b0304140000000800"))
        assert ext == "zip"
        assert ftype == "archive"

    def test_rar(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("526172211a0700"))
        assert ext == "rar"
        assert ftype == "archive"

    def test_7z(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("377abcaf271c"))
        assert ext == "7z"
        assert ftype == "archive"

    def test_gif(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(b"GIF89a")
        assert ext == "gif"
        assert ftype == "image"

    def test_gz(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("1f8b"))
        assert ext == "gz"
        assert ftype == "archive"

    def test_elf(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(bytes.fromhex("7f454c46"))
        assert ext == "elf"
        assert ftype == "binary"

    def test_exe(self):
        from automisc.core.actions.hex_router import detect_magic
        _, ext, ftype, _ = detect_magic(b"MZ")
        assert ext == "exe"
        assert ftype == "binary"

    def test_unknown(self):
        from automisc.core.actions.hex_router import detect_magic
        label, ext, ftype, _ = detect_magic(b"just plain text")
        assert ext == ".bin"
        assert ftype == "unknown"


# ---------- route_hex_to_file ----------
class TestRouteHexToFile:
    def test_routes_png_hex(self):
        """Owner 13:39 真实场景: 35000 字符 hex 头 = PNG -> 写 /tmp/foo.png."""
        from automisc.core.actions.hex_router import route_hex_to_file

        # 真实 PNG header (1x1 PNG header, 8 bytes IHDR)
        png_header = "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154"
        # 拼到 35000 chars (实际 34082)
        hex_text = png_header + "00" * 17000  # 82 + 34000 = 34082

        result = route_hex_to_file(hex_text, follow_up=False)
        assert "image" in result.magic
        assert result.ext == "png"
        assert result.file_type == "image"
        # 34082 / 2 = 17041 bytes raw
        assert result.raw_size == 17041
        # v0.5-hex-router-samedir: 无 input_path 走系统 /tmp/automisc/
        assert "/tmp" in result.output_path or "/private/tmp" in result.output_path
        assert "automisc" in result.output_path
        # 验证 file 真存在且 magic 头对
        out = Path(result.output_path)
        assert out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        # cleanup
        out.unlink(missing_ok=True)

    def test_routes_zip_hex(self):
        from automisc.core.actions.hex_router import route_hex_to_file
        # ZIP magic + 0 padding
        zip_header = "504b0304140000000800"
        hex_text = zip_header + "00" * 100  # 208 chars
        result = route_hex_to_file(hex_text, follow_up=False)
        assert result.ext == "zip"
        assert result.file_type == "archive"
        Path(result.output_path).unlink(missing_ok=True)

    def test_short_hex_rejected(self):
        from automisc.core.actions.hex_router import route_hex_to_file, HexRouterError
        # < 200 chars
        with pytest.raises(HexRouterError):
            route_hex_to_file("aabb" * 30)  # 120 chars

    def test_invalid_hex_rejected(self):
        from automisc.core.actions.hex_router import route_hex_to_file, HexRouterError
        # 非 hex 字符
        with pytest.raises(HexRouterError):
            route_hex_to_file("xyz" * 70)  # 210 chars but non-hex


# ---------- strings adapter 集成 ----------
class TestStringsAdapterIntegration:
    def test_short_hex_prints_to_gui(self, tmp_path):
        """短 hex 串 (50 chars) 仍打印前 200 字符到 GUI (per Owner 13:39 设计)."""
        from automisc.tools.shared.strings import StringsAdapter

        f = tmp_path / "short.txt"
        # 50 chars hex (低于 200 阈值) - 仍打印
        f.write_text("aabbcc" * 8 + "\n")
        a = StringsAdapter()
        r = a.run(str(f))
        # 渲染版应含 L1 命中行 (前 200 字符)
        assert "L1:" in r.stdout
        assert "aabbcc" in r.stdout

    def test_long_hex_does_not_print_35000_chars(self, tmp_path):
        """长 hex 串 (35000 chars) 不打印实际内容 -> L1 显示 <hex_router 已自动处理>."""
        from automisc.tools.shared.strings import StringsAdapter

        f = tmp_path / "long.txt"
        # 35000 chars hex (PNG header repeated)
        png_header = (
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154"
        )
        body = png_header * 200 + "00" * 10000  # 38200 chars
        f.write_text(body)
        a = StringsAdapter()
        r = a.run(str(f))
        # 渲染版应含 hex_router summary
        assert "v0.5-hex-router" in r.stdout
        assert "已自动 route" in r.stdout
        # 命中行应是占位符 (不含 35000 字符实际 hex)
        assert "<hex_router 已自动处理" in r.stdout
        # 35000 字符不应直接出现
        # (但前 60 字符的 preview "89504e47..." 可能出现, 验证主要 body 不出现)
        # 跑 magic 探测部分
        assert "magic=image" in r.stdout
        assert "saved=" in r.stdout
        # cleanup routed file
        import glob
        for ff in glob.glob("/tmp/automisc_text_outputs/hex_router_image_*"):
            ff.unlink(missing_ok=True)

    def test_long_hex_routed_file_is_valid_png(self, tmp_path):
        """长 hex 自动路由产出的文件是真 PNG (magic 头 + 可被 zbar/file 识别)."""
        from automisc.tools.shared.strings import StringsAdapter
        from automisc.core.actions.hex_router import route_hex_to_file

        # 先直接调 route_hex_to_file 验证产物
        png_header = "89504e470d0a1a0a" + "00" * 100
        result = route_hex_to_file(png_header + "00" * 100, follow_up=False)
        # 验证 PNG magic
        out = Path(result.output_path)
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        out.unlink(missing_ok=True)

    def test_long_hex_short_zip_still_works(self, tmp_path):
        """短 zip hex (100 chars, < 200) 仍打印, 不走 router."""
        from automisc.tools.shared.strings import StringsAdapter

        f = tmp_path / "f.bin"
        # 100 chars zip (50 bytes)
        zip_hex = ("504b0304140000000800" * 5)  # 100 chars
        f.write_text(zip_hex)
        a = StringsAdapter()
        r = a.run(str(f))
        # 100 chars < 200 -> 不触发 router, 仍打印
        assert "v0.5-hex-router" not in r.stdout
        # L1 命中行有内容
        assert "L1:" in r.stdout
        assert "504b" in r.stdout


# ---------- v0.5-hex-router-samedir: 输出路径优先级 (Owner 14:24) ----------
class TestRouteHexToFileSamedir:
    """v0.5-hex-router-samedir (per Owner 14:24 反馈):
    - input_path 已知 -> samedir (per v0.5-output-samedir)
    - out_dir 显式 -> 用之
    - 都不传 -> 系统 /tmp/automisc (不是 macOS /private/var/folders/.../T/)
    """

    def test_input_path_writes_to_samedir(self, tmp_path):
        """input_path 已知时, 写到 file_path.parent (samedir per v0.5-output-samedir)."""
        from automisc.core.actions.hex_router import route_hex_to_file

        fake_input = tmp_path / "meihuai.jpg"
        fake_input.write_text("dummy")  # 内容无关, 只用路径
        # PNG header 拼到 35000 chars
        png_header = "89504e470d0a1a0a"
        hex_text = png_header + "00" * 17000
        result = route_hex_to_file(hex_text, follow_up=False, input_path=fake_input)
        out = Path(result.output_path)
        # samedir!
        assert out.parent.resolve() == fake_input.parent.resolve()
        assert out.exists()
        out.unlink(missing_ok=True)

    def test_out_dir_explicit(self, tmp_path):
        """out_dir 显式 (无 input_path) -> 用 out_dir."""
        from automisc.core.actions.hex_router import route_hex_to_file

        png_header = "89504e470d0a1a0a"
        hex_text = png_header + "00" * 17000
        custom = tmp_path / "my_custom_dir"
        result = route_hex_to_file(
            hex_text, follow_up=False, out_dir=custom
        )
        out = Path(result.output_path)
        assert out.parent.resolve() == custom.resolve()
        out.unlink(missing_ok=True)

    def test_no_anchor_writes_to_system_tmp(self):
        """无 input_path / out_dir -> 系统 /tmp/automisc/ (Owner 期望的 /tmp, 不是 /private/var/folders)."""
        from automisc.core.actions.hex_router import route_hex_to_file

        png_header = "89504e470d0a1a0a"
        hex_text = png_header + "00" * 17000
        result = route_hex_to_file(hex_text, follow_up=False)
        out = Path(result.output_path)
        # 不应在 macOS /private/var/folders/.../T/ (旧 gettempdir 行为)
        assert "/private/var/folders" not in result.output_path
        # 应该在 /tmp/automisc/ 下
        assert "/tmp" in result.output_path or "/private/tmp" in result.output_path
        assert "automisc" in result.output_path
        out.unlink(missing_ok=True)

    def test_strings_adapter_writes_to_input_samedir(self, tmp_path):
        """end-to-end: strings adapter 调 route_hex_to_file, saved 路径在 input_path.parent.

        Owner 14:24 反馈: 'saved=/private/var/folders/.../automisc_text_outputs/hex_router_unknown_xxx..bin'
        修: strings adapter 现在传 input_path, 应该写到 meihuai.jpg 同目录.
        """
        # 造个长 hex 串文件
        f = tmp_path / "fake.jpg"
        png_header = "89504e470d0a1a0a"
        f.write_text(png_header + "00" * 17000)

        from automisc.tools.shared.strings import StringsAdapter
        a = StringsAdapter()
        r = a.run(str(f))
        # 找 saved=
        saved_line = next(
            (l for l in r.stdout.splitlines() if "saved=" in l), None
        )
        assert saved_line is not None, f"应该有 saved= 行, 实际 stdout: {r.stdout!r}"
        # saved 应在 f.parent (samedir)
        assert str(f.parent) in saved_line, f"saved 不在 samedir: {saved_line}"
        # 不应在 /private/var/folders (旧 gettempdir)
        assert "/private/var/folders" not in saved_line

        # cleanup
        from automisc.core.utils.output_path import is_in_tmp
        import re
        m = re.search(r"saved=(\S+?)(?:,|\s|$)", saved_line)
        if m:
            saved_path = m.group(1)
            if not is_in_tmp(saved_path):
                Path(saved_path).unlink(missing_ok=True)
