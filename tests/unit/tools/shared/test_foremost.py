"""测试 tools/shared/foremost.py (v0.5-philosophy-rethink 2-bug 修复)

修复 (per Owner 2026-06-20 13:11 实测):
1. -q flag bug: foremost 1.5.7 macOS quiet 模式漏 ZIP 提取
   - 删 -q 让 foremost 走 verbose 模式 (内部 ZIP 中央目录解析正常)
2. 输出路径 bug: 实际输出 outdir/<type>/<file>, 不是 outdir/FOREMOST/<type>/<file>
   - 改用 outdir.rglob("*") 递归扫, 排除 audit.txt
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from automisc.tools.shared.foremost import ForemostAdapter


# ---------- Bug 1: -q flag 必须不在 cmd 里 ----------

def test_foremost_no_q_flag():
    """foremost cmd **不**含 -q (per 1.5.7 macOS quiet 模式漏 ZIP 提取 bug).

    Owner 复现 (2026-06-20 13:11):
      foremost -t all -i X -o Y -q → 1 file (jpg only)
      foremost -t all -i X -o Y    → 2 files (jpg + zip)
    修法: 删 -q flag.
    """
    from unittest.mock import MagicMock

    a = ForemostAdapter()
    # mock _run_subprocess 让其成为 MagicMock (可访问 call_args)
    mock_subprocess = MagicMock(return_value=(0, "", "", 100))
    with patch.object(a, "_run_subprocess", mock_subprocess):
        with patch("automisc.tools.shared.foremost.extract_dir_for") as mock_extract_dir:
            outdir_mock = Path("/tmp/__test_foremost_outdir__")
            mock_extract_dir.return_value = outdir_mock
            outdir_mock.mkdir(parents=True, exist_ok=True)
            try:
                a.run("/tmp/__test_foremost_input__")
            finally:
                if outdir_mock.exists():
                    shutil.rmtree(outdir_mock)

    # 验证 _run_subprocess 调用的 cmd 不含 -q
    cmd_used = mock_subprocess.call_args.args[0]
    assert "-q" not in cmd_used, (
        f"foremost cmd 不该有 -q (1.5.7 macOS quiet 模式漏 ZIP 提取): cmd={cmd_used}"
    )
    # 验证 cmd 含必要的 flag
    assert "-t" in cmd_used and "all" in cmd_used
    assert "-i" in cmd_used
    assert "-o" in cmd_used


# ---------- Bug 2: 输出路径用 rglob 而非 outdir/FOREMOST ----------

def test_foremost_scans_outdir_recursively(tmp_path: Path):
    """foremost 输出结构是 outdir/<type>/<file>, adapter 必须 rglob 扫整个 outdir.

    修复前: adapter 只查 outdir/FOREMOST/ (假设的子目录, 实际不存在).
    修复后: outdir.rglob("*") 递归扫, 排除 audit.txt.
    """
    # 构造 mock 的 foremost 输出目录 (放在隔离路径, adapter 不会 rmtree 它)
    # 注意: adapter 会清空 outdir 后跑 foremost, 我们用 mock _run_subprocess
    # 跳过真实 foremost, 但 outdir 的清理逻辑仍会跑, 所以必须用不同的策略.
    # 策略: mock extract_dir_for 返回一个**新空目录**, 然后 mock _run_subprocess
    #       在那个目录里造 foremost 的输出结构. 但 _run_subprocess 返回值是 (exit, out, err, dur)
    #       不会真写文件. 所以我们必须 mock 整个清理逻辑.
    outdir = tmp_path / "fake_foremost_output"
    outdir.mkdir()

    # 模拟 foremost 输出结构
    (outdir / "jpg").mkdir()
    (outdir / "jpg" / "00000000.jpg").write_bytes(b"\xff\xd8\xff\xe0fake jpg")
    (outdir / "zip").mkdir()
    (outdir / "zip" / "00000038.zip").write_bytes(b"PK\x03\x04fake zip")
    (outdir / "audit.txt").write_text("foremost audit log\n")

    # mock extract_dir_for 返回 outdir + mock _run_subprocess (防 adapter 跑真实 foremost)
    # mock shutil.rmtree 防 adapter 清掉我们 mock 的文件
    a = ForemostAdapter()
    with patch("automisc.tools.shared.foremost.extract_dir_for", return_value=outdir):
        with patch("automisc.tools.shared.foremost.shutil.rmtree"):  # 不删 mock 文件
            with patch.object(a, "_run_subprocess", return_value=(0, "", "foremost output", 100)):
                result = a.run("/tmp/fake_input.jpg")

    # 验证 SP 包含 2 个 extracted files (jpg + zip, 不含 audit.txt)
    extracted_sp = [sp for sp in result.suspicious_points if sp.category == "extracted_files"]
    assert len(extracted_sp) == 1, f"应有 1 个 extracted_files SP, 实际 {len(extracted_sp)}"

    sp = extracted_sp[0]
    # matched_pattern 含 jpg + zip, 不含 audit.txt
    assert "jpg/00000000.jpg" in sp.matched_pattern
    assert "zip/00000038.zip" in sp.matched_pattern
    assert "audit.txt" not in sp.matched_pattern, (
        f"audit.txt 不该出现在 SP: {sp.matched_pattern}"
    )


def test_foremost_excludes_audit_txt_from_sp(tmp_path: Path):
    """outdir.rglob 结果必须过滤掉 audit.txt (per fix)."""
    outdir = tmp_path / "fake_outdir"
    outdir.mkdir()
    # 只有 audit.txt 没其他文件 — SP 应该空
    (outdir / "audit.txt").write_text("audit only")

    a = ForemostAdapter()
    with patch("automisc.tools.shared.foremost.extract_dir_for", return_value=outdir):
        with patch("automisc.tools.shared.foremost.shutil.rmtree"):
            with patch.object(a, "_run_subprocess", return_value=(0, "", "", 50)):
                result = a.run("/tmp/fake_input.jpg")

    assert result.suspicious_points == [], (
        f"只有 audit.txt 时不该有 SP, 实际: {result.suspicious_points}"
    )


def test_foremost_no_extracted_files_no_sp(tmp_path: Path):
    """outdir 里只有 audit.txt (没有 carved 文件) → 不写 SP."""
    outdir = tmp_path / "empty_outdir"
    outdir.mkdir()
    # audit.txt 但没 carved 文件
    (outdir / "audit.txt").write_text("0 FILES EXTRACTED\n")

    a = ForemostAdapter()
    with patch("automisc.tools.shared.foremost.extract_dir_for", return_value=outdir):
        with patch("automisc.tools.shared.foremost.shutil.rmtree"):
            with patch.object(a, "_run_subprocess", return_value=(0, "", "0 files extracted", 50)):
                result = a.run("/tmp/fake_input.jpg")

    assert result.suspicious_points == []  


# ---------- 集成: 真实 123456cry.jpg (Owner 实战样本) ----------

SAMPLE_JPG = "/Users/minzhizhou/Downloads/123456cry.jpg"


@pytest.mark.skipif(
    not os.path.exists(SAMPLE_JPG),
    reason=f"Owner 实战样本不存在: {SAMPLE_JPG}",
)
@pytest.mark.skipif(
    not shutil.which("foremost"),
    reason="foremost not installed",
)
def test_foremost_extracts_zip_from_owner_sample(tmp_path: Path):
    """真实 123456cry.jpg: foremost adapter 应该提取 jpg + zip 两个文件.

    Owner 实战 (2026-06-20 13:11):
      - 命令行 `foremost 123456cry.jpg` 直接跑 → 成功提取 zip + jpg
      - 走 automisc foremost → 0 SP (bug)
      - 修后: 应跟命令行一致, 提取 zip + jpg
    """
    # 备份原 samedir 输出 (万一 owner 已跑过)
    real_outdir = Path(SAMPLE_JPG).parent / (Path(SAMPLE_JPG).stem + "__foremost")
    backup_dir = None
    if real_outdir.exists():
        backup_dir = tmp_path / "backup"
        shutil.move(str(real_outdir), str(backup_dir))

    try:
        a = ForemostAdapter()
        result = a.run(SAMPLE_JPG)

        # exit_code 0
        assert result.exit_code == 0

        # 至少 1 个 extracted_files SP
        extracted_sp = [sp for sp in result.suspicious_points if sp.category == "extracted_files"]
        assert len(extracted_sp) == 1, (
            f"应有 1 个 extracted_files SP, 实际 {len(extracted_sp)}: {result.suspicious_points}"
        )

        sp = extracted_sp[0]
        # 关键断言: SP 应包含 zip 提取 (Owner 报告之前缺这个)
        assert "zip" in sp.matched_pattern.lower(), (
            f"matched_pattern 应含 zip 提取 (per Owner 实测期望):\n{sp.matched_pattern}"
        )
        assert "jpg" in sp.matched_pattern.lower(), (
            f"matched_pattern 应含 jpg 提取:\n{sp.matched_pattern}"
        )

        # severity 4 (跟其他文件头 SP 一致)
        assert sp.severity == 4

        # 实际文件应存在
        assert real_outdir.exists(), f"输出目录应存在: {real_outdir}"
        zip_files = list(real_outdir.rglob("*.zip"))
        assert len(zip_files) >= 1, (
            f"应有至少 1 个 .zip 提取文件, 实际: "
            f"{[str(p) for p in real_outdir.rglob('*')]}"
        )
    finally:
        # 清理输出目录
        if real_outdir.exists():
            shutil.rmtree(real_outdir)
        # 恢复 backup
        if backup_dir and backup_dir.exists():
            shutil.move(str(backup_dir), str(real_outdir))


# ---------- 旧 v0.1 测试保留 ----------

def test_foremost_adapter_is_registered():
    """foremost adapter 应在 registry 里."""
    from automisc.core.registry import get_tool
    a = get_tool("foremost")
    assert isinstance(a, ForemostAdapter)


def test_foremost_default_timeout_high_enough():
    """foremost 大文件雕刻可能很慢, default_timeout 应 ≥ 60s."""
    a = ForemostAdapter()
    assert a.default_timeout >= 60.0, (
        f"default_timeout 应 ≥ 60s (foremost 大文件可能慢): got {a.default_timeout}"
    )
