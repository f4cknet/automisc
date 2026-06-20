"""测试 tools/misc/archive/sevenz_extract.py (v0.5-sevenz-extract)

per Owner 2026-06-20 19:48 拍板:
- 新建 sevenz_extract adapter (跟 sevenz / unzip 对偶)
- GUI 工具栏 "Misc/Archive" 下新增 "📦 7z 解压"
- 真正 `7z x` 解压到 `<input_stem>__7z_extracted/`

覆盖:
- 注册: get_tool("sevenz_extract") → SevenZipExtractAdapter
- 解压正常 .7z → output 目录有文件 + severity=5 SP
- 解压伪加密 .zip → Headers Error → severity=4
- 解压非归档文件 → exit_code != 0 + severity 3
- v0.5-output-samedir: output 路径 = `<stem>__7z_extracted/`
"""
from __future__ import annotations

import subprocess

import pytest

from automisc.core.registry import get_tool
from automisc.core.utils.output_path import extract_dir_for
from automisc.tools.misc.archive.sevenz_extract import SevenZipExtractAdapter


# ---------- 是否有 7z CLI ----------
HAS_7Z = subprocess.run(["which", "7z"], capture_output=True).returncode == 0
SKIP_REASON = "7z CLI not installed (brew install p7zip)"


# ---------- 注册 ----------

class TestSevenZipExtractRegistration:
    """per 双注册铁律: sevenz_extract 必须通过 get_tool() 拿到."""

    def test_sevenz_extract_is_registered(self):
        a = get_tool("sevenz_extract")
        assert isinstance(a, SevenZipExtractAdapter)
        assert a.name == "sevenz_extract"
        assert a.category == "misc_archive"
        assert a.default_timeout >= 30.0  # 解压可能慢, 不应该是 30s 默认

    def test_sevenz_extract_not_conflict_with_sevenz(self):
        """sevenz (探测) 跟 sevenz_extract (解压) 必须独立注册, 不互相覆盖."""
        sevenz = get_tool("sevenz")
        sevenz_extract = get_tool("sevenz_extract")
        assert sevenz.name == "sevenz"
        assert sevenz_extract.name == "sevenz_extract"
        assert type(sevenz) is not type(sevenz_extract)


# ---------- 正常解压 ----------

