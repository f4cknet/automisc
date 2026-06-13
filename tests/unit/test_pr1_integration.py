"""测试 v0.1.0b-PR1 集成：所有 6 个 adapter 都注册成功。"""
from __future__ import annotations

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import get_tool, list_tools
from automisc.tools import shared  # 触发 @register_tool


EXPECTED_TOOLS = {"file", "strings", "binwalk", "foremost", "exiftool", "xxd"}


def test_all_6_shared_adapters_registered():
    tools = set(list_tools())
    assert EXPECTED_TOOLS.issubset(tools), (
        f"missing tools: {EXPECTED_TOOLS - tools}"
    )


def test_all_adapters_can_be_instantiated():
    for name in EXPECTED_TOOLS:
        a = get_tool(name)
        assert a is not None
        assert hasattr(a, "run")
        assert a.check_available() is True, f"{name} not in PATH"


def test_all_adapters_have_correct_category():
    for name in EXPECTED_TOOLS:
        a = get_tool(name)
        assert a.category == "shared", f"{name}.category={a.category}"


def test_orchestrator_can_run_all_6(tmp_text_file):
    """端到端 smoke：CoreOrchestrator.run_tool 跑 6 个 adapter 全成功。"""
    core = CoreOrchestrator()
    file_path = str(tmp_text_file)

    for name in EXPECTED_TOOLS:
        result = core.run_tool(name, file_path)
        # file / strings / binwalk / exiftool / xxd 应该成功
        # foremost 对纯文本可能 exit code 0 但无提取（也接受）
        assert result.exit_code in (0, 1), (
            f"{name} exit_code={result.exit_code}, stderr={result.stderr[:200]}"
        )