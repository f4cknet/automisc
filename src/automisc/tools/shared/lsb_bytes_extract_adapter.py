"""lsb_bytes_extract adapter —— auto-run 兜底 zsteg 漏报 (per v0.5-lsb-bytes-auto-run).

**目的**: 把 ``LSBBytesExtractAction`` 包成 adapter, 让 ``core.run_tool`` 统一入口能跑。
默认跑 12 组合 (RGB × bit 0/7 × row/col × MSB), ~5s/张图, zsteg 兜不住的 N=NP 类 LSB 题自动命中。

**与 GUI user-controlled 入口的关系** (互补):
- v0.5-lsb-bytes-gui (main `c898a46`): GUI Run→Chain 弹 dialog 收 4 参数, user-controlled
- 本迭代: auto-run 拖图片自动跑, 默认 12 组合兜底

**不在 owner-specific 参数场景**:
- 96 组合 (3 通道 × 8 bit × 2 scan_order × 2 byte_bit_order) 不可能全跑, 默认 12 组合是实战常用子集
- 想要 96 全跑 / RGBA / bit 1-6 等特殊组合 → 走 GUI user-controlled (v0.5-lsb-bytes-gui)

**与 magic_sniffer 关系**:
- 写完 .bin 后**不**自动调 magic_sniffer (decoder 不混进 Action 链, per v0.5-lsb-byte-stream-extract spec §3.1)
- Owner 看 auto-run SP 命中后, 自己决定跑不跑 magic_sniffer (Tools 菜单)

**用法**:
- auto-run (默认): `core.run_tool("lsb_bytes_extract", file_path)` → 跑 12 组合
- 手工 (CLI): `automisc chain --chain lsb-bytes --file X` (per v0.5-lsb-byte-stream-extract)

**注册**:
- @register_tool 装饰器 → registry
- 双注册: tools/__init__.py + tools/shared/__init__.py (per automisc-tool-registration memory)
"""
from __future__ import annotations

from automisc.core.actions.lsb_bytes_extract import LSBBytesExtractAction
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


