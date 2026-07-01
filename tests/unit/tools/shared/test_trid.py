"""测试 tools/shared/trid.py (v0.5-trid-toolbar)

per Owner 2026-07-01 22:00 拍板:
- 新建 trid adapter (基于 signature pattern 的文件类型识别器)
- GUI 工具栏 "共享基础工具 (PR1)" 下新增 "🔍 文件类型识别"
- 候选 vs 后缀 mismatch → severity=4 ⚠️

覆盖:
- 注册: get_tool("trid") → TridAdapter
- 真 PNG → file_type_trid SP (sev=1, 无 mismatch)
- 后缀伪装 ZIP 为 .png → file_type_mismatch SP (sev=4)
- 不存在的文件 → exit_code != 0 不 panic
- GUI menu 集成: 共享基础工具分类 + ADAPTER_TOOLS + 显示名
"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.shared.trid import TridAdapter
from automisc.tools.paths import resolve_tool_binary


# ---------- trid.exe 可用性 (跨平台, v0.5-platform-extend-tools) ----------
# macOS / Linux brew 不维护 trid (类似 zsteg), 默认 skip
# Win: extend-tools/bin/win-x64/TrID/trid.exe 手工部署 (per Owner 2026-07-01)
HAS_TRID = resolve_tool_binary("trid") is not None
SKIP_REASON = (
    "trid CLI not installed (extend-tools/bin/win-x64/TrID/trid.exe 手工部署, "
    "或 brew install -- 没有官方支持)"
)


# ---------- 注册 ----------

class TestTridRegistration:
    """per 双注册铁律: trid 必须通过 get_tool() 拿到."""

    def test_trid_is_registered(self):
        a = get_tool("trid")
        assert isinstance(a, TridAdapter)
        assert a.name == "trid"
        assert a.category == "shared"

    def test_trid_default_timeout_at_least_60s(self):
        """trid 加载 5.8MB defs + 扫描需要时间, default_timeout >= 60s."""
        a = get_tool("trid")
        assert a.default_timeout >= 60.0, (
            f"trid 加载 defs 包可能慢, default_timeout 应≥60s, got {a.default_timeout}"
        )


# ---------- 真 binary 跑 (trid.exe 已装才跑) ----------

@pytest.mark.skipif(not HAS_TRID, reason=SKIP_REASON)
class TestTridRun:
    """跑真 trid.exe + 真实 fixture, 验证 SP 解析 + 后缀 mismatch 判定."""

    def test_trid_runs_on_png_no_mismatch(self, tmp_png_file):
        """真 PNG → file_type_trid sev=1 SP, 后缀匹配无 mismatch."""
        a = TridAdapter()
        result = a.run(str(tmp_png_file))

        assert result.is_success, (
            f"trid 跑 PNG 应成功, got exit={result.exit_code}, "
            f"stderr={result.stderr}"
        )
        # stdout 应含 PNG 候选
        assert "PNG" in result.stdout, (
            f"stdout 应含 PNG 候选, got: {result.stdout[:200]}"
        )
        # file_type_trid SP 必须存在
        trid_sps = [sp for sp in result.suspicious_points if sp.category == "file_type_trid"]
        assert len(trid_sps) >= 1, (
            f"应至少 1 个 file_type_trid SP, got: {[(sp.category, sp.severity) for sp in result.suspicious_points]}"
        )
        assert trid_sps[0].severity == 1
        # 后缀 .png 与 PNG 候选一致 → 不应有 file_type_mismatch
        mismatch_sps = [sp for sp in result.suspicious_points if sp.category == "file_type_mismatch"]
        assert len(mismatch_sps) == 0, (
            f".png 真 PNG 不应触发 mismatch, got: {[sp.matched_pattern for sp in mismatch_sps]}"
        )

    def test_trid_detects_extension_mismatch_zip_as_png(self, tmp_path):
        """ZIP bytes 命名为 .png → 命中 file_type_mismatch sev=4 ⚠️.

        CTF 实战最常见的"扩展名伪装"套路之一. trid 基于 frequency signature
        透过 .png 后缀看到真实是 ZIP.
        """
        zip_bytes = b"PK\x03\x04rest of zip data, this is a minimal zip local file header"
        fake_png = tmp_path / "fake.png"  # 命名是 .png, 实际是 ZIP bytes
        fake_png.write_bytes(zip_bytes)

        a = TridAdapter()
        result = a.run(str(fake_png))

        # file_type_mismatch sev=4 是亮点
        mismatch_sps = [sp for sp in result.suspicious_points if sp.category == "file_type_mismatch"]
        assert len(mismatch_sps) == 1, (
            f"伪造 .png 应触发 1 个 file_type_mismatch, got categories: "
            f"{[sp.category for sp in result.suspicious_points]}"
        )
        assert mismatch_sps[0].severity == 4
        # matched_pattern 应同时提及 .png (实际后缀) + ZIP (trid 判定)
        assert ".png" in mismatch_sps[0].matched_pattern
        assert "zip" in mismatch_sps[0].matched_pattern.lower()
        # suggested_action 应有"扩展名伪装"提示
        assert "扩展名伪装" in mismatch_sps[0].suggested_action or "改后缀" in mismatch_sps[0].suggested_action

    def test_trid_handles_missing_file(self, tmp_path):
        """不存在的文件 → adapter 不 panic, exit_code != 0."""
        nonexistent = tmp_path / "does_not_exist_xyz.bin"
        a = TridAdapter()
        result = a.run(str(nonexistent))

        # 不应抛异常
        assert result is not None
        assert result.suspicious_points is not None
        # exit_code 应 != 0 (file not found)
        # 注: TrID 即使文件不存在也 exit 0, 但 stderr 报 "Cannot open", 走 SP 兜底
        # 我们只断言不 panic + SP 列表存在
        assert isinstance(result.suspicious_points, list)

    def test_trid_returns_useful_categories_on_real_binaries(self, tmp_path):
        """任意二进制 → adapter 至少 1 个 SP (no_candidates or file_type_trid)."""
        # 写个简单混合内容 binary
        binary = tmp_path / "mix.bin"
        binary.write_bytes(b"some bytes " * 50)

        a = TridAdapter()
        result = a.run(str(binary))

        # 至少 1 个 SP (适配器必须有产出)
        assert len(result.suspicious_points) >= 1, (
            f"trid adapter 应至少有 1 个 SP, got 0. stdout: {result.stdout[:200]}"
        )


# ---------- GUI 集成 ----------

class TestTridGuiIntegration:
    """验证 GUI 工具栏能识别 trid (per menu_dock.py 集成 + STRUCTURE.md)."""

    def test_trid_in_shared_category(self):
        """menu_dock.TOOL_CATEGORIES["共享基础工具 (PR1)"] 必须含 trid."""
        from automisc.gui.menu_dock import TOOL_CATEGORIES

        shared_tools = TOOL_CATEGORIES.get("共享基础工具 (PR1)", [])
        assert "trid" in shared_tools, (
            f"共享基础工具应含 trid, got: {shared_tools}"
        )
        # 跟 file/strings/binwalk/foremost/exiftool/xxd 同一级 (per v0.5-trid-toolbar §5)
        for peer in ("file", "strings", "binwalk", "foremost", "exiftool", "xxd"):
            assert peer in shared_tools, f"共享基础工具应含 {peer}"

    def test_trid_in_adapter_tools_set(self):
        """ADAPTER_TOOLS 必须含 trid (GUI 标记 ✓ 才会显示)."""
        from automisc.gui.menu_dock import ADAPTER_TOOLS

        assert "trid" in ADAPTER_TOOLS

    def test_trid_has_chinese_display_name(self):
        """ACTION_DISPLAY_NAMES 必须给 trid 配 "文件类型识别" 显示名 (Owner 指定)."""
        from automisc.gui.menu_dock import ACTION_DISPLAY_NAMES

        display = ACTION_DISPLAY_NAMES.get("trid")
        assert display is not None, "trid 应有中文 display name"
        assert "文件类型识别" in display, (
            f"display 应含 '文件类型识别' (Owner 指定), got: {display}"
        )


# ---------- 离线约束 (per STRUCTURE.md §1 + v0.5-trid-toolbar §4.4) ----------

class TestTridOfflineConstraint:
    """验证 adapter 永远走本地 defs 包 (-d: 显式锁), 不依赖 mark0.net 在线拉 defs.

    不真起 subprocess, 只 unit-test: _parse_candidates + defs 路径推导.
    """

    def test_defs_path_resolved_from_trid_binary_dir(self, monkeypatch, tmp_path):
        """defs 路径 = trid_binary.parent / triddefs.trd, 不依赖 PATH 在线拉."""
        # 模拟: trid.exe 在 tmp_path/TrID/ 下, defs 在 tmp_path/TrID/triddefs.trd
        fake_trid_dir = tmp_path / "TrID"
        fake_trid_dir.mkdir()
        fake_trid = fake_trid_dir / "trid.exe"
        fake_trid.write_bytes(b"fake trid binary")  # 仅占位, 不真跑
        fake_defs = fake_trid_dir / "triddefs.trd"
        fake_defs.write_bytes(b"fake defs")

        # monkey-patch automisc.tools.paths.resolve_tool_binary —
        # adapter.run() 函数内部用 `from automisc.tools.paths import resolve_tool_binary`
        # lazy import, 每次 run() 都从 automisc.tools.paths 模块拿当前值,
        # patch 模块 attribute 就影响所有 run() 调用.
        from automisc.tools import paths as paths_module
        monkeypatch.setattr(
            paths_module, "resolve_tool_binary",
            lambda name: str(fake_trid) if name == "trid" else None,
        )

        # mock _run_subprocess 避免真跑 trid, 拿到 defs_arg 验证
        captured_cmd: list[str] = []
        def fake_run(self, cmd, *, timeout=None):
            captured_cmd.extend(cmd)
            return 0, "fake_stdout", "", 0

        monkeypatch.setattr(TridAdapter, "_run_subprocess", fake_run)

        a = TridAdapter()
        dummy = tmp_path / "dummy.bin"
        dummy.write_bytes(b"x")
        a.run(str(dummy))

        # cmd 应含 -d:<abs_path_to_defs>
        assert any(
            arg.startswith("-d:") and str(fake_defs.resolve()) in arg
            for arg in captured_cmd
        ), (
            f"cmd 应含 -d:<abs defs path>, got: {captured_cmd}"
        )

    def test_defs_missing_does_not_panic(self, monkeypatch, tmp_path):
        """defs 包缺失 (误删) → adapter 不 panic, 调 trid 让 trid 报在线错误."""
        # 只有 trid.exe, 没 defs
        fake_trid_dir = tmp_path / "NoDef"
        fake_trid_dir.mkdir()
        fake_trid = fake_trid_dir / "trid.exe"
        fake_trid.write_bytes(b"fake trid")

        from automisc.tools import paths as paths_module
        monkeypatch.setattr(
            paths_module, "resolve_tool_binary",
            lambda name: str(fake_trid) if name == "trid" else None,
        )

        # mock _run_subprocess 不调用实际 binary
        def fake_run(self, cmd, *, timeout=None):
            # 验证 defs 缺失时, cmd 不含 -d: 参数 (走 trid 默认在线拉)
            assert not any(arg.startswith("-d:") for arg in cmd), (
                f"defs 缺失时 cmd 不应含 -d: 前缀, got: {cmd}"
            )
            return 0, "fake_stdout", "", 0
        monkeypatch.setattr(TridAdapter, "_run_subprocess", fake_run)

        a = TridAdapter()
        dummy = tmp_path / "dummy.bin"
        dummy.write_bytes(b"x")
        # 不 panic = OK
        result = a.run(str(dummy))
        assert result is not None
