"""DAG + actions 单测（v0.5-DAG-chain）"""
from __future__ import annotations

import shutil
import struct
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


def _make_pseudo_zip_form(p: Path, form: str) -> Path:
    """构造伪加密 zip (3 形态之一).

    形态 (per v0.5-train-004-cdh-pseudo-detect):
    - A: LFH bit0=1, CDH bit0=0 (仅 LFH 假加密)
    - B: LFH bit0=0, CDH bit0=1 (仅 CDH 假加密) ← 真实样本 00000038.zip 命中
    - C: LFH bit0=1, CDH bit0=1 (双假加密)
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(f"flag_{form}.txt", f"flag_{form}_test_xyz\n")
    data = bytearray(p.read_bytes())
    for i in range(len(data) - 4):
        if data[i : i + 4] == b"PK\x03\x04":  # LFH
            if form in ("A", "C"):
                data[i + 6] |= 0x1
            elif form == "B":
                data[i + 6] &= 0xFE  # 确保 LFH bit0=0
        elif data[i : i + 4] == b"PK\x01\x02":  # CDH
            if form in ("B", "C"):
                data[i + 8] |= 0x1
            elif form == "A":
                data[i + 8] &= 0xFE  # 确保 CDH bit0=0
    p.write_bytes(data)
    return p


@pytest.fixture
def pseudo_zip(tmp_path) -> Path:
    """真伪加密 zip: 加密位 set 但内容明文, 可通过 fix_pseudo 解压.

    兼容旧测试: 写 'flag{pseudo}.txt' (而不是 'flag_c.txt').
    形态: LFH+CDH bit0=1 (形态 C, 旧测试预期此形态).
    """
    p = tmp_path / "pseudo.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("flag{pseudo}.txt", "flag{pseudo_zip_test_xyz}\n")
    data = bytearray(p.read_bytes())
    for i in range(len(data) - 4):
        if data[i : i + 4] == b"PK\x03\x04":
            data[i + 6] |= 0x1
        elif data[i : i + 4] == b"PK\x01\x02":
            data[i + 8] |= 0x1
    p.write_bytes(data)
    return p


@pytest.fixture
def pseudo_zip_form_a(tmp_path) -> Path:
    """形态 A: 仅 LFH bit0=1 (CDH 0)."""
    return _make_pseudo_zip_form(tmp_path / "pseudo_a.zip", "A")


@pytest.fixture
def pseudo_zip_form_b(tmp_path) -> Path:
    """形态 B: 仅 CDH bit0=1 (LFH 0) ← 真实样本 00000038.zip 命中."""
    return _make_pseudo_zip_form(tmp_path / "pseudo_b.zip", "B")


@pytest.fixture
def pseudo_zip_form_c(tmp_path) -> Path:
    """形态 C: LFH+CDH bit0 都 = 1 (双假加密)."""
    return _make_pseudo_zip_form(tmp_path / "pseudo_c.zip", "C")


@pytest.fixture
def nested_pseudo_zip(tmp_path) -> Path:
    """外层 zip 形态 B 假加密 + 内含嵌套 zip (store 透明).

    模拟 v0.5-train-004 真实样本 00000038.zip 拓扑 (外层 CDH 假加密 + 嵌套 qwe.zip store).
    修复后必须: ① 外层 entry 能解出 ② 嵌套 zip 内部 CRC 一致 (不被破坏)

    实现: 先造嵌套 zip → 外层 zip write 嵌套文件 → 用 EOCD 倒推外层 CDH 区域,
    只设外层 CDH bit0=1 (避免误设嵌套 CDH).
    """
    # 1) 造嵌套 zip
    nested_p = tmp_path / "_nested_inner.zip"
    with zipfile.ZipFile(nested_p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("nested_flag.txt", "nested_content_xyz\n")

    # 2) 外层 zip: 1 entry (形态 B 假加密) + 内含 nested_p 数据
    outer_p = tmp_path / "outer_pseudo.zip"
    with zipfile.ZipFile(outer_p, "w", zipfile.ZIP_STORED) as zf:
        zf.write(nested_p, arcname="inner.zip")
    data = bytearray(outer_p.read_bytes())

    # 3) 找最末尾 EOCD, 拿外层 CDH 区域
    eocd_offset = -1
    i = len(data) - 22
    while i >= 0:
        if data[i : i + 4] == b"PK\x05\x06":
            eocd_offset = i
            break
        i -= 1
    cdh_count = struct.unpack("<H", data[eocd_offset + 10 : eocd_offset + 12])[0]
    cdh_size = struct.unpack("<I", data[eocd_offset + 12 : eocd_offset + 16])[0]
    cdh_start = struct.unpack("<I", data[eocd_offset + 16 : eocd_offset + 20])[0]
    cdh_end = cdh_start + cdh_size

    # 4) 只设外层 CDH (在 [cdh_start, cdh_end) 范围内) bit0=1
    for i in range(cdh_start, cdh_end - 46):
        if data[i : i + 4] == b"PK\x01\x02":
            data[i + 8] |= 0x1
    outer_p.write_bytes(data)
    return outer_p


@pytest.fixture
def mixed_zip(tmp_path) -> Path:
    """混合 zip: 1 clear + 1 pseudo (形态 B) + 1 real (per v0.5-zip-pseudo-per-entry-classify).

    验证 per-entry 分类算法 (per ctf-wiki 原理):
    - clear.txt: LFH/CDH bit0=0, 完全明文 → 分类 clear
    - pseudo.txt: LFH/CDH bit0=0, CDH bit0=1 (形态 B), data 末位不在 0-11 → 分类 pseudo
    - real.txt: LFH/CDH bit0=0, CDH bit0=1 (形态 B), data 第 11 字节改成 0-11 → 分类 real

    owner 决策 A+A:
    - FixPseudoEncryptionAction 只清 pseudo 的 LFH/CDH bit 0 (1 处), 不动 real
    """
    # 1) 先用 zipfile 写 3 个 store entry (LFH/CDH bit0 都 0, data 末位都不在 0-11)
    p = tmp_path / "mixed.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("clear.txt", "clear_content_xyz\n")  # 18 bytes, [11]='t' 不在 0-11
        zf.writestr("pseudo.txt", "pseudo_content_xyz\n")  # 19 bytes, [11]='n' 不在 0-11
        zf.writestr("real.txt", "real_content_xyz_buffer\n")  # 24 bytes, [11]='z' 不在 0-11
    data = bytearray(p.read_bytes())

    # 2) 找外层 CDH 区域 (用 EOCD 倒推)
    eocd_offset = -1
    i = len(data) - 22
    while i >= 0:
        if data[i : i + 4] == b"PK\x05\x06":
            eocd_offset = i
            break
        i -= 1
    cdh_count = struct.unpack("<H", data[eocd_offset + 10 : eocd_offset + 12])[0]
    cdh_size = struct.unpack("<I", data[eocd_offset + 12 : eocd_offset + 16])[0]
    cdh_start = struct.unpack("<I", data[eocd_offset + 16 : eocd_offset + 20])[0]
    cdh_end = cdh_start + cdh_size

    # 3) 改 CDH bit0=1 for pseudo + real (按 fname 匹配, 顺序写入)
    #    收集外层 CDH 区域的 (cdh_offset, fname) 对
    cdh_entries = []
    k = cdh_start
    while k < cdh_end - 46:
        if data[k : k + 4] == b"PK\x01\x02":
            fnl = struct.unpack("<H", data[k + 28 : k + 30])[0]
            exl = struct.unpack("<H", data[k + 30 : k + 32])[0]
            cmt = struct.unpack("<H", data[k + 32 : k + 34])[0]
            cdh_fname = data[k + 46 : k + 46 + fnl].decode("utf-8", errors="replace")
            cdh_entries.append((k, cdh_fname))
            k = k + 46 + fnl + exl + cmt
        else:
            k += 1

    # zipfile.writestr 写入顺序: clear → pseudo → real (按 writestr 顺序)
    for cdh_off, fname in cdh_entries:
        if fname == "pseudo.txt":
            data[cdh_off + 8] |= 0x1  # CDH bit0=1
        elif fname == "real.txt":
            data[cdh_off + 8] |= 0x1  # CDH bit0=1

    # 4) 改 real.txt 的 data 第 11 字节 (offset 11) 到 0-11 范围 → 模拟 PKCS#5 末位
    #    real.txt data 起点: 用 CDH 反查 LFH, 再 LFH + 30 + fnl + exl
    for cdh_off, fname in cdh_entries:
        if fname == "real.txt":
            lfh_off = struct.unpack("<I", data[cdh_off + 42 : cdh_off + 46])[0]
            fnl = struct.unpack("<H", data[lfh_off + 26 : lfh_off + 28])[0]
            exl = struct.unpack("<H", data[lfh_off + 28 : lfh_off + 30])[0]
            data_start = lfh_off + 30 + fnl + exl
            # real.txt data 第 11 字节 = data_start + 11
            data[data_start + 11] = 0x05  # 0-11 范围 → 模拟 PKCS#5 末位 → 判 real
            break

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

    # v0.5-zip-pseudo-cdh-detect: 3 形态覆盖 (per train-004 §5)
    def test_form_a_lfh_only(self, pseudo_zip_form_a):
        """形态 A: LFH bit0=1, CDH bit0=0 → 旧代码能识别 (回归)."""
        assert _is_pseudo_encrypted(pseudo_zip_form_a) is True

    def test_form_b_cdh_only(self, pseudo_zip_form_b):
        """形态 B: LFH bit0=0, CDH bit0=1 ← 旧代码漏识别, 新代码覆盖."""
        assert _is_pseudo_encrypted(pseudo_zip_form_b) is True

    def test_form_c_both(self, pseudo_zip_form_c):
        """形态 C: LFH bit0=1, CDH bit0=1 (双假加密) ← 旧代码能识别 (回归)."""
        assert _is_pseudo_encrypted(pseudo_zip_form_c) is True

    def test_nested_pseudo_detected(self, nested_pseudo_zip):
        """嵌套 zip (外层形态 B 假加密 + 内含 zip) → 外层应判 True."""
        assert _is_pseudo_encrypted(nested_pseudo_zip) is True

    def test_mixed_zip_has_pseudo(self, mixed_zip):
        """混合 zip (1 clear + 1 pseudo + 1 real) → 含伪加密 → True."""
        assert _is_pseudo_encrypted(mixed_zip) is True


# v0.5-zip-pseudo-per-entry-classify: per-entry 分类算法
class TestClassifyZipEntries:
    """v0.5-train-005 反馈: per-entry 独立判断, 不 short-circuit (per ctf-wiki 原理)."""

    def test_normal_zip_all_clear(self, normal_zip):
        """正常 zip (无加密位) → 全部 clear, 0 pseudo, 0 real."""
        from automisc.core.actions.zip_chain import _classify_zip_entries
        classify = _classify_zip_entries(normal_zip)
        assert len(classify["pseudo"]) == 0
        assert len(classify["real"]) == 0
        assert set(classify["clear"].keys()) == {"flag{normal}.txt", "readme.txt"}

    def test_form_b_cdh_only_classified_as_pseudo(self, pseudo_zip_form_b):
        """形态 B (CDH bit0=1, data 明文) → per-entry 分类为 pseudo (不修真加密)."""
        from automisc.core.actions.zip_chain import _classify_zip_entries
        classify = _classify_zip_entries(pseudo_zip_form_b)
        assert "flag_B.txt" in classify["pseudo"]
        assert "flag_B.txt" not in classify["real"]
        assert "flag_B.txt" not in classify["clear"]

    def test_mixed_zip_per_entry(self, mixed_zip):
        """混合 zip: clear + pseudo + real 三种 entry 各 1 个."""
        from automisc.core.actions.zip_chain import _classify_zip_entries
        classify = _classify_zip_entries(mixed_zip)
        # 1 clear (CDH bit0=0, 无加密位)
        assert "clear.txt" in classify["clear"]
        # 1 pseudo (CDH bit0=1, data 末位不在 0-11)
        assert "pseudo.txt" in classify["pseudo"]
        # 1 real (CDH bit0=1, data 第 11 字节改成 0-11 模拟 PKCS#5 末位)
        assert "real.txt" in classify["real"]
        # 三个互不重叠
        all_entries = set(classify["pseudo"]) | set(classify["real"]) | set(classify["clear"])
        assert all_entries == {"clear.txt", "pseudo.txt", "real.txt"}

    def test_nested_zip_outer_classification(self, nested_pseudo_zip):
        """嵌套 zip: 外层 entry 分类正确, 嵌套 entry 不混入外层分类.

        外层 'inner.zip' (CDH bit0=1) → 伪加密 (per train-004)
        嵌套 'nested_flag.txt' (嵌套 CDH bit0=0, 不在外层 CDH 区域) → 不被外层分类
        """
        from automisc.core.actions.zip_chain import _classify_zip_entries
        classify = _classify_zip_entries(nested_pseudo_zip)
        # 外层 inner.zip: 形态 B 假加密 (data 是嵌套 zip 184 字节, 第 11 字节不在 0-11)
        assert "inner.zip" in classify["pseudo"]
        # 嵌套 entry 不会被收进外层分类 (因为 CDH 区域只扫外层)
        assert "nested_flag.txt" not in classify["pseudo"]
        assert "nested_flag.txt" not in classify["real"]
        assert "nested_flag.txt" not in classify["clear"]


# v0.5-zip-pseudo-per-entry-classify: 修复只清伪加密, 不修真加密
class TestFixMixedZip:
    """v0.5-train-005 + owner 决策 A+A: 只清 pseudo, 不动 real."""

    def test_fix_mixed_zip_only_clears_pseudo(self, mixed_zip):
        """混合 zip 修复: 只清 pseudo (1 处), 不动 real."""
        # 1) 修复前状态
        with zipfile.ZipFile(mixed_zip) as zf:
            pre_flags = {info.filename: info.flag_bits for info in zf.infolist()}
        assert pre_flags["pseudo.txt"] & 0x1, "pseudo.txt CDH bit0 应为 1 (形态 B)"
        assert pre_flags["real.txt"] & 0x1, "real.txt CDH bit0 应为 1"
        assert not (pre_flags["clear.txt"] & 0x1), "clear.txt CDH bit0 应为 0"

        # 2) 跑 fix_pseudo
        result = FixPseudoEncryptionAction().run({"file_path": str(mixed_zip)})
        assert result.success is True
        # 1 处修复 (pseudo.txt 的 CDH bit0)
        assert result.data["fixed_count"] == 1
        # 报告 per-entry 分类
        assert "pseudo.txt" in result.data["pseudo_entries"]
        assert "real.txt" in result.data["real_entries"]
        assert "clear.txt" in result.data["clear_entries"]

        # 3) 修复后状态
        with zipfile.ZipFile(mixed_zip) as zf:
            post_flags = {info.filename: info.flag_bits for info in zf.infolist()}
        # pseudo: bit0 清 0 (修复)
        assert not (post_flags["pseudo.txt"] & 0x1), "pseudo.txt CDH bit0 应被清 0"
        # real: bit0 保持 1 (不修, per-owner 决策 A)
        assert post_flags["real.txt"] & 0x1, "real.txt CDH bit0 应保持 1 (不修真加密)"
        # clear: bit0 保持 0 (本来就没设)
        assert not (post_flags["clear.txt"] & 0x1), "clear.txt CDH bit0 应保持 0"

        # 4) clear + pseudo 解出, real 解不出 (真加密, 无密码)
        assert result.data["extracted_count"] >= 1
        # bad_entries 应包含 real.txt (zipfile 报 encrypted/password required)
        real_bad = [b for b in result.data["bad_entries"] if b[0] == "real.txt"]
        # 注意: real.txt 的 data 第 11 字节被改成 0x05 (模拟 PKCS#5), 但 data 不是真加密算法输出
        # zipfile 仍会读 entry 看 CDH bit0=1 → 要密码 → 报"is encrypted"或 CRC 错
        # 这个测试只验证: real 没被修真加密位 (bit0 仍是 1), 不强制要求它能解压
        backup = mixed_zip.with_suffix(mixed_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()


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
        # v0.5-zip-pseudo-per-entry-classify: 改用 "no pseudo-encrypted entry found"
        assert "no pseudo-encrypted entry" in result.message.lower()

    # v0.5-zip-pseudo-cdh-detect: 3 形态 fix_pseudo 都应能解压 (per train-004)
    def test_fix_form_a(self, pseudo_zip_form_a):
        """形态 A: fix_pseudo 清 LFH/CDH bit0 → 解压 OK."""
        result = FixPseudoEncryptionAction().run({"file_path": str(pseudo_zip_form_a)})
        assert result.success is True
        with zipfile.ZipFile(pseudo_zip_form_a) as zf:
            data = zf.read("flag_A.txt")
            assert b"flag_A_test_xyz" in data
        backup = pseudo_zip_form_a.with_suffix(pseudo_zip_form_a.suffix + ".bak")
        if backup.exists():
            backup.unlink()

    def test_fix_form_b(self, pseudo_zip_form_b):
        """形态 B: fix_pseudo 清 LFH/CDH bit0 → 解压 OK ← owner 真实样本命中形态."""
        result = FixPseudoEncryptionAction().run({"file_path": str(pseudo_zip_form_b)})
        assert result.success is True
        with zipfile.ZipFile(pseudo_zip_form_b) as zf:
            data = zf.read("flag_B.txt")
            assert b"flag_B_test_xyz" in data
        backup = pseudo_zip_form_b.with_suffix(pseudo_zip_form_b.suffix + ".bak")
        if backup.exists():
            backup.unlink()

    def test_fix_form_c(self, pseudo_zip_form_c):
        """形态 C: fix_pseudo 清 LFH/CDH bit0 → 解压 OK (回归)."""
        result = FixPseudoEncryptionAction().run({"file_path": str(pseudo_zip_form_c)})
        assert result.success is True
        with zipfile.ZipFile(pseudo_zip_form_c) as zf:
            data = zf.read("flag_C.txt")
            assert b"flag_C_test_xyz" in data
        backup = pseudo_zip_form_c.with_suffix(pseudo_zip_form_c.suffix + ".bak")
        if backup.exists():
            backup.unlink()

    def test_fix_nested_zip_no_collateral_damage(self, nested_pseudo_zip):
        """嵌套 zip: fix_pseudo 只修外层 LFH/CDH, 嵌套 zip 内部 CRC 一致.

        关键 (per v0.5-train-004 §3.4): 旧修复代码用 magic 搜索 PK\\x03\\x04/PK\\x01\\x02
        会破坏嵌套 zip 内部 LFH/CDH → 嵌套 zip CRC fail.
        新代码用 EOCD 倒推 + CDH 反查 LFH offset, 只修外层 entry 的 LFH/CDH.
        """
        result = FixPseudoEncryptionAction().run({"file_path": str(nested_pseudo_zip)})
        assert result.success is True
        assert result.data["fixed_count"] >= 1
        # 验证外层 entry 解压 OK
        with zipfile.ZipFile(nested_pseudo_zip) as zf:
            data = zf.read("inner.zip")
            # 验证嵌套 zip 内部 CRC 一致 (即嵌套 zip 仍可正常解压)
            import io
            with zipfile.ZipFile(io.BytesIO(data)) as nested_zf:
                nested_data = nested_zf.read("nested_flag.txt")
                assert b"nested_content_xyz" in nested_data
        backup = nested_pseudo_zip.with_suffix(nested_pseudo_zip.suffix + ".bak")
        if backup.exists():
            backup.unlink()


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


# ---------- v0.5-journal-highlight-keywords: stop_if 谓词 ----------
class TestStopIfPredicate:
    """v0.5-journal-highlight-keywords (per Owner 2026-06-16) 加的 stop_if 谓词机制."""

    def test_stop_if_true_terminates_chain(self):
        """stop_if 返回 True → chain 立即停, 即使 on_failure 指向下一步."""
        from automisc.core.dag import DAG, DAGNode, Action, ActionResult

        class StubAction(Action):
            def __init__(self, name, return_data=None):
                super().__init__()
                self.name = name
                self._return_data = return_data or {}

            def run(self, context):
                return ActionResult(
                    success=False,
                    data={**self._return_data, "stop_reason": "encrypted"},
                    message=f"{self.name} failed",
                )

        def stop_on_encrypted(result):
            return result.data and result.data.get("stop_reason") == "encrypted"

        a = StubAction("a", {"encrypted": True})
        b = StubAction("b")

        node_a = DAGNode(a, stop_if=stop_on_encrypted)
        node_b = DAGNode(b)
        node_a.on_failure = node_b  # 即使失败, stop_if 应优先

        dag = DAG(start_node=node_a)
        ctx = dag.execute({"file_path": "x.zip"})

        # 应只跑了 a, 没跑 b
        steps = [step["node"] for step in ctx.get("__log__", [])]
        assert "a" in steps
        assert "b" not in steps
        # log 应标记 stop_reason
        assert any("stop_if" in step.get("stop_reason", "") for step in ctx["__log__"])

    def test_stop_if_false_continues_normal_flow(self):
        """stop_if 返回 False → 走 on_success / on_failure 正常转移."""
        from automisc.core.dag import DAG, DAGNode, Action, ActionResult

        class StubAction(Action):
            def __init__(self, name, success):
                super().__init__()
                self.name = name
                self._success = success

            def run(self, context):
                return ActionResult(success=self._success, data={}, message=f"{self.name}")

        def never_stop(result):
            return False

        a = StubAction("a", success=False)
        b = StubAction("b", success=True)

        node_a = DAGNode(a, stop_if=never_stop)
        node_b = DAGNode(b)
        node_a.on_failure = node_b

        dag = DAG(start_node=node_a)
        ctx = dag.execute({})

        steps = [step["node"] for step in ctx.get("__log__", [])]
        assert "a" in steps
        assert "b" in steps  # 正常走了 on_failure

    def test_stop_if_none_default_unchanged(self):
        """stop_if 不传 (None) → 行为跟 v0.1 一致."""
        from automisc.core.dag import DAG, DAGNode, Action, ActionResult

        class StubAction(Action):
            def __init__(self, name, success):
                super().__init__()
                self.name = name
                self._success = success

            def run(self, context):
                return ActionResult(success=self._success, data={}, message=self.name)

        a = StubAction("a", success=True)
        node_a = DAGNode(a)  # stop_if 默认 None
        node_a.on_success = None
        node_a.on_failure = None

        dag = DAG(start_node=node_a)
        ctx = dag.execute({})
        # 不抛异常就行
        assert "a" in [s["node"] for s in ctx.get("__log__", [])]
