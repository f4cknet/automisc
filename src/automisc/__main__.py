"""AutoMisc CLI 入口（v0.1.0b-PR1 占位）

v0.1.0b-PR1 阶段仅暴露 ``automisc tools list`` 子命令用于核对 adapter 注册。
GUI 入口（v0.1.1+）将在后续 PR 引入 PySide6 后启用。
"""
from __future__ import annotations

import argparse
import sys

from automisc import __version__


def cmd_tools_list(_args: argparse.Namespace) -> int:
    """列出所有已注册的 tool adapter。"""
    from automisc.core.registry import list_tools
    from automisc.tools import shared  # 触发 @register_tool 装饰器

    names = list_tools()
    if not names:
        print("(no tools registered yet)")
        return 0
    print(f"Registered tools ({len(names)}):")
    for name in names:
        print(f"  - {name}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """对给定文件运行指定 tool，返回 0/非 0。"""
    from automisc.core.orchestrator import CoreOrchestrator
    from automisc.core.registry import get_tool

    try:
        get_tool(args.tool)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    core = CoreOrchestrator()
    result = core.run_tool(args.tool, args.file)

    print(f"=== {result.tool_name} ===")
    print(f"exit_code: {result.exit_code}")
    print(f"duration_ms: {result.duration_ms}")
    if result.stderr:
        print(f"stderr:\n{result.stderr}")

    if result.suspicious_points:
        print(f"suspicious_points ({len(result.suspicious_points)}):")
        for sp in result.suspicious_points:
            print(f"  [{sp.severity}] {sp.category}: {sp.matched_pattern}")

    return 0 if result.exit_code == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="automisc",
        description="AutoMisc — CTF Misc 半自动化辅助工具箱",
    )
    parser.add_argument("--version", action="version", version=f"automisc {__version__}")

    sub = parser.add_subparsers(dest="cmd")

    p_tools = sub.add_parser("tools", help="工具管理")
    p_tools_sub = p_tools.add_subparsers(dest="tools_cmd")
    p_tools_sub.add_parser("list", help="列出已注册工具")

    p_run = sub.add_parser("run", help="运行指定工具")
    p_run.add_argument("--tool", required=True, help="工具名（见 `automisc tools list`）")
    p_run.add_argument("--file", required=True, help="目标文件路径")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "tools" and getattr(args, "tools_cmd", None) == "list":
        return cmd_tools_list(args)
    if args.cmd == "run":
        return cmd_run(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())