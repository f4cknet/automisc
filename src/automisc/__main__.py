"""AutoMisc CLI 入口（v0.1.0b-PR1 占位 + v0.1.1 GUI 子命令）

v0.1.0b-PR1 阶段仅暴露 ``automisc tools list`` 子命令用于核对 adapter 注册。
v0.1.1 起新增 ``automisc gui`` 启动 PySide6 GUI 窗口（macOS only）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automisc import __version__


def cmd_tools_list(_args: argparse.Namespace) -> int:
    """列出所有已注册的 tool adapter."""
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
    """对给定文件运行指定 tool，返回 0/非 0."""
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


def cmd_gui(_args: argparse.Namespace) -> int:
    """启动 PySide6 GUI 主窗口（macOS only）."""
    return main_gui()


def main_gui() -> int:
    """无参入口：给 console_script `automisc-gui` 用."""
    import sys

    from PySide6.QtWidgets import QApplication

    from automisc.core.orchestrator import CoreOrchestrator
    from automisc.gui.main_window import MainWindow
    # 触发全部 adapter 注册
    from automisc.tools import shared  # noqa: F401
    from automisc.tools import steganography, forensics, misc  # noqa: F401

    app = QApplication.instance() or QApplication(sys.argv)
    core = CoreOrchestrator()
    win = MainWindow(core=core)
    win.show()
    return app.exec()


def cmd_decode_base64_image(args: argparse.Namespace) -> int:
    """CLI: base64 -> 图片（v0.5+ standalone）.

    决策树: data URL 头 -> 直接 decode; 无头 -> 加 image/* 头尝试;
            解出 tmp -> file 命令验证是 image; 否则报"转图片失败".

    v0.5-decoder-menu: 通用 dispatcher (v0.5+ decoder 自动从 registry 注册).
    """
    from automisc.core.decoders.base64_image import (
        Base64ImageError,
        decode_file_to_image,
    )

    try:
        r = decode_file_to_image(
            args.file,
            output_dir=args.out_dir,
            keep_output=args.keep,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Base64ImageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("=== base64 -> image ===")
    print(f"output_path:   {r.output_path}")
    print(f"detected_mime: {r.detected_mime}")
    print(f"source_hint:   {r.source_mime_hint or '(no data: header)'}")
    print(f"raw_size:      {r.raw_size}")
    return 0


def cmd_decode_dispatcher(args: argparse.Namespace) -> int:
    """v0.5-decoder-menu: 通用 decoder dispatcher (按 decoder name 派发).

    所有 v0.5+ decoder 通过 core.decoders.registry 注册, CLI 子命令自动生成.
    """
    from automisc.core.decoders.registry import get_decoder

    spec = get_decoder(args.decoder_name)
    if spec is None:
        print(f"error: unknown decoder '{args.decoder_name}'", file=sys.stderr)
        return 2

    # 只传 decoder 知道的 kwargs (用 inspect 拿 signature, 排除未知字段)
    import inspect
    sig = inspect.signature(spec.run)
    valid_kwargs = set(sig.parameters.keys())
    raw_kwargs = {
        k: v for k, v in vars(args).items()
        if k in valid_kwargs
    }

    try:
        result = spec.run(**raw_kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # 打印 result 字段 (简单 dataclass dump, 长字段截断)
    print(f"=== {spec.display} ===")
    for k, v in vars(result).items():
        if isinstance(v, str) and len(v) > 500:
            v = v[:500] + f"... (truncated, total {len(v)} chars)"
        elif isinstance(v, list) and len(v) > 20:
            v = v[:20] + [f"... and {len(v) - 20} more"]
        print(f"{k}: {v}")
    return 0


def cmd_chain(args: argparse.Namespace) -> int:
    """CLI: 跑预定义 DAG chain (v0.5-DAG).

    支持的 chain:
    - zip: try_unzip -> fix_pseudo (默认)
    - zip-full: try_unzip -> fix_pseudo -> bruteforce
    - binwalk: binwalk 检测 + foremost 提取
    - foremost: foremost 单独提取 (skip binwalk detection)
    - lsb: binwalk 提取 + LSB 智能路由 (text 终止 / file 二次 router)
    - lsb-bytes: binwalk 提取 + LSB 字节流自定义抽取 (4 参数 user-controlled)
    """
    from automisc.core.chains import (
        build_binwalk_extract_dag,
        build_foremost_extract_dag,
        build_lsb_bytes_chain,
        build_lsb_extract_chain,
        build_zip_chain_dag,
        build_zip_chain_with_bruteforce,
    )
    from automisc.core.router import FileRouter

    chain_name = args.chain
    file_path = args.file

    # 1) router 推荐
    print(f"=== chain: {chain_name} ===")
    print(f"=== file:  {file_path} ===")
    try:
        route = FileRouter().route(file_path)
        print(f"\n[router] ext={route.detected_extension} magic={route.detected_magic or 'unknown'}")
        for rec in route.recommendations[:5]:
            print(f"  {rec.score:3d}  {rec.tool_name:15s}  {rec.reason}")
    except Exception as e:  # noqa: BLE001
        print(f"[router] error: {e}")
        return 1

    # 2) 选 chain
    if chain_name == "zip":
        dag = build_zip_chain_dag()
    elif chain_name == "zip-full":
        dag = build_zip_chain_with_bruteforce()
    elif chain_name == "binwalk":
        dag = build_binwalk_extract_dag()
    elif chain_name == "foremost":
        dag = build_foremost_extract_dag()
    elif chain_name == "lsb":
        dag = build_lsb_extract_chain()
    elif chain_name == "lsb-bytes":
        # v0.5-lsb-byte-stream-extract: 4 参数 user-controlled
        dag = build_lsb_bytes_chain(
            channels=getattr(args, "channels", None),
            bit=getattr(args, "bit", 0),
            scan_order=getattr(args, "scan_order", "row"),
            byte_bit_order=getattr(args, "byte_bit_order", "MSB"),
        )
    else:
        print(f"unknown chain: {chain_name}")
        return 1

    # 3) 跑
    context: dict = {"file_path": file_path}
    if args.bruteforce_limit:
        context["__bruteforce_limit__"] = args.bruteforce_limit

    print(f"\n=== executing {chain_name} chain ===\n")
    result_ctx = dag.execute(context)
    log = result_ctx.get("__log__", [])

    # 4) 打印结果
    success_count = sum(1 for step in log if step["success"])
    fail_count = sum(1 for step in log if not step["success"])
    print(f"--- chain log ({len(log)} steps) ---")
    for step in log:
        marker = "OK" if step["success"] else "FAIL"
        print(f"  [{step['step']}] {step['node']:25s} {marker:5s}  {step['message'][:80]}")
    print(f"\n--- summary ---")
    print(f"  total:   {len(log)} steps")
    print(f"  success: {success_count}")
    print(f"  failure: {fail_count}")

    # 5) 拿最终 ToolResult
    last_result = result_ctx.get("__last_result__")
    if last_result and last_result.success:
        print(f"\n--- last action data ---")
        for k, v in last_result.data.items():
            if isinstance(v, str) and len(v) > 100:
                v = v[:100] + "..."
            print(f"  {k}: {v}")

    # 6) cleanup backup（如果 fix_pseudo 跑了）
    backup = Path(file_path).with_suffix(Path(file_path).suffix + ".bak")
    if backup.exists() and not args.keep_backup:
        backup.unlink()
        print(f"  [cleanup] removed {backup}")

    return 0 if success_count > 0 else 1


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

    p_gui = sub.add_parser("gui", help="启动 PySide6 GUI 主窗口（macOS only）")
    p_gui.set_defaults(func=cmd_gui)

    p_decode = sub.add_parser("decode", help="解码器（v0.5+ standalone, 自动从 registry 注册）")
    p_decode_sub = p_decode.add_subparsers(dest="decode_cmd")
    # 触发 decoder 注册 (import 一次即生效)
    from automisc.core.decoders import base64_image  # noqa: F401
    from automisc.core.decoders import base_convert  # noqa: F401
    from automisc.core.decoders import coords_to_qr  # noqa: F401
    # v0.5-lsb-byte-stream-extract: magic_sniffer decoder
    from automisc.core.decoders import magic_sniffer  # noqa: F401
    # v0.5-pyc-magic-sniffer: pyc_decompiler decoder
    from automisc.core.decoders import pyc_decompiler  # noqa: F401
    from automisc.core.decoders.registry import list_decoders
    for spec in list_decoders():
        p_sub = p_decode_sub.add_parser(spec.name, help=spec.description)
        # v0.5-hex-ascii-fix: --file 不再 required, 允许 --text 文本模式
        p_sub.add_argument(
            "--file", required=False, help="目标文件路径", dest="file_path"
        )
        # v0.5-hex-ascii-fix + v0.5-coords-qr: text-based decoders 接受 --text
        p_sub.add_argument(
            "--text", required=False,
            help="直接传文本 (跟 --file 二选一; e.g. coords-qr 用 '(7,7),(7,8),...')"
        )
        # 通用 args: --out-dir, --keep
        p_sub.add_argument(
            "--out-dir", default=None,
            help="输出目录 (None = 与 input 同目录, v0.5-output-samedir)"
        )
        p_sub.add_argument(
            "--keep", action="store_true", help="保留 output 文件（默认删）"
        )
        # v0.5-cipher-decoders: cipher decoder 通用参数
        # (dispatcher 用 inspect 过滤掉 runner 不认识的 kwargs, 这里全加不会出错)
        p_sub.add_argument(
            "--shift", type=int, default=None,
            help="凯撒解密位移 (caesar 用, 默认 3)"
        )
        p_sub.add_argument(
            "--rails", type=int, default=None,
            help="栅栏解密层数 (rail-fence 用, 默认 2)"
        )
        p_sub.add_argument(
            "--variant", default=None,
            help="变体参数 (bacon 用 '24'/'26', pigpen 用 'unicode'/'simple')"
        )
        p_sub.add_argument(
            "--word-sep", default=None,
            help="摩尔斯单词间分隔符 (morse 用, 默认 ' '; 传 '' 拼成连续字符串, CTF 数字串场景)"
        )
        # v0.5-lsb-byte-stream-extract: magic_sniffer decoder 通用参数
        p_sub.add_argument(
            "--max-offset", type=int, default=32,
            help="magic 嗅探扫描最大偏移 (magic_sniffer 用, 默认 32)"
        )
        p_sub.set_defaults(func=cmd_decode_dispatcher, decoder_name=spec.name)

    p_chain = sub.add_parser("chain", help="运行预定义 DAG chain (v0.5-DAG)")
    p_chain.add_argument(
        "--chain",
        required=True,
        choices=["zip", "zip-full", "binwalk", "foremost", "lsb", "lsb-bytes"],
        help="chain 类型: zip / zip-full / binwalk (检测+foremost提取) / foremost (单独提取) / lsb (zsteg 智能路由) / lsb-bytes (4 参数自定义抽取)",
    )
    p_chain.add_argument("--file", required=True, help="目标文件路径")
    p_chain.add_argument(
        "--bruteforce-limit",
        type=int,
        default=None,
        help="bruteforce 字典上限 (测试用; 8.4M 完整字典太慢)",
    )
    p_chain.add_argument(
        "--keep-backup",
        action="store_true",
        help="保留 fix_pseudo 的 .bak 备份 (默认清理)",
    )
    # v0.5-lsb-byte-stream-extract: lsb-bytes chain 4 参数
    p_chain.add_argument(
        "--channels",
        default=None,
        help="lsb-bytes 用: 通道列表 e.g. 'G' 或 'RGB' (默认 RGB 三通道)",
    )
    p_chain.add_argument(
        "--bit",
        type=int,
        default=0,
        help="lsb-bytes 用: bit 位 0~7 (默认 0 = LSB)",
    )
    p_chain.add_argument(
        "--scan-order",
        default="row",
        choices=["row", "col"],
        help="lsb-bytes 用: 扫描顺序 (默认 row, writeup 是 col)",
    )
    p_chain.add_argument(
        "--byte-bit-order",
        default="MSB",
        choices=["MSB", "LSB"],
        help="lsb-bytes 用: 字节内 bit 顺序 (默认 MSB)",
    )
    p_chain.set_defaults(func=cmd_chain)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "tools" and getattr(args, "tools_cmd", None) == "list":
        return cmd_tools_list(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "gui":
        return cmd_gui(args)
    if args.cmd == "chain":
        return cmd_chain(args)
    if args.cmd == "decode" and getattr(args, "decode_cmd", None):
        return cmd_decode_dispatcher(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())