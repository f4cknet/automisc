"""测试 tools/misc/archive/zip_classify.py (v0.5-zip-verdict-pool)

覆盖:
- verdict SP 构造 (4 种情形: 伪加密/真加密/混合/clear)
- per-entry 分类 (复用 ed5a00c 实现)
- clear 自动解压 (per Owner verdict_silent 拍板)
- auto_run pool 注册
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.auto_runner import (
    FIND_SUSPICIOUS_ARCHIVE_TOOLS,
    pick_suspicious_pool,
)
from automisc.tools.misc.archive.zip_classify import ZipClassifyAdapter


# ---------- adapter 注册 ----------

def test_zip_classify_is_registered():
    """zip_classify adapter 必须注册 (pool 引用)."""
    from automisc.core.registry import get_tool
    a = get_tool("zip_classify")
    assert isinstance(a, ZipClassifyAdapter)
    assert a.name == "zip_classify"
    assert a.category == "archive"


# ---------- pool 路由 ----------

def test_archive_pool_includes_zip_classify():
    """v0.5-zip-verdict-pool (Owner 2026-06-20 14:13): zip 拖入后 verdict 必须出现在 auto_run."""
    pool, tools = pick_suspicious_pool("/tmp/x.zip")
    assert pool == "archive"
    assert "zip_classify" in tools, (
        f"archive pool 必须含 zip_classify (per Owner 实测需求): {tools}"
    )
    assert tools == FIND_SUSPICIOUS_ARCHIVE_TOOLS


# ---------- verdict SP 4 种情形 ----------

class TestVerdictClassification:
    """4 种 verdict 情形: 伪/真/混合/clear."""

    def _build_zip(self, tmp_path: Path, name: str, *, encrypted: bool, password: bool = False) -> Path:
        """构造测试 ZIP, 1 entry.

        encrypted=True 且 password=False → 伪加密 (flag bit 0 = 1 但内容明文)
        encrypted=True 且 password=True  → 真加密 (内容加密)
        encrypted=False → clear (无加密)
        """
        zf_path = tmp_path / name
        with zipfile.ZipFile(zf_path, "w") as zf:
            # zipfile 写时: 没法直接写伪加密 (它默认写真的或 clear)
            # 我们用 _classify_zip_entries 验证:
            # - clear: 不设 flag bit 0
            # - pseudo: 设 flag bit 0 但内容明文 (手工写)
            # - real: 设 flag bit 0 + 真加密内容
            if not encrypted:
                # clear
                zf.writestr("test.txt", "hello clear content")
            elif password:
                # 真加密 (zipfile 标准支持)
                zf.writestr("test.txt", "secret content", pwd=b"test123")
            else:
                # 伪加密: 手工写 zip, 设 flag bit 0 但内容明文
                import struct
                # 先写一个 minimal zip + 手工改 flag bit
                # 简单做法: 用 zipfile 写 clear, 然后手工 patch flag_bits
                zf.writestr("test.txt", "secret-looking but plaintext")
                # 关闭后, 读 + 改 flag_bits
                # (实际不在这里做, 改用更简单的 mock 策略)
        return zf_path

    def test_pseudo_only_verdict(self, tmp_path: Path):
        """纯伪加密 (1 pseudo + 0 real + 0 clear) → severity 5 + Fix 建议."""
        # 构造伪加密 ZIP: 手工写 (flag_bits bit 0 = 1 但内容明文)
        zf_path = tmp_path / "pseudo_only.zip"
        self._write_pseudo_zip(zf_path, [("test.txt", "plaintext secret")])

        a = ZipClassifyAdapter()
        result = a.run(str(zf_path))

        verdict_sp = [sp for sp in result.suspicious_points if sp.category == "zip_encryption_verdict"]
        assert len(verdict_sp) == 1
        sp = verdict_sp[0]
        assert sp.severity == 5
        assert "纯伪加密" in sp.matched_pattern
        assert "Fix Zip 伪加密" in sp.suggested_action

    def test_real_only_verdict(self, tmp_path: Path, monkeypatch):
        """纯真加密 (0 pseudo + 1 real + 0 clear) → severity 4 + bruteforce 建议.

        Python 3.14 zipfile.writestr 不支持 pwd, 用 mock _classify_zip_entries 模拟.
        """
        # mock _classify_zip_entries 在 adapter 引用的模块里
        from automisc.tools.misc.archive import zip_classify as zc_adapt_mod

        def fake_classify(zip_path):
            return {
                "pseudo": {},
                "real": {"secret.txt": (0, 100)},
                "clear": {},
            }

        monkeypatch.setattr(zc_adapt_mod, "_classify_zip_entries", fake_classify)

        # 写一个 valid ZIP (但 classify 会被 mock)
        zf_path = tmp_path / "real_only.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("secret.txt", "encrypted content")

        a = ZipClassifyAdapter()
        result = a.run(str(zf_path))

        verdict_sp = [sp for sp in result.suspicious_points if sp.category == "zip_encryption_verdict"]
        assert len(verdict_sp) == 1
        sp = verdict_sp[0]
        assert sp.severity == 4  # 真加密 (severity 4, 不是 5)
        assert "纯真加密" in sp.matched_pattern
        assert "暴力破解" in sp.suggested_action

    def test_clear_only_verdict(self, tmp_path: Path):
        """纯 clear (0 pseudo + 0 real + 1 clear) → severity 2 + 直接 unzip."""
        zf_path = tmp_path / "clear_only.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("readme.txt", "no encryption")

        a = ZipClassifyAdapter()
        result = a.run(str(zf_path))

        verdict_sp = [sp for sp in result.suspicious_points if sp.category == "zip_encryption_verdict"]
        assert len(verdict_sp) == 1
        sp = verdict_sp[0]
        assert sp.severity == 2
        assert "无加密" in sp.matched_pattern
        assert "直接解压" in sp.suggested_action

    def test_mixed_verdict_severity_5(self, tmp_path: Path, monkeypatch):
        """混合 (1 pseudo + 1 real) → severity 5 (最严重) + 双建议.

        Python 3.14 zipfile.writestr 不支持 pwd, 用 mock _classify_zip_entries.
        """
        from automisc.tools.misc.archive import zip_classify as zc_adapt_mod

        def fake_classify(zip_path):
            return {
                "pseudo": {"pseudo_entry.txt": (0, 100)},
                "real": {"real_entry.txt": (200, 200)},
                "clear": {},
            }

        monkeypatch.setattr(zc_adapt_mod, "_classify_zip_entries", fake_classify)

        zf_path = tmp_path / "mixed.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("a.txt", "x")

        a = ZipClassifyAdapter()
        result = a.run(str(zf_path))

        verdict_sp = [sp for sp in result.suspicious_points if sp.category == "zip_encryption_verdict"]
        assert len(verdict_sp) == 1
        sp = verdict_sp[0]
        assert sp.severity == 5
        assert "混合" in sp.matched_pattern
        assert "Fix Zip 伪加密" in sp.suggested_action
        assert "暴力破解" in sp.suggested_action

    def test_clear_auto_extract(self, tmp_path: Path):
        """clear entry 自动解压到 <stem>_clear_unzipped/ (per Owner verdict_silent)."""
        zf_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("readme.txt", "no encryption")

        a = ZipClassifyAdapter()
        result = a.run(str(zf_path))

        # metadata 应含 clear_extract_dir
        assert result.metadata["clear_extract_dir"] is not None
        extract_dir = Path(result.metadata["clear_extract_dir"])
        assert extract_dir.exists()
        # 提取的文件应存在
        assert len(result.metadata["clear_extracted_files"]) == 1
        extracted = Path(result.metadata["clear_extracted_files"][0])
        assert extracted.exists()
        assert extracted.read_text() == "no encryption"

    def test_invalid_zip_no_sp(self, tmp_path: Path):
        """非 ZIP 文件 → 不写 SP, exit_code != 0."""
        fake = tmp_path / "not_zip.txt"
        fake.write_text("not a zip")

        a = ZipClassifyAdapter()
        result = a.run(str(fake))

        assert result.exit_code != 0
        assert result.suspicious_points == []
        assert "not a valid zip" in result.stderr.lower()

    def test_missing_file_no_sp(self, tmp_path: Path):
        """文件不存在 → 不写 SP, exit_code != 0."""
        a = ZipClassifyAdapter()
        result = a.run(str(tmp_path / "nonexistent.zip"))

        assert result.exit_code != 0
        assert result.suspicious_points == []

    # ---------- helper methods ----------

    @staticmethod
    def _write_pseudo_zip(zf_path: Path, entries: list[tuple[str, str]]) -> None:
        """写一个伪加密 ZIP (flag bit 0 = 1 但内容明文).

        步骤:
        1. zipfile 写正常 ZIP
        2. 读 binary, 找到 Local File Header (PK\x03\x04) 的 flag_bits, 设 bit 0
        3. 写回
        """
        import struct
        with zipfile.ZipFile(zf_path, "w") as zf:
            for name, content in entries:
                zf.writestr(name, content)
        # Patch flag bits (设 bit 0 = encrypted flag, 但内容明文 → 伪加密)
        data = bytearray(zf_path.read_bytes())
        offset = 0
        while offset < len(data) - 4:
            if data[offset:offset+4] == b"PK\x03\x04":
                # Local File Header: flag_bits at offset+6 (2 bytes, little-endian)
                flag_bits = struct.unpack_from("<H", data, offset + 6)[0]
                flag_bits |= 0x1  # 设 encrypted flag bit
                struct.pack_into("<H", data, offset + 6, flag_bits)
                # 跳到 file data 后找下一个 header
                comp_size = struct.unpack_from("<I", data, offset + 18)[0]
                fname_len = struct.unpack_from("<H", data, offset + 26)[0]
                extra_len = struct.unpack_from("<H", data, offset + 28)[0]
                offset += 30 + fname_len + extra_len + comp_size
            else:
                break
        zf_path.write_bytes(bytes(data))

    @staticmethod
    def _patch_to_pseudo(zf_path: Path, entry_name: str) -> None:
        """把指定 entry 改成伪加密 (flag bit 0 = 1, 内容保持明文)."""
        import struct
        data = bytearray(zf_path.read_bytes())
        offset = 0
        while offset < len(data) - 30:
            if data[offset:offset+4] == b"PK\x03\x04":
                fname_len = struct.unpack_from("<H", data, offset + 26)[0]
                extra_len = struct.unpack_from("<H", data, offset + 28)[0]
                fname = data[offset+30:offset+30+fname_len].decode("utf-8", errors="replace")
                if fname == entry_name:
                    flag_bits = struct.unpack_from("<H", data, offset + 6)[0]
                    flag_bits |= 0x1
                    struct.pack_into("<H", data, offset + 6, flag_bits)
                    break
                comp_size = struct.unpack_from("<I", data, offset + 18)[0]
                offset += 30 + fname_len + extra_len + comp_size
            else:
                break
        zf_path.write_bytes(bytes(data))


# ---------- 集成: 真实 owner 实战样本 ----------

OWNER_SAMPLE = "/Users/minzhizhou/Downloads/123456cry__foremost/zip/00000038.zip"


@pytest.mark.skipif(
    not os.path.exists(OWNER_SAMPLE),
    reason=f"owner 实战样本不存在: {OWNER_SAMPLE}",
)
def test_owner_sample_zip_classify():
    """owner 实战样本 00000038.zip (per v0.5-zip-verdict-pool 实测).

    期望:
    - 1 pseudo (asd/good-已合并.jpg) + 0 real + 2 clear (asd/ + asd/qwe.zip)
    - verdict = "纯伪加密: 1 entries 可修复 (无密码)" (severity 5)
    - clear entry asd/qwe.zip 自动解压
    - suggested_action = "GUI Fix Zip 伪加密"
    """
    a = ZipClassifyAdapter()
    result = a.run(OWNER_SAMPLE)

    # Verdict SP
    verdict_sp = [sp for sp in result.suspicious_points if sp.category == "zip_encryption_verdict"]
    assert len(verdict_sp) == 1
    sp = verdict_sp[0]
    assert sp.severity == 5

    # per-entry 计数
    assert result.metadata["pseudo_count"] == 1
    assert result.metadata["real_count"] == 0
    assert result.metadata["clear_count"] == 2

    # 伪加密 entry 名字
    assert "asd/good-已合并.jpg" in result.metadata["pseudo_entries"]

    # clear 自动解压
    assert result.metadata["clear_extract_dir"] is not None
    assert len(result.metadata["clear_extracted_files"]) == 1
    assert "qwe.zip" in result.metadata["clear_extracted_files"][0]

    # suggested_action 指向 GUI Fix
    assert "Fix Zip 伪加密" in sp.suggested_action
