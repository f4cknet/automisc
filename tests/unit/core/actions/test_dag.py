"""DAG + actions 单测（v0.5-DAG-chain）"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from automisc.core.actions.binwalk_extract import BinwalkExtractAction
from automisc.core.actions.zip_chain import (
    BruteforceZipAction,
    FixPseudoEncryptionAction,
    TryUnzipAction,
    _generate_passwords,
    _is_pseudo_encrypted,
)
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

        if not shutil.which("binwalk"):
            pytest.skip("binwalk not installed")

        extract_dir = tmp_path / "extract"
        action = BinwalkExtractAction()
        result = action.run({"file_path": str(src), "extract_dir": str(extract_dir)})
        assert result.message  # 必有 message

    def test_binwalk_extract_missing_file(self, tmp_path):
        action = BinwalkExtractAction()
        result = action.run({"file_path": str(tmp_path / "nonexistent.bin")})
        assert result.success is False
        assert "not found" in result.message


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
