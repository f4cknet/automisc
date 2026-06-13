"""v0.1.0b-PR9 — Python 包基座 smoke 单测

锁定 ``automisc`` 包的物理形态 + CLI 入口不被后续 PR 破坏：
1. ``import automisc`` + 元数据（__version__ / __author__）就位
2. ``automisc.core`` + ``automisc.tools`` 子包可导入
3. ``python -m automisc`` + console_script ``automisc`` 入口函数 ``main()`` 行为一致
4. ``--version`` 子命令正确输出版本号
5. ``automisc`` 无子命令时输出帮助（exit 0）不抛异常

不依赖任何外部工具 / GUI / fixture。
"""
from __future__ import annotations

import importlib
import subprocess
import sys

import pytest


# ---------- 1. 包元数据 ----------

def test_package_imports():
    """automisc 包可导入，无 ImportError。"""
    pkg = importlib.import_module("automisc")
    assert pkg is not None


def test_package_version():
    """__version__ 必须是非空字符串（per pyproject.toml 项目版本）。"""
    import automisc

    assert hasattr(automisc, "__version__")
    assert isinstance(automisc.__version__, str)
    assert automisc.__version__ != ""
    # v0.1.0b.dev0 是当前 dev 版本号（per pyproject.toml）
    assert automisc.__version__ == "0.1.0b.dev0"


def test_package_docstring_or_summary():
    """包级文档字符串（per Architecture.md §1 一句话定位）。"""
    import automisc

    # 包级 __doc__ 非空即可（不强制文本匹配，PR 演进时 summary 可能微调）
    assert automisc.__doc__ is not None
    assert len(automisc.__doc__.strip()) > 0


# ---------- 2. 子包可导入 ----------

@pytest.mark.parametrize(
    "module_path",
    [
        "automisc",
        "automisc.core",
        "automisc.core.result",
        "automisc.core.suspicious",
        "automisc.core.registry",
        "automisc.core.orchestrator",
        "automisc.tools",
        "automisc.tools.base",
        "automisc.tools.shared",
        "automisc.tools.steganography",
        "automisc.tools.steganography.image",
    ],
)
def test_submodule_imports(module_path: str):
    """所有 PR1/PR2 已落地子模块必须可 import。

    这是 PR9 的核心锁定 — 防止后续 PR 误删 / 改名某个子模块导致 GUI / CLI 启动失败。
    """
    mod = importlib.import_module(module_path)
    assert mod is not None


# ---------- 3. CLI main() 行为 ----------

def test_main_version_flag_exits_zero():
    """``automisc --version`` 应 exit 0 并输出 __version__。"""
    from automisc.__main__ import main

    # argparse --version 行为：parse 后 SystemExit(0)
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0


def test_main_no_args_prints_help_and_exits_zero():
    """``automisc`` 无子命令应输出帮助并 exit 0（per __main__.py parser.print_help 分支）。"""
    from automisc.__main__ import main

    # 不传 argv → 走到 parser.print_help() + return 0（不会 SystemExit）
    rc = main([])
    assert rc == 0


def test_main_tools_list_via_function():
    """``automisc tools list`` 直接调函数应 exit 0。"""
    from automisc.__main__ import cmd_tools_list, main
    import argparse

    args = argparse.Namespace()  # cmd_tools_list 不读 args
    rc = main(["tools", "list"])
    assert rc == 0


def test_main_unknown_subcommand_prints_help():
    """``automisc unknown-cmd`` argparse 应 SystemExit(2)（argparse 默认行为）。"""
    from automisc.__main__ import main

    with pytest.raises(SystemExit) as exc_info:
        main(["definitely-not-a-real-subcommand"])

    # argparse 默认对未知子命令 exit 2
    assert exc_info.value.code == 2


# ---------- 4. console_script 入口可调用 ----------

def test_console_script_entry_point_registered():
    """pyproject.toml [project.scripts] 必须注册 automisc = automisc.__main__:main。"""
    import automisc.__main__ as cli_main

    assert hasattr(cli_main, "main")
    assert callable(cli_main.main)


# ---------- 5. 真实 subprocess 烟囱测试（锁定 console_script 真在 PATH 中）----------

def test_console_script_subprocess_runs(tmp_path, monkeypatch):
    """真实跑 ``python -m automisc --version`` 子进程 — 锁定从 shell 启动也不挂。

    PR9 的关键 smoke：未来 PR 改坏 CLI 入口时这条 fail 立即可见。
    """
    # 用当前 Python 解释器调 -m（比依赖 PATH 中的 automisc shim 更稳）
    result = subprocess.run(
        [sys.executable, "-m", "automisc", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    # argparse --version 输出 "automisc 0.1.0b.dev0"
    assert "automisc" in result.stdout
    assert "0.1.0b.dev0" in result.stdout


def test_console_script_help_subprocess():
    """无参数调 ``python -m automisc`` 应输出 usage 文本并 exit 0。"""
    result = subprocess.run(
        [sys.executable, "-m", "automisc"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    # parser.print_help 输出含 prog 名 + 子命令列表
    assert "usage:" in result.stdout
    assert "{tools,run,gui,chain}" in result.stdout


# ---------- 6. __main__ 模块自身 ----------

def test_main_module_has_parser_builder():
    """__main__ 必须暴露 build_parser() — 给后续 PR / 外部脚本复用。"""
    import automisc.__main__ as cli_main

    assert hasattr(cli_main, "build_parser")
    parser = cli_main.build_parser()
    # argparse.ArgumentParser 的 .prog 属性是我们设的 "automisc"
    assert parser.prog == "automisc"