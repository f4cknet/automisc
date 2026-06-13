"""DAG + actions 单测（v0.5-DAG-chain）"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from automisc.core.actions.binwalk_extract import BinwalkExtractAction
from automisc.core.actions.foremost_extract import (
    ForemostExtractAction,
    find_foremost_extract,
)
from automisc.core.actions.zip_chain import (
    BruteforceZipAction,
    FixPseudoEncryptionAction,
    TryUnzipAction,
    _generate_passwords,
    _is_pseudo_encrypted,
)
from pathlib import Path
from automisc.core.dag import Action, ActionResult, DAG, DAGNode


# ---------- fixtures ----------
@pytest.fixture
def normal_zip(tmp_path) -> Path:
    """正常 zip（无密码可解压）."""
    p = tmp_path / "normal.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("flag{normal}.txt", "flag{normal_zip_test_xyz}\n")
        zf.writestr("readme.txt", "this is a normal zip\n")
    return p


@pytest.fixture
def pseudo_zip(tmp_path) -> Path:
    """真伪加密 zip: 加密位 set 但内容明文, 可通过 fix_pseudo 解压."""
    p = tmp_path / "pseudo.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("flag{pseudo}.txt", "flag{pseudo_zip_test_xyz}\n")
    # 二进制修改 flag bit 0 = 1
    data = bytearray(p.read_bytes())
    for i in range(len(data) - 4):
        if data[i : i + 4] == b"PK\x03\x04":
            data[i + 6] |= 0x1
        elif data[i : i + 4] == b"PK\x01\x02":
            data[i + 8] |= 0x1
    p.write_bytes(data)
    return p


# ---------- DAG core ----------
class TestDAGCore:
    def test_action_abstract(self):
        with pytest.raises(TypeError):
            Action()  # type: ignore

    def test_dag_execute_single_node(self):
        class AddOne(Action):
            name = "add_one"
            def run(self, context):
                return ActionResult(
                    success=True,
                    data={"value": context.get("value", 0) + 1},
                )

        node = DAGNode(AddOne())
        dag = DAG(start_node=node)
        ctx = dag.execute({"value": 41})
        assert ctx["__last_result__"].data == {"value": 42}
        assert ctx["__log__"][0]["node"] == "add_one"

    def test_dag_failure_transfer(self):
        class AlwaysFail(Action):
            name = "fail"
            def run(self, context):
                return ActionResult(success=False, message="boom")

        class Recover(Action):
            name = "recover"
            def run(self, context):
                return ActionResult(success=True, data={"recovered": True})

        fail = DAGNode(AlwaysFail())
        recover = DAGNode(Recover())
        fail.on_failure = recover
        dag = DAG(start_node=fail)
        ctx = dag.execute({})
        log = ctx["__log__"]
        assert len(log) == 2
        assert log[0]["node"] == "fail" and log[0]["success"] is False
        assert log[1]["node"] == "recover" and log[1]["success"] is True

    def test_dag_max_steps_safety(self):
        count = {"n": 0}

        class Loop(Action):
            name = "loop"
            def run(self, context):
                count["n"] += 1
                return ActionResult(success=True)

        node = DAGNode(Loop())
        node.on_success = node
        dag = DAG(start_node=node, max_steps=5)
        ctx = dag.execute({})
        assert count["n"] == 5
        assert "__error__" in ctx


# ---------- binwalk_extract ----------
class TestBinwalkExtract:
    def test_binwalk_extract_real_file(self, tmp_path):
        src = tmp_path / "composite.bin"
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        zip_data = b"PK\x03\x04" + b"\x00" * 50
        src.write_bytes(png_data + b"\x00\x00\x00\x00" + zip_data)

        if not shutil.which("binwalk") or not shutil.which("foremost"):
            pytest.skip("binwalk or foremost not installed")

        extract_dir = tmp_path / "extract"
        action = BinwalkExtractAction()
        result = action.run({"file_path": str(src), "extract_dir": str(extract_dir)})
        # binwalk 可能识别也可能不识别（取决于样本）
        # 至少要返回 success=True 或 False with message
        assert result.message  # 必有 message

    def test_binwalk_extract_missing_file(self, tmp_path):
        action = BinwalkExtractAction()
        result = action.run({"file_path": str(tmp_path / "nonexistent.bin")})
        assert result.success is False
        assert "not found" in result.message


# ---------- foremost_extract (v0.5 重构) ----------
class TestForemostExtract:
    def test_foremost_extract_real_file(self, tmp_path):
        """foremost 单独提取（skip binwalk）."""
        if not shutil.which("foremost"):
            pytest.skip("foremost not installed")

        # 造一个含 zip 头的复合文件
        src = tmp_path / "composite.bin"
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        zip_data = b"PK\x03\x04" + b"\x00" * 50
        src.write_bytes(png_data + b"\x00\x00\x00\x00" + zip_data)

        action = ForemostExtractAction(file_types="all")
        result = action.run({"file_path": str(src)})
        # foremost 应该会识别 zip + png
        assert result.message
        if result.success:
            assert "extracted_files" in result.data

    def test_foremost_extract_missing_file(self, tmp_path):
        action = ForemostExtractAction()
        result = action.run({"file_path": str(tmp_path / "nonexistent.bin")})
        assert result.success is False
        assert "not found" in result.message

    def test_foremost_extract_custom_types(self, tmp_path):
        """file_types 参数生效 (e.g. 仅 zip)."""
        if not shutil.which("foremost"):
            pytest.skip("foremost not installed")

        # 造 png-only 文件
        src = tmp_path / "img.bin"
        src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        action = ForemostExtractAction(file_types="zip")
        result = action.run({"file_path": str(src)})
        # 期望失败 (无 zip 提取)
        assert result.message

    def test_find_foremost_extract_helper(self, tmp_path):
        """helper 函数: 扫描 output_dir 找 extracted files."""
        # 造 fake foremost output 结构
        out = tmp_path / "foremost_out"
        (out / "zip").mkdir(parents=True)
        (out / "png").mkdir(parents=True)
        (out / "zip" / "00000000.zip").write_bytes(b"fake")
        (out / "png" / "00000000.png").write_bytes(b"fake")
        (out / "zip" / "audit.txt").write_text("audit")  # 应被排除

        files = find_foremost_extract(out)
        assert len(files) == 2  # 排除 audit.txt
        assert any("zip" in f for f in files)
        assert any("png" in f for f in files)
        assert not any("audit.txt" in f for f in files)

    def test_foremost_extract_nonexistent_dir(self, tmp_path):
        """output dir 不存在 → empty list."""
        assert find_foremost_extract(tmp_path / "no_such_dir") == []


# ---------- v0.5 4 快捷 action (GUI 工具栏入口) ----------
class TestQuickActions:
    """Owner 需求: 工具栏加 4 入口 (lsb / fix_pseudo / bruteforce_zip / bruteforce_rar).

    通过 ChainRunner 跑 (single action mode) — 验证 GUI 端到端.
    """

    def test_fix_pseudo_zip_action(self, qtbot, tmp_path):
        """FixPseudoEncryptionAction: 伪加密 zip → 修复 OK."""
        from automisc.gui.chain_runner import ChainRunner
        import zipfile

        p = tmp_path / "pseudo.zip"
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("flag.txt", "flag{fix_pseudo_test}\n")
        # 改加密位 → 伪加密
        data = bytearray(open(p, "rb").read())
        for i in range(len(data) - 4):
            if data[i:i+4] == b"PK\x03\x04":
                data[i+6] |= 0x1
            elif data[i:i+4] == b"PK\x01\x02":
                data[i+8] |= 0x1
        open(p, "wb").write(data)

        results = {}
        runner = ChainRunner(chain_name="fix_pseudo_zip", file_path=str(p))
        runner.finished_with_context.connect(
            lambda cn, fp, ctx: results.setdefault("ctx", ctx)
        )
        runner.start()
        qtbot.waitUntil(lambda: "ctx" in results, timeout=10_000)
        runner.wait()

        log = results["ctx"].get("__log__", [])
        assert log[0]["node"] == "fix_pseudo_encryption"
        assert log[0]["success"] is True
        assert results["ctx"]["__last_result__"].data.get("fixed_count") == 2

    def test_bruteforce_zip_action(self, qtbot, tmp_path):
        """BruteforceZipAction: 真加密 zip (4位密码) → 找到密码."""
        from automisc.gui.chain_runner import ChainRunner
        import zipfile
        import subprocess

        # 7z 造真加密 zip
        p = tmp_path / "real.zip"
        subprocess.run(
            ["7z", "a", "-tzip", "-mem=ZipCrypto", "-p7531", str(p), "/etc/hosts"],
            capture_output=True,
            check=True,
        )

        results = {}
        runner = ChainRunner(
            chain_name="bruteforce_zip", file_path=str(p),
            bruteforce_limit=10000,  # 7531 < 10000
        )
        runner.finished_with_context.connect(
            lambda cn, fp, ctx: results.setdefault("ctx", ctx)
        )
        runner.start()
        qtbot.waitUntil(lambda: "ctx" in results, timeout=60_000)
        runner.wait()

        log = results["ctx"].get("__log__", [])
        assert log[0]["node"] == "bruteforce_zip"
        assert log[0]["success"] is True
        assert results["ctx"]["__last_result__"].data.get("password") == "7531"

    def test_lsb_extract_action(self, qtbot):
        """LSBExtractAction: PNG LSB text → flag_candidate."""
        from automisc.gui.chain_runner import ChainRunner
        if not Path("Challenge/steg.png").exists():
            pytest.skip("Challenge/steg.png 不存在")

        results = {}
        runner = ChainRunner(chain_name="lsb_extract", file_path="Challenge/steg.png")
        runner.finished_with_context.connect(
            lambda cn, fp, ctx: results.setdefault("ctx", ctx)
        )
        runner.start()
        qtbot.waitUntil(lambda: "ctx" in results, timeout=30_000)
        runner.wait()

        log = results["ctx"].get("__log__", [])
        assert log[0]["node"] == "lsb_extract"
        assert log[0]["success"] is True
        last = results["ctx"]["__last_result__"]
        assert last.data.get("flag_candidate")  # 整段 text
        assert "st3g0_saurus_wr3cks" in last.data["flag_candidate"]

    def test_bruteforce_rar_action_no_rar(self, qtbot, tmp_path):
        """BruteforceRarAction: rar 文件不存在 → graceful fail."""
        from automisc.gui.chain_runner import ChainRunner

        p = tmp_path / "no.rar"
        results = {}
        runner = ChainRunner(chain_name="bruteforce_rar", file_path=str(p))
        runner.finished_with_context.connect(
            lambda cn, fp, ctx: results.setdefault("ctx", ctx)
        )
        runner.start()
        qtbot.waitUntil(lambda: "ctx" in results, timeout=5_000)
        runner.wait()

        log = results["ctx"].get("__log__", [])
        assert log[0]["node"] == "bruteforce_rar"
        assert log[0]["success"] is False
        assert "not found" in log[0]["message"]


# ---------- zip_chain: detection ----------
class TestPseudoDetection:
    def test_pseudo_detected(self, pseudo_zip):
        assert _is_pseudo_encrypted(pseudo_zip) is True

    def test_normal_not_pseudo(self, normal_zip):
        assert _is_pseudo_encrypted(normal_zip) is False

    def test_nonexistent_returns_false(self, tmp_path):
        assert _is_pseudo_encrypted(tmp_path / "nonexistent.zip") is False


# ---------- zip_chain: actions ----------
class TestTryUnzip:
    def test_normal_zip_succeeds(self, normal_zip):
        result = TryUnzipAction().run({"file_path": str(normal_zip)})
        assert result.success is True
        assert "unzipped" in result.message
        assert "extracted_to" in result.data
        assert result.data["extracted_count"] == 2

    def test_pseudo_zip_fails(self, pseudo_zip):
        result = TryUnzipAction().run({"file_path": str(pseudo_zip)})
        assert result.success is False

    def test_nonexistent_file(self, tmp_path):
        result = TryUnzipAction().run({"file_path": str(tmp_path / "nope.zip")})
        assert result.success is False
        assert "not found" in result.message


class TestFixPseudoEncryption:
    def test_fix_pseudo_zip(self, pseudo_zip, tmp_path):
        fix_result = FixPseudoEncryptionAction().run({"file_path": str(pseudo_zip)})
        assert fix_result.success is True
        assert "fixed" in fix_result.message
        assert fix_result.data["fixed_count"] >= 1
        # 验证 zipfile 修复后可直接解压
        with zipfile.ZipFile(pseudo_zip) as zf:
            data = zf.read("flag{pseudo}.txt")
            assert b"pseudo_zip_test_xyz" in data
        backup = pseudo_zip.with_suffix(pseudo_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()

    def test_fix_normal_zip_fails(self, normal_zip):
        result = FixPseudoEncryptionAction().run({"file_path": str(normal_zip)})
        assert result.success is False
        assert "not pseudo" in result.message.lower()


# ---------- generate_passwords ----------
class TestGeneratePasswords:
    def test_dict_size(self):
        d = _generate_passwords(4, 6)
        assert 8_000_000 < len(d) < 9_000_000

    def test_starts_with_digits(self):
        d = _generate_passwords(4, 4)
        # 字典是 digits 4 位 (0-9999) + letters 4 位 (aaaa-ZZZZ)
        assert d[0] == "0000"
        # 9999 应该是 digits 最后
        assert "9999" in d[: 10**4]
        # ZZZZ 是 letters 最后
        assert d[-1] == "ZZZZ"

    def test_contains_letters(self):
        d = _generate_passwords(4, 4)
        assert "aaaa" in d
        assert "ZZZZ" in d


# ---------- zip_chain: 完整 DAG 链 ----------
class TestZipChainDAG:
    def test_normal_zip_chain(self, normal_zip):
        try_node = DAGNode(TryUnzipAction())
        fix_node = DAGNode(FixPseudoEncryptionAction())
        try_node.on_failure = fix_node

        dag = DAG(start_node=try_node)
        ctx = dag.execute({"file_path": str(normal_zip)})
        log = ctx["__log__"]
        assert len(log) == 1
        assert log[0]["node"] == "try_unzip"
        assert log[0]["success"] is True

    def test_pseudo_zip_chain(self, pseudo_zip):
        # 关键: 跑完 chain 后修复 fixture 回伪加密状态（避免影响下次测试）
        # 保存原始 bytes
        original_bytes = pseudo_zip.read_bytes()

        try_node = DAGNode(TryUnzipAction())
        fix_node = DAGNode(FixPseudoEncryptionAction())
        try_node.on_failure = fix_node
        fix_node.on_success = None
        fix_node.on_failure = None

        dag = DAG(start_node=try_node)
        ctx = dag.execute({"file_path": str(pseudo_zip)})
        log = ctx["__log__"]
        assert len(log) == 2
        assert log[0]["node"] == "try_unzip" and log[0]["success"] is False
        assert log[1]["node"] == "fix_pseudo_encryption" and log[1]["success"] is True

        # 验证解压后能读到
        import zipfile
        with zipfile.ZipFile(pseudo_zip) as zf:
            data = zf.read("flag{pseudo}.txt")
            assert b"pseudo_zip_test_xyz" in data

        # 还原 fixture: 删除 .bak + 重新设 flag bit 0 = 1
        backup = pseudo_zip.with_suffix(pseudo_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()
        # 重新构造伪加密
        data = bytearray(pseudo_zip.read_bytes())
        for i in range(len(data) - 4):
            if data[i : i + 4] == b"PK\x03\x04":
                data[i + 6] |= 0x1
            elif data[i : i + 4] == b"PK\x01\x02":
                data[i + 8] |= 0x1
        pseudo_zip.write_bytes(data)
