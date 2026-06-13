"""单测: core.decoders.base64_image (v0.5+ standalone)

覆盖 5 决策树分支 + 3 边界.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from automisc.core.decoders.base64_image import (
    Base64ImageError,
    Base64ImageResult,
    _strip_data_url,
    _strip_padding,
    _try_with_fallback_headers,
    decode_file_to_image,
)


# ---------- helpers ----------
def _make_png_bytes() -> bytes:
    """最小 1x1 PNG bytes."""
    img = Image.new("RGB", (1, 1), "red")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _make_jpeg_bytes() -> bytes:
    """最小 1x1 JPEG bytes."""
    img = Image.new("RGB", (1, 1), "blue")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _write_tmp(content: str | bytes, suffix: str = ".txt") -> str:
    if isinstance(content, str):
        mode = "w"
    else:
        mode = "wb"
    tmp = tempfile.NamedTemporaryFile(mode=mode, delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------- _strip_data_url ----------
class TestStripDataUrl:
    def test_strip_with_data_jpg_header(self):
        text = "data:image/jpg;base64,iVBORw0KGgo="
        b64, mime = _strip_data_url(text)
        assert b64 == "iVBORw0KGgo="
        assert mime == "image/jpg"

    def test_strip_with_data_jpeg_header(self):
        text = "data:image/jpeg;base64,abcdefghijklmnop"
        b64, mime = _strip_data_url(text)
        assert b64 == "abcdefghijklmnop"
        assert mime == "image/jpeg"

    def test_strip_with_data_png_header(self):
        text = "data:image/png;base64,xyz"
        b64, mime = _strip_data_url(text)
        assert b64 == "xyz"
        assert mime == "image/png"

    def test_no_data_url_header(self):
        text = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4//8/AwAI/AL+XJ/PIQAAAABJRU5ErkJggg=="
        b64, mime = _strip_data_url(text)
        assert b64 == text
        assert mime is None

    def test_data_url_with_extra_params(self):
        # data:image/png;charset=utf-8;base64,...
        text = "data:image/png;charset=utf-8;base64,abc"
        b64, mime = _strip_data_url(text)
        assert b64 == "abc"
        assert mime == "image/png"

    def test_data_url_unsupported_mime(self):
        # data:text/plain;base64,xxx -> 不匹配 (不在白名单)
        text = "data:text/plain;base64,abc"
        b64, mime = _strip_data_url(text)
        assert b64 == text
        assert mime is None


# ---------- _strip_padding ----------
class TestStripPadding:
    def test_no_padding_needed(self):
        assert _strip_padding("abcd") == "abcd"

    def test_one_eq_needed(self):
        assert _strip_padding("abc") == "abc="

    def test_two_eq_needed(self):
        assert _strip_padding("ab") == "ab=="


# ---------- _try_with_fallback_headers ----------
class TestTryWithFallbackHeaders:
    def test_pure_base64_png(self):
        png_bytes = _make_png_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        result = _try_with_fallback_headers(b64)
        assert result is not None
        raw, mime = result
        assert raw == png_bytes
        assert mime in ("image/png", "image/jpeg", "image/jpg")  # fallback 可能选 jpeg

    def test_pure_base64_jpeg(self):
        jpeg_bytes = _make_jpeg_bytes()
        b64 = base64.b64encode(jpeg_bytes).decode()
        result = _try_with_fallback_headers(b64)
        assert result is not None
        raw, _ = result
        assert raw == jpeg_bytes

    def test_invalid_base64_returns_none(self):
        result = _try_with_fallback_headers("not!valid!base64!@#")
        assert result is None


# ---------- decode_file_to_image ----------
class TestDecodeFileToImage:
    def test_data_url_header_png(self, tmp_path):
        """Case A: 文件含 data:image/jpg;base64 头 (KEY.exe 模式)"""
        png_bytes = _make_png_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        content = f"data:image/jpg;base64,{b64}"
        f = tmp_path / "with_header.txt"
        f.write_text(content)

        r = decode_file_to_image(str(f), keep_output=True)
        assert isinstance(r, Base64ImageResult)
        assert r.source_mime_hint == "image/jpg"
        assert "PNG image" in r.detected_mime
        assert r.raw_size == len(png_bytes)
        assert Path(r.output_path).exists()
        Path(r.output_path).unlink()  # cleanup

    def test_pure_base64_no_header(self, tmp_path):
        """Case B: 纯 base64 无头, 内容是 PNG (meihuai 风格)"""
        png_bytes = _make_png_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        f = tmp_path / "pure_b64.txt"
        f.write_text(b64)

        r = decode_file_to_image(str(f), keep_output=True)
        assert r.source_mime_hint in ("image/png", "image/jpeg", "image/jpg")
        assert "PNG image" in r.detected_mime or "JPEG image" in r.detected_mime
        Path(r.output_path).unlink()

    def test_pure_base64_no_header_jpeg(self, tmp_path):
        """Case C: 纯 base64 无头, 内容是 JPEG"""
        jpeg_bytes = _make_jpeg_bytes()
        b64 = base64.b64encode(jpeg_bytes).decode()
        f = tmp_path / "pure_jpeg_b64.txt"
        f.write_text(b64)

        r = decode_file_to_image(str(f), keep_output=True)
        assert "image" in r.detected_mime.lower()
        Path(r.output_path).unlink()

    def test_not_base64_fails(self, tmp_path):
        """Case D: 完全不是 base64 -> Base64ImageError"""
        f = tmp_path / "plain.txt"
        f.write_text("hello world, this is plain text content")

        with pytest.raises(Base64ImageError) as exc_info:
            decode_file_to_image(str(f))
        assert "不是有效 base64" in str(exc_info.value) or "转图片失败" in str(exc_info.value)

    def test_file_not_found(self, tmp_path):
        """Case E: 文件不存在 -> FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            decode_file_to_image(str(tmp_path / "no_such_file.txt"))

    def test_real_KEY_exe(self):
        """真实题: Challenge/KEY.exe (Owner 提供)"""
        key_path = Path("Challenge/KEY.exe")
        if not key_path.exists():
            pytest.skip("Challenge/KEY.exe not found")
        r = decode_file_to_image(str(key_path), keep_output=True)
        assert r.source_mime_hint == "image/jpg"
        assert "PNG image" in r.detected_mime
        assert r.raw_size == 2884  # KEY.exe 已知
        # 验证解出的 PNG 是 133x133 RGBA
        img = Image.open(r.output_path)
        assert img.size == (133, 133)
        assert img.mode == "RGBA"
        Path(r.output_path).unlink()

    def test_output_dir(self, tmp_path):
        """output_dir 参数生效"""
        png_bytes = _make_png_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        f = tmp_path / "in.txt"
        f.write_text(b64)

        custom_dir = tmp_path / "custom_out"
        r = decode_file_to_image(str(f), output_dir=str(custom_dir), keep_output=True)
        assert str(custom_dir) in r.output_path
        assert Path(r.output_path).exists()
        Path(r.output_path).unlink()

    def test_keep_output_true(self, tmp_path):
        """keep_output=True -> 文件保留 (caller 自己删)"""
        png_bytes = _make_png_bytes()
        b64 = base64.b64encode(png_bytes).decode()
        f = tmp_path / "in.txt"
        f.write_text(b64)

        r = decode_file_to_image(str(f), keep_output=True)
        assert r.kept_output is True
        assert Path(r.output_path).exists()
        Path(r.output_path).unlink()
