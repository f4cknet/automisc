"""测试 tools/misc/archive/qemu_img.py + qemu_img_extract.py (v0.5-qemu-img-adapter).

per Owner 2026-06-29 23:23 拍 B 升架构 (实战 v0.5-train-018 flag.vmdk):
- 新建 qemu_img (info 探测, 可挂 auto-run) + qemu_img_extract (convert 写盘, GUI 工具栏)
- 跟 sevenz / sevenz_extract 对偶
- 双注册: get_tool("qemu_img") + get_tool("qemu_img_extract")

覆盖:
- 注册: get_tool("qemu_img") → QemuImgAdapter
- 注册: get_tool("qemu_img_extract") → QemuImgExtractAdapter
- 2 个不互相覆盖
- qemu_img info mock vmdk format → SP vdisk_format sev=3
- qemu_img_extract convert mock 成功 → SP vdisk_extracted sev=5
- qemu_img_extract 清空已有 extract_dir
- qemu_img 用 resolve_tool_binary 找 qemu-img
- qemu_img extract 失败兜底
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from automisc.core.registry import get_tool
from automisc.tools.misc.archive.qemu_img import QemuImgAdapter
from automisc.tools.misc.archive.qemu_img_extract import QemuImgExtractAdapter


# ---------- 是否装 qemu-img (PATH 找, per v0.5-qemu-img-extend-tools NSIS 装) ----------
HAS_QEMU_IMG = shutil.which("qemu-img") is not None
SKIP_REASON = "qemu-img CLI not installed (Owner 跑 install.ps1 装, 或手工 PATH 注册)"


# ---------- 注册 ----------

class TestQemuImgRegistration:
    """per 双注册铁律: qemu_img + qemu_img_extract 必须通过 get_tool() 拿到."""

    def test_qemu_img_is_registered(self):
        a = get_tool("qemu_img")
        assert isinstance(a, QemuImgAdapter)
        assert a.name == "qemu_img"
        assert a.category == "archive"
        # 探测默认 timeout 30s (跟 sevenz 同)
        assert a.default_timeout >= 30.0

    def test_qemu_img_extract_is_registered(self):
        a = get_tool("qemu_img_extract")
        assert isinstance(a, QemuImgExtractAdapter)
        assert a.name == "qemu_img_extract"
        assert a.category == "archive"
        # convert 写盘可能慢, timeout ≥ 60s
        assert a.default_timeout >= 60.0

    def test_qemu_img_and_extract_not_conflict(self):
        """qemu_img (info 探测) 跟 qemu_img_extract (convert 写盘) 必须独立注册, 不互相覆盖."""
        a = get_tool("qemu_img")
        b = get_tool("qemu_img_extract")
        assert a.name == "qemu_img"
        assert b.name == "qemu_img_extract"
        assert type(a) is not type(b)


# ---------- qemu_img info 探测 (mock subprocess, 跨平台) ----------

class TestQemuImgInfo:
    """qemu_img info 探测: mock _run_subprocess 验证 SP 写入."""

    def test_qemu_img_info_vmdk_format_suspicious_point(self, monkeypatch):
        """mock qemu-img info 输出含 'file format: vmdk' → SP vdisk_format sev=3."""
        a = QemuImgAdapter()
        mock_output = (
            "image: flag.vmdk\n"
            "file format: vmdk\n"
            "virtual size: 3.0G (3145728000 bytes)\n"
            "disk size: 3.0M\n"
        )
        # mock _run_subprocess
        monkeypatch.setattr(
            a, "_run_subprocess",
            lambda cmd, timeout=None: (0, mock_output, "", 100),
        )

        result = a.run("/fake/flag.vmdk")
        assert result.exit_code == 0
        # 至少 1 条 SP vdisk_format
        fmt_sps = [sp for sp in result.suspicious_points if sp.category == "vdisk_format"]
        assert len(fmt_sps) == 1, f"应有 1 条 vdisk_format SP, 实际 {len(fmt_sps)}"
        assert "vmdk" in fmt_sps[0].matched_pattern
        assert fmt_sps[0].severity == 3
        # suggested_action 引用 GUI 工具栏
        assert "qemu-img 转换" in fmt_sps[0].suggested_action or "工具栏" in fmt_sps[0].suggested_action

    def test_qemu_img_info_unsupported_format_returns_toolresult(self, monkeypatch):
        """qemu-img info 不支持的格式 → exit 1, 不 panic, 返回 ToolResult."""
        a = QemuImgAdapter()
        monkeypatch.setattr(
            a, "_run_subprocess",
            lambda cmd, timeout=None: (
                1, "",
                "qemu-img: Could not open '/fake/random.bin': Failed to open file\n",
                50,
            ),
        )

        result = a.run("/fake/random.bin")
        assert result.exit_code == 1
        # exit 1 应该有 stderr
        assert "Could not open" in result.stderr
        # 不一定有 vdisk_format SP (output 没有 "file format:" 关键词)
        fmt_sps = [sp for sp in result.suspicious_points if sp.category == "vdisk_format"]
        assert len(fmt_sps) == 0

    def test_qemu_img_uses_resolve_tool_binary(self, monkeypatch):
        """qemu_img 走 resolve_tool_binary('qemu-img') 找 binary (per v0.5-platform-extend-tools 模式)."""
        from automisc.tools import paths as paths_mod

        fake_qemu_path = r"C:\Program Files\qemu\qemu-img.exe"
        monkeypatch.setattr(paths_mod, "resolve_tool_binary", lambda name: fake_qemu_path if name == "qemu-img" else None)

        captured = {}

        def mock_subprocess(cmd, timeout=None):
            captured["cmd"] = cmd
            return (0, "file format: vmdk\n", "", 100)

        a = QemuImgAdapter()
        monkeypatch.setattr(a, "_run_subprocess", mock_subprocess)
        a.run("/fake/flag.vmdk")
        # cmd 头应是 resolve_tool_binary 返回的 path
        assert captured["cmd"][0] == fake_qemu_path


# ---------- qemu_img_extract convert 写盘 (mock subprocess, 跨平台) ----------

class TestQemuImgExtractConvert:
    """qemu_img_extract convert 写盘: mock _run_subprocess + 写 raw 文件, 验证 SP + 路径."""

    def test_qemu_img_extract_vmdk_to_raw_suspicious_point(self, monkeypatch, tmp_path):
        """mock qemu-img convert 成功 + 写 .raw 文件 → SP vdisk_extracted sev=5."""
        # 准备输入文件
        input_vmdk = tmp_path / "flag.vmdk"
        input_vmdk.write_bytes(b"fake vmdk content\n")

        # 写 extract_dir
        from automisc.core.utils.output_path import extract_dir_for
        expected_dir = extract_dir_for(str(input_vmdk), purpose="qemu_img_raw")
        expected_raw = expected_dir / "flag.raw"

        def mock_subprocess(cmd, timeout=None):
            # cmd 应该是 [qemu-img, convert, -f, vmdk, -O, raw, <input>, <output>]
            assert cmd[0].endswith("qemu-img") or cmd[0] == "qemu-img"
            assert cmd[1] == "convert"
            assert cmd[2] == "-f"
            assert cmd[3] == "vmdk"
            assert cmd[4] == "-O"
            assert cmd[5] == "raw"
            # 写 .raw 文件模拟 qemu-img 成功
            expected_dir.mkdir(parents=True, exist_ok=True)
            expected_raw.write_bytes(b"fake raw vdisk\n" * 100)
            return (0, "", "", 100)

        b = QemuImgExtractAdapter()
        monkeypatch.setattr(b, "_run_subprocess", mock_subprocess)

        result = b.run(str(input_vmdk))
        assert result.exit_code == 0
        # raw 写成功
        assert expected_raw.exists()
        # SP vdisk_extracted sev=5
        ext_sps = [sp for sp in result.suspicious_points if sp.category == "vdisk_extracted"]
        assert len(ext_sps) == 1, f"应有 1 条 vdisk_extracted SP, 实际 {len(ext_sps)}"
        assert ext_sps[0].severity == 5
        assert "raw" in ext_sps[0].matched_pattern.lower()
        # metadata.written_files
        assert "written_files" in result.metadata
        assert result.metadata["written_files"][0]["path"] == str(expected_raw)

    def test_qemu_img_extract_cleans_existing_dir(self, monkeypatch, tmp_path):
        """extract_dir 已有旧内容 → 清空再写 (per v0.5-output-samedir 模式)."""
        from automisc.core.utils.output_path import extract_dir_for

        input_vmdk = tmp_path / "flag.vmdk"
        input_vmdk.write_bytes(b"fake vmdk\n")
        expected_dir = extract_dir_for(str(input_vmdk), purpose="qemu_img_raw")
        # 预先创建 dir 含旧文件
        expected_dir.mkdir(parents=True, exist_ok=True)
        old_file = expected_dir / "old.txt"
        old_file.write_text("old content")

        def mock_subprocess(cmd, timeout=None):
            expected_dir.mkdir(parents=True, exist_ok=True)
            (expected_dir / "flag.raw").write_bytes(b"new content")
            return (0, "", "", 50)

        b = QemuImgExtractAdapter()
        monkeypatch.setattr(b, "_run_subprocess", mock_subprocess)
        result = b.run(str(input_vmdk))
        # 旧文件应被清
        assert not old_file.exists()
        assert (expected_dir / "flag.raw").exists()

    def test_qemu_img_extract_handles_convert_failure(self, monkeypatch, tmp_path):
        """qemu-img convert 失败 (exit 1) → 不写 raw, 不 panic, SP archive_error (sev=3)."""
        input_vmdk = tmp_path / "flag.vmdk"
        input_vmdk.write_bytes(b"fake vmdk\n")

        def mock_subprocess(cmd, timeout=None):
            return (1, "", "qemu-img: Could not open file\n", 50)

        b = QemuImgExtractAdapter()
        monkeypatch.setattr(b, "_run_subprocess", mock_subprocess)
        result = b.run(str(input_vmdk))
        assert result.exit_code == 1
        # 没 vdisk_extracted SP (没成功)
        ext_sps = [sp for sp in result.suspicious_points if sp.category == "vdisk_extracted"]
        assert len(ext_sps) == 0


# ---------- e2e: 真实 qemu-img CLI (前提: 已装, 跨平台 skip) ----------

@pytest.mark.skipif(not HAS_QEMU_IMG, reason=SKIP_REASON)
class TestQemuImgE2E:
    """e2e: Owner 跑 install.ps1 装 qemu-img 后, 真实 CLI 跑通.

    实测: qemu-img info <任意文件> 应该 exit 0 或 exit 1, 不 panic.
    实战 1 道同类 (v0.5-train-018 flag.vmdk) → 真实 flag.vmdk Owner 实测通过.
    """

    def test_qemu_img_info_real_binary_does_not_panic(self, tmp_path):
        """真实 qemu-img info 在 fake file 上 exit 1, 不 panic."""
        a = QemuImgAdapter()
        fake_file = tmp_path / "fake.txt"
        fake_file.write_text("dummy")
        result = a.run(str(fake_file))
        # qemu-img info 在非虚拟磁盘文件上 exit 1 (per v0.5-train-018 实测)
        assert result.exit_code in (0, 1)  # 0=真虚拟磁盘, 1=不识别
        assert result.stderr or result.stdout  # 有 output 不空