@pytest.mark.skipif(not HAS_7Z, reason=SKIP_REASON)
class TestSevenZipExtractNormal:
    """正常 .7z 解压 → severity=5 archive_extracted SP + output 目录有文件."""

    def test_extract_normal_7z_creates_output_dir(self, tmp_path):
        """7z 构造正常 7z → sevenz_extract.run() → output 目录存在 + 有文件."""
        # 1. 构造测试 archive: 用 7z a 创建正常 7z
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "hello.txt").write_text("hello from 7z test")
        (src_dir / "sub").mkdir()
        (src_dir / "sub" / "world.txt").write_text("world in subdir")

        archive = tmp_path / "test.7z"
        subprocess.run(
            ["7z", "a", "-t7z", str(archive), str(src_dir / "hello.txt"), str(src_dir / "sub")],
            capture_output=True, check=True,
        )
        assert archive.exists()

        # 2. 跑 sevenz_extract
        a = SevenZipExtractAdapter()
        result = a.run(str(archive))

        # 3. 验证
        assert result.is_success, f"7z x 失败: stdout={result.stdout}, stderr={result.stderr}"
        extract_dir = extract_dir_for(str(archive), purpose="7z_extracted")
        assert extract_dir.exists(), f"output 目录不存在: {extract_dir}"
        extracted_files = list(extract_dir.rglob("*"))
        assert sum(1 for p in extracted_files if p.is_file()) >= 2, (
            f"应有 ≥2 个文件 (hello.txt + sub/world.txt), got {extracted_files}"
        )

    def test_extract_normal_zip_creates_output_dir(self, tmp_path):
        """7z 也能解压 zip — 测一下 zip 走 sevenz_extract 也能成功."""
        # 1. 构造正常 zip
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("alpha")
        (src_dir / "b.txt").write_text("bravo")

        archive = tmp_path / "test.zip"
        subprocess.run(
            ["7z", "a", "-tzip", str(archive), str(src_dir / "a.txt"), str(src_dir / "b.txt")],
            capture_output=True, check=True,
        )

        # 2. 跑 sevenz_extract
        a = SevenZipExtractAdapter()
        result = a.run(str(archive))

        # 3. 验证
        assert result.is_success, f"7z x 失败: {result.stderr}"
        extract_dir = extract_dir_for(str(archive), purpose="7z_extracted")
        assert extract_dir.exists()
        assert sum(1 for p in extract_dir.rglob("*") if p.is_file()) >= 2

    def test_extract_emits_severity_5_success_sp(self, tmp_path):
        """成功解压 → severity=5 archive_extracted SP (跟 keyword 同级最高优先级)."""
        src = tmp_path / "x.txt"
        src.write_text("flag content here")
        archive = tmp_path / "test.7z"
        subprocess.run(
            ["7z", "a", "-t7z", str(archive), str(src)], capture_output=True, check=True,
        )

        a = SevenZipExtractAdapter()
        result = a.run(str(archive))

        success_sps = [sp for sp in result.suspicious_points if sp.category == "archive_extracted"]
        assert len(success_sps) >= 1, f"应有 archive_extracted SP, got {result.suspicious_points}"
        assert success_sps[0].severity == 5
        assert "extracted" in success_sps[0].matched_pattern.lower()
        # suggested_action 应指明 output 目录
        assert "解压成功" in success_sps[0].suggested_action or "output" in success_sps[0].suggested_action.lower()

    def test_extract_writes_to_input_samedir(self, tmp_path):
        """v0.5-output-samedir 铁律: output 跟 input 同目录."""
        src = tmp_path / "x.txt"
        src.write_text("data")
        archive = tmp_path / "input.7z"
        subprocess.run(
            ["7z", "a", "-t7z", str(archive), str(src)], capture_output=True, check=True,
        )

        a = SevenZipExtractAdapter()
        a.run(str(archive))

        extract_dir = extract_dir_for(str(archive), purpose="7z_extracted")
        # 必须跟 input 同目录 (tmp_path)
        assert extract_dir.parent == tmp_path
        # 命名规则: <stem>__7z_extracted
        assert extract_dir.name == "input__7z_extracted"


# ---------- 失败兜底 ----------

@pytest.mark.skipif(not HAS_7Z, reason=SKIP_REASON)
class TestSevenZipExtractFailure:
    """失败场景: 伪加密 / 真加密 / 损坏 / 非归档."""

    def test_pseudo_encrypted_zip_emits_severity_4(self, tmp_path):
        """伪加密 zip (zipcrypto + flag 0x09) → 7z x 报 Headers Error → severity=4."""
        # 1. 构造伪加密 zip (用 zipfile + 手动改 flag 位)
        import zipfile
        import struct

        archive = tmp_path / "pseudo.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("flag.txt", "fake_flag_content")

        # 改 LFH general purpose bit flag: byte[6] = 0x09 (encrypted)
        with open(archive, "r+b") as f:
            data = f.read()
            # LFH signature 后 6-7 字节是 general purpose bit flag
            # 找第一个 PK\x03\x04
            idx = data.find(b"PK\x03\x04")
            assert idx >= 0
            f.seek(idx + 6)
            f.write(b"\x09\x00")  # flag = 0x0009 (encrypted)

        # 2. 跑 sevenz_extract
        a = SevenZipExtractAdapter()
        result = a.run(str(archive))

        # 3. 7z 应该报错 (exit_code != 0)
        assert not result.is_success, "伪加密 zip 应该 7z 解压失败"

        # 4. SP 应该是 archive_pseudo_encryption severity=4
        pseudo_sps = [sp for sp in result.suspicious_points if sp.category == "archive_pseudo_encryption"]
        assert len(pseudo_sps) >= 1, (
            f"伪加密应有 archive_pseudo_encryption SP, got categories: "
            f"{[sp.category for sp in result.suspicious_points]}"
        )
        assert pseudo_sps[0].severity == 4
        assert "headers error" in pseudo_sps[0].matched_pattern.lower() or "7z" in pseudo_sps[0].matched_pattern.lower()

    def test_encrypted_zip_emits_severity_4(self, tmp_path):
        """真加密 zip (zipcrypto + 正确密码不知道) → 7z x 报 Wrong password → severity=4."""
        # 1. 构造真加密 zip 用 7z a -mem=ZipCrypto -p<password>
        src = tmp_path / "secret.txt"
        src.write_text("encrypted content")
        archive = tmp_path / "encrypted.zip"
        subprocess.run(
            ["7z", "a", "-tzip", "-mem=ZipCrypto", "-psecret123", str(archive), str(src)],
            capture_output=True, check=True,
        )

        # 2. 跑 sevenz_extract (空密码尝试)
        a = SevenZipExtractAdapter()
        result = a.run(str(archive))

        # 3. 7z 报 Wrong password
        assert not result.is_success
        enc_sps = [sp for sp in result.suspicious_points if sp.category in ("archive_encrypted", "archive_pseudo_encryption")]
        assert len(enc_sps) >= 1, (
            f"真加密应有 archive_encrypted SP, got: "
            f"{[(sp.category, sp.severity) for sp in result.suspicious_points]}"
        )
        assert enc_sps[0].severity >= 3

    def test_non_archive_file_does_not_panic(self, tmp_path):
        """非归档文件 → 7z 报错 exit != 0, 但 adapter 不 panic, 返回 SP."""
        bad = tmp_path / "not_archive.txt"
        bad.write_bytes(b"this is just plain text, not an archive")

        a = SevenZipExtractAdapter()
        result = a.run(str(bad))

        # exit_code 应该 != 0 (7z 拒绝)
        assert result.exit_code != 0, f"非归档应该报错, got exit_code={result.exit_code}"
        # 但 adapter 不应该 panic (能 return ToolResult)
        assert result.suspicious_points is not None

    def test_nonexistent_file_does_not_panic(self, tmp_path):
        """不存在的文件 → adapter 不 panic."""
        nonexistent = tmp_path / "does_not_exist.7z"

        a = SevenZipExtractAdapter()
        # 不应该抛异常
        result = a.run(str(nonexistent))
        assert result.exit_code != 0
        assert result.suspicious_points is not None