@register_tool
class LsbBytesExtractAdapter(ToolAdapter):
    """lsb_bytes_extract adapter —— auto-run 兜底 zsteg 漏报 (per v0.5-lsb-bytes-auto-run).

    默认跑 12 组合 (RGB × bit 0/7 × row/col × MSB), ~5s/张图。
    auto-run 拖图片自动调; GUI user-controlled 4 参数走 `lsb-bytes` chain (per v0.5-lsb-bytes-gui)。

    **失败 graceful**:
    - PIL/numpy 没装 → SP severity=2 "usage_hint" 风格 (per v0.5-auto-run-discipline 铁律 "不中断")
    - 文件不存在 / 损坏 → 同上
    - 通道不支持 (JPEG) → action 内部 graceful skip, adapter 包装成 SP
    """

    name = "lsb_bytes_extract"
    category = "shared"
    description = (
        "LSB 字节流自定义抽取 (12 组合兜底, zsteg 漏报时用; "
        "不依赖外部 CLI, PIL/numpy 直抽)"
    )

    default_timeout = 30.0  # 12 组合 ~5s, 给 buffer

    # 默认 12 组合: RGB × bit 0/7 × row/col × MSB (per spec §3.3.2 Q1=A 拍板)
    # 实战覆盖 N=NP 题 G 通道 bit 0 col MSB (在 12 组合里)
    DEFAULT_COMBOS = [
        # (channels, bit, scan_order, byte_bit_order)
        ("RGB", 0, "row", "MSB"),
        ("RGB", 0, "col", "MSB"),
        ("RGB", 7, "row", "MSB"),
        ("RGB", 7, "col", "MSB"),
        ("R", 0, "row", "MSB"),
        ("R", 0, "col", "MSB"),
        ("R", 7, "row", "MSB"),
        ("R", 7, "col", "MSB"),
        ("G", 0, "row", "MSB"),
        ("G", 0, "col", "MSB"),
        ("G", 7, "row", "MSB"),
        ("G", 7, "col", "MSB"),
    ]

    def run(self, file_path: str) -> ToolResult:
        """auto-run 跑默认 12 组合, 写 .bin 到 input 同目录.

        Args:
            file_path: 目标图片路径 (PNG/BMP/GIF)

        Returns:
            ToolResult(success, suspicious_points, stdout/stderr)
        """
        from pathlib import Path

        from automisc.core.logging_setup import get_logger
        log = get_logger(__name__)

        p = Path(file_path)
        if not p.exists():
            return self._usage_hint_sp(
                file_path,
                f"lsb_bytes_extract: file not found: {p}",
            )

        suspicious_points: list[SuspiciousPoint] = []
        extracted_files: list[str] = []
        errors: list[str] = []
        soft_failures: list[str] = []  # ActionResult(success=False) 不抛异常, 但也没抽到内容

        # 跑 12 组合, 逐个 SP 累积 (per v0.5-auto-run-discipline 铁律 "可疑点越多越好")
        for channels, bit, scan_order, byte_bit_order in self.DEFAULT_COMBOS:
            try:
                action = LSBBytesExtractAction(
                    channels=channels,
                    bit=bit,
                    scan_order=scan_order,
                    byte_bit_order=byte_bit_order,
                )
                context = {"file_path": file_path}
                result = action.run(context)
                if result.success:
                    extracted_path = result.data.get("lsb_bytes", {}).get("extracted_path")
                    if extracted_path:
                        extracted_files.append(extracted_path)
                        suspicious_points.append(SuspiciousPoint(
                            id="",
                            tool_name=self.name,
                            file_path=file_path,
                            category="lsb_bytes_extracted",
                            offset=None,
                            matched_pattern=(
                                f"lsb_bytes_extract: channels={channels} bit={bit} "
                                f"scan_order={scan_order} byte_bit_order={byte_bit_order}"
                            ),
                            severity=5,  # 可疑, 需要人工二次分析
                            suggested_action=(
                                f"已抽 LSB 字节流到 {extracted_path}, "
                                "用 magic_sniffer (Tools 菜单) sniff 看命中 magic"
                            ),
                        ))
                else:
                    # 单组合失败 (e.g. JPEG 不支持 RGBA, 跳过) — 不中断, log + 累积
                    log.debug(
                        "lsb_bytes_extract combo skip: channels=%s bit=%d scan=%s: %s",
                        channels, bit, scan_order, result.message,
                    )
                    if result.message:
                        soft_failures.append(
                            f"channels={channels} bit={bit} scan={scan_order}: {result.message}"
                        )
            except Exception as e:  # noqa: BLE001
                errors.append(
                    f"channels={channels} bit={bit} scan={scan_order}: {e}"
                )
                log.warning(
                    "lsb_bytes_extract combo error: channels=%s bit=%d scan=%s: %s",
                    channels, bit, scan_order, e,
                )
                continue

        # 12 组合全跑完, 写 summary SP
        stdout_lines = [
            f"lsb_bytes_extract: {len(extracted_files)} 个组合抽到内容",
            f"输入: {file_path}",
        ]
        if extracted_files:
            stdout_lines.append("抽到文件:")
            for ef in extracted_files:
                stdout_lines.append(f"  - {ef}")
        if errors:
            stdout_lines.append(f"{len(errors)} 个组合异常 (已跳过):")
            for err in errors[:3]:  # 只显示前 3 个
                stdout_lines.append(f"  - {err}")

        # 异常 (exception) 总数 > 半数 → 整体 severity=2 (per v0.5-auto-run-discipline)
        if len(errors) > len(self.DEFAULT_COMBOS) // 2:
            suspicious_points.append(self._usage_hint_sp(
                file_path,
                f"lsb_bytes_extract: {len(errors)}/12 组合异常 (exception), 可能是 PIL/numpy 缺失",
            ).suspicious_points[0])
        # 全软失败 (12 组合都 ActionResult(success=False), 例如 JPEG LSB 不支持) → 提示格式
        elif not extracted_files and len(soft_failures) == len(self.DEFAULT_COMBOS):
            suspicious_points.append(self._usage_hint_sp(
                file_path,
                f"lsb_bytes_extract: 12/12 组合都没抽到内容, 可能是格式不支持 (JPEG 有损压缩 LSB 不可用)",
            ).suspicious_points[0])

        # exit_code: 没抽到文件 (包括 12 组合全 fail 或 exception 失败) → 1
        return ToolResult(
            tool_name=self.name,
            exit_code=0 if extracted_files else 1,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(errors[:5]) if errors else "",
            suspicious_points=suspicious_points,
            duration_ms=0,
        )

    def _usage_hint_sp(self, file_path: str, message: str) -> ToolResult:
        """失败 graceful: SP severity=2 (不中断 auto-run)."""
        return ToolResult(
            tool_name=self.name,
            exit_code=1,
            stdout="",
            stderr=message,
            suspicious_points=[
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="usage_hint",
                    offset=None,
                    matched_pattern=f"lsb_bytes_extract 异常: {message}",
                    severity=2,
                    suggested_action=(
                        "检查 PIL/numpy 装好 + 文件格式支持 PNG/BMP/GIF; "
                        "或走 GUI user-controlled 入口 (Run → Chain → lsb-bytes) 调 4 参数"
                    ),
                )
            ],
            duration_ms=0,
        )


__all__ = ["LsbBytesExtractAdapter", "DEFAULT_COMBOS"]


# 暴露 module-level 默认组合 (per v0.5-lsb-bytes-auto-run spec §3.3.2 Q1=A 拍板)
# 测试需要 import 这个常量, 所以放 module-level (class attribute 也可访问, 但 module-level 语义更清晰)
DEFAULT_COMBOS = LsbBytesExtractAdapter.DEFAULT_COMBOS