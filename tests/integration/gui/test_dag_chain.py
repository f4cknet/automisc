"""e2e: zip 链 + 嵌套 zip 提取 (v0.5-zip-pseudo-per-entry-classify).

依赖: tests/fixtures/sample_archive_pseudo_real.zip (177 bytes, 伪加密 zip)
v0.5-philosophy-rethink: 删 TestBinwalkTriggerE2E (auto_run 不再触发链)
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from automisc.core.chains import (
    build_zip_chain_dag,
    build_zip_chain_with_bruteforce,
    find_embedded_archives,
)
from automisc.core.orchestrator import CoreOrchestrator
from automisc.gui.main_window import MainWindow


@pytest.fixture
def pseudo_zip() -> Path:
    return Path("tests/fixtures/sample_archive_pseudo_real.zip")


class TestChainHelpers:
    def test_find_embedded_archives_zip(self):
        text = "12345: ZIP archive, bad password\n67890: PNG image"
        archives = find_embedded_archives(text)
        assert any("ZIP" in a for a in archives)
        assert not any("PNG" in a for a in archives)

    def test_find_embedded_archives_7z(self):
        text = "0: 7z archive, encrypted"
        archives = find_embedded_archives(text)
        assert len(archives) == 1
        assert "7z" in archives[0]

    def test_find_embedded_archives_empty(self):
        assert find_embedded_archives("nothing here") == []


class TestZipChainE2E:
    def test_chain_runs_on_pseudo_zip(self, pseudo_zip, tmp_path):
        """伪加密 zip → try_unzip fail → fix_pseudo success → 终止."""
        # 用 tmp_path 副本避免污染 fixture
        import shutil
        copy_zip = tmp_path / "pseudo.zip"
        shutil.copy2(pseudo_zip, copy_zip)

        dag = build_zip_chain_dag()
        ctx = dag.execute({"file_path": str(copy_zip)})
        log = ctx["__log__"]
        assert len(log) == 2
        assert log[0]["node"] == "try_unzip" and log[0]["success"] is False
        assert log[1]["node"] == "fix_pseudo_encryption" and log[1]["success"] is True
        # 验证修复后 zip 可解压
        import zipfile
        with zipfile.ZipFile(copy_zip) as zf:
            data = zf.read("flag{pseudo}.txt")
            assert b"pseudo_zip_test_xyz" in data
        # 清理 backup
        backup = copy_zip.with_suffix(copy_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()

    def test_chain_does_not_loop(self, pseudo_zip, tmp_path):
        """DAG max_steps 防死循环（fix.on_success = None 不重试）."""
        import shutil
        copy_zip = tmp_path / "pseudo.zip"
        shutil.copy2(pseudo_zip, copy_zip)

        dag = build_zip_chain_dag()
        ctx = dag.execute({"file_path": str(copy_zip)})
        # 仅 2 step (try_unzip + fix_pseudo)
        assert len(ctx["__log__"]) == 2
        backup = copy_zip.with_suffix(copy_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()