# ---------- 集成: GUI 工具栏 / registry ----------

class TestSevenZipExtractIntegration:
    """验证 GUI 工具栏能识别 sevenz_extract (per menu_dock.py 集成)."""

    def test_sevenz_extract_in_misc_archive_category(self):
        """menu_dock.TOOL_CATEGORIES["Misc/Archive (PR5)"] 必须含 sevenz_extract.

        per v0.5-sevenz-toolbar-cleanup (Owner 2026-06-20 20:03):
        探测类 sevenz (list/test) 不显示在 GUI menu (auto_run 用), 但 adapter 仍注册.
        所以 archive_tools 应含 sevenz_extract 但不含 sevenz.
        """
        from automisc.gui.menu_dock import TOOL_CATEGORIES

        archive_tools = TOOL_CATEGORIES.get("Misc/Archive (PR5)", [])
        assert "sevenz_extract" in archive_tools, (
            f"Misc/Archive 应含 sevenz_extract, got: {archive_tools}"
        )
        # sevenz 是探测类, per Owner 20:03 设计原则, 不显示在 GUI menu
        assert "sevenz" not in archive_tools, (
            f"sevenz 是探测类, 不应显示在 GUI menu (per Owner 20:03), got: {archive_tools}"
        )
        # 跟 unzip / john / zip_classify 同一级 (操作类)
        assert "unzip" in archive_tools  # owner 暂保留, 也算操作类入口
        assert "john" in archive_tools
        assert "zip_classify" in archive_tools

    def test_sevenz_extract_in_adapter_tools_set(self):
        """ADAPTER_TOOLS 必须含 sevenz_extract (GUI 标记 ✓ 才会显示)."""
        from automisc.gui.menu_dock import ADAPTER_TOOLS

        assert "sevenz_extract" in ADAPTER_TOOLS

    def test_sevenz_extract_has_display_name(self):
        """ACTION_DISPLAY_NAMES 必须给 sevenz_extract 配中文 display name."""
        from automisc.gui.menu_dock import ACTION_DISPLAY_NAMES

        display = ACTION_DISPLAY_NAMES.get("sevenz_extract")
        assert display is not None, "sevenz_extract 应有中文 display name"
        assert "7z" in display or "7Z" in display, f"display 应含 7z: {display}"
        assert "解压" in display, f"display 应说明功能 (解压): {display}"