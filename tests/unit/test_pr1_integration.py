"""测试 v0.1.0b-PR1 + v0.1.0b-PR2 集成：所有 adapter 都注册成功。"""
from __future__ import annotations

from automisc.core.orchestrator import CoreOrchestrator
from automisc.core.registry import get_tool, list_tools
from automisc.tools import shared  # 触发 @register_tool


EXPECTED_TOOLS = {
    # PR1: 共享基础工具
    "file", "strings", "binwalk", "foremost", "exiftool", "xxd",
    # PR2: Stego/Image
    "zsteg", "stegseek",
}


def test_all_8_adapters_registered():
    tools = set(list_tools())
    missing = EXPECTED_TOOLS - tools
    assert not missing, f"missing tools: {missing}"


def test_all_adapters_can_be_instantiated():
    for name in EXPECTED_TOOLS:
        a = get_tool(name)
        assert a is not None
        assert hasattr(a, "run")
        # check_available：PR1 工具都在 PATH；zsteg/steghide 也都装了
        assert a.check_available() is True, f"{name} not in PATH"


def test_pr1_adapters_have_shared_category():
    """PR1 6 个 adapter 的 category 都是 'shared'。"""
    for name in ("file", "strings", "binwalk", "foremost", "exiftool", "xxd"):
        a = get_tool(name)
        assert a.category == "shared", f"{name}.category={a.category}"


def test_pr2_adapters_have_steganography_image_category():
    """PR2 2 个 adapter 的 category 是 'steganography_image'。"""
    for name in ("zsteg", "stegseek"):
        a = get_tool(name)
        assert a.category == "steganography_image", f"{name}.category={a.category}"


def test_orchestrator_can_run_all_8_on_text(tmp_text_file):
    """端到端 smoke：CoreOrchestrator.run_tool 跑所有 8 个 adapter。"""
    core = CoreOrchestrator()
    file_path = str(tmp_text_file)

    for name in EXPECTED_TOOLS:
        result = core.run_tool(name, file_path)
        # 对纯文本：file / strings / binwalk / exiftool / xxd 成功；
        # foremost / zsteg / steghide 可能 exit code 0 或 1（格式不支持）——都接受
        assert result.exit_code in (0, 1), (
            f"{name} exit_code={result.exit_code}, stderr={result.stderr[:200]}"
        )


def test_orchestrator_can_run_pr2_on_png(tmp_png_file):
    """Stego/Image adapter 在真实 PNG 上能跑通。"""
    core = CoreOrchestrator()
    file_path = str(tmp_png_file)

    for name in ("zsteg", "stegseek"):
        result = core.run_tool(name, file_path)
        # zsteg 在 PNG 上应成功（exit 0）；steghide 在 PNG 上 macOS 默认报不支持（exit 1）—— 都接受
        assert result.exit_code in (0, 1), (
            f"{name} exit_code={result.exit_code}, stderr={result.stderr[:200]}"
        )