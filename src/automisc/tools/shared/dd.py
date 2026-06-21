"""dd adapter —— 手工单文件雕刻 (foremost 兜底).

**v0.5-journal-highlight-keywords Q9 新增** (per Owner 2026-06-16 1:28 实测拍板):
- foremost 在某些样本雕不出 (e.g. 套娃嵌 ZIP, foremost magic 误判)
- binwalk 报 offset 0x109B3 有 ZIP, 但 binwalk -e 在 PySide6 QThread 死锁 (Q8)
- dd 单文件雕, 按 offset+size 切, 是最稳兜底

**用法 (手工, 不进 auto-run)**:
- CLI: ``automisc carve <file> --offset 0x109B3 --size 233 --ext zip``
- 或 GUI: foremost 0 extracted 时, SP context 提示用户手动跑 dd

**不在 auto-run 列表** (router.py 不注册 dd):
- dd 需要 offset 参数, run(file_path) 签名不带参数
- 手工工具, 不适合 auto-run (auto-run 不知道雕哪里)

**v0.5 Q9 后续 (Q10 候选)**:
- GUI 端 foremost 跑完 0 extracted → status bar "雕不出来, 用 dd 兜底?" dialog
- user 选 Yes → 拿 binwalk SP offset, 调 dd carve
- 这违反铁律 5 (单题打补丁) → 等 ≥ 3 道同类 foremost 雕不出样本再升架构
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.core.utils.output_path import extract_dir_for
from automisc.tools.base import ToolAdapter


@register_tool
class DdAdapter(ToolAdapter):
    """`dd` adapter —— 单文件雕 (offset+size), foremost 兜底 (per v0.5 Q9).

    **不在 auto-run 跑** (需要 offset/size 参数).
    手工触发: ``automisc carve <file> --offset X --size Y --ext zip``.
    """

    name = "dd"
    category = "shared"
    description = "dd 单文件雕 (offset+size), foremost 兜底; 不进 auto-run"

    default_timeout = 5.0  # dd 应该极快 (< 1s)

    def run(self, file_path: str) -> ToolResult:
        # dd adapter 不在 auto-run 跑, 如果误调, 返回明确错误 SP
        return ToolResult(
            tool_name=self.name,
            exit_code=1,
            stdout="",
            stderr=(
                "dd adapter 不在 auto-run 跑 (需要 offset/size 参数).\n"
                "请用 CLI: automisc carve <file> --offset X --size Y --ext zip\n"
                "或 GUI 手工触发 (per v0.5 Q9 文档)."
            ),
            suspicious_points=[
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="usage_hint",
                    offset=None,
                    matched_pattern="dd 误调: 需要 offset/size 参数",
                    severity=2,
                    suggested_action=(
                        "用 automisc carve 命令:\n"
                        f"  automisc carve {file_path} --offset <HEX_OR_DEC> --size <BYTES> --ext <ext>"
                    ),
                )
            ],
            duration_ms=0,
        )

    # ---- 手工 carve 接口 (CLI/GUI 触发) ----

    def carve(
        self,
        file_path: str,
        offset: int,
        size: int,
        ext: str = "bin",
    ) -> ToolResult:
        """手工雕: dd if=<file> bs=1 skip=<offset> count=<size> of=<out>.<ext>.

        Args:
            file_path: 输入文件路径
            offset: 雕 offset (bytes), 十进制
            size: 雕 size (bytes)
            ext: 输出扩展名 (e.g. "zip", "jpg")

        Returns:
            ToolResult with suspicious_points = [1 个 extracted_file SP]
        """
        from automisc.core.logging_setup import get_logger
        log = get_logger(__name__)
        log.info(
            "DdAdapter.carve: file=%s offset=%d size=%d ext=%s",
            file_path, offset, size, ext,
        )

        if size <= 0 or size > 1_000_000_000:  # 1GB 兜底
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"invalid size={size} (must be 0 < size <= 1GB)",
                suspicious_points=[],
                duration_ms=0,
            )

        # 输出路径: <input_dir>/<stem>__dd_extracted/<offset_hex>.<ext>
        outdir = extract_dir_for(file_path, purpose="dd_extracted")
        outdir.mkdir(parents=True, exist_ok=True)
        out_file = outdir / f"{offset:x}.{ext}"

        # dd 命令
        cmd = [
            "dd",
            f"if={file_path}",
            "bs=1",
            f"skip={offset}",
            f"count={size}",
            f"of={out_file}",
            "status=none",  # macOS BSD dd 不支持 status=noxfer, 用 status=none
        ]
        try:
            ec, so, se, dur = self._run_subprocess(cmd)
        except Exception as e:
            import traceback
            log.error("DdAdapter.carve: dd failed: %s\n%s", e, traceback.format_exc())
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"dd failed: {e}",
                suspicious_points=[],
                duration_ms=0,
            )
        log.info(
            "DdAdapter.carve: dd done exit=%d dur=%dms out=%s exists=%s",
            ec, dur, out_file, out_file.exists(),
        )

        if not out_file.exists():
            return ToolResult(
                tool_name=self.name,
                exit_code=ec or 1,
                stdout=so,
                stderr=se or f"dd 输出文件不存在: {out_file}",
                suspicious_points=[],
                duration_ms=dur,
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=ec,
            stdout=so,
            stderr=se,
            suspicious_points=[
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="extracted_files",
                    offset=offset,
                    matched_pattern=(
                        f"dd 雕出文件 ({size} bytes @ offset {offset}) -> {out_file}"
                    ),
                    severity=4,
                    suggested_action=f"查看雕出文件: {out_file}",
                    context=f"ext={ext}, size={size}",
                )
            ],
            duration_ms=dur,
        )


# ---- CLI 入口 ----

def _main():
    """CLI: automisc carve <file> --offset X --size Y --ext zip"""
    parser = argparse.ArgumentParser(
        prog="automisc carve",
        description="dd 单文件雕 (offset+size), foremost 兜底",
    )
    parser.add_argument("file", help="输入文件路径")
    parser.add_argument(
        "--offset", required=True, type=lambda s: int(s, 0),
        help="雕 offset (bytes), 接受 hex (0x...) 或十进制",
    )
    parser.add_argument("--size", required=True, type=int, help="雕 size (bytes)")
    parser.add_argument("--ext", default="bin", help="输出扩展名 (默认 bin)")
    args = parser.parse_args()

    adapter = DdAdapter()
    result = adapter.carve(
        file_path=args.file,
        offset=args.offset,
        size=args.size,
        ext=args.ext,
    )
    print(f"exit: {result.exit_code}, duration: {result.duration_ms}ms")
    for sp in result.suspicious_points:
        print(f"  {sp.matched_pattern}")
    sys.exit(result.exit_code)


if __name__ == "__main__":
    _main()


__all__ = ["DdAdapter"]
